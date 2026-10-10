"""Проверяет новые вакансии Chief Officer на crewell.net и присылает их в Telegram."""

import json
import os
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup

TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

# Какие должности искать (без учёта регистра)
KEYWORDS = ["chief officer", "chief mate"]

# Для Telegram-каналов: в постах пишут по-разному, поэтому слов больше
CHANNEL_KEYWORDS = KEYWORDS + ["c/o", "старпом", "старший помощник", "ст. помощник", "ст.помощник"]

# Публичные Telegram-каналы с вакансиями: имя канала из ссылки t.me/ИМЯ
CHANNELS = []

# Страница crewell с вакансиями старших офицеров
CREWELL_URL = "https://crewell.net/en/vacancies/?positionGroup=109"

# Файл, где запоминаем уже отправленные вакансии
SEEN_FILE = Path("seen.json")

HEADERS = {"User-Agent": "Mozilla/5.0 (oceanjob_bot; personal job alerts)"}


def load_seen():
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text()))
    return None  # первый запуск


def save_seen(seen):
    SEEN_FILE.write_text(json.dumps(sorted(seen), indent=0))


def get_crewell():
    """Возвращает список вакансий: [{'id', 'title', 'url'}], новые сверху."""
    html = requests.get(CREWELL_URL, headers=HEADERS, timeout=30).text
    soup = BeautifulSoup(html, "html.parser")
    jobs, ids = [], set()
    for a in soup.find_all("a", href=True):
        m = re.search(r"/vacancies/(\d+)/?$", a["href"])
        title = a.get_text(" ", strip=True)
        if not m or not title or "apply" in title.lower():
            continue
        job_id = "crewell-" + m.group(1)
        if job_id in ids:
            continue
        if any(k in title.lower() for k in KEYWORDS):
            ids.add(job_id)
            url = a["href"]
            if url.startswith("/"):
                url = "https://crewell.net" + url
            jobs.append({"id": job_id, "title": title, "url": url})
    return jobs


def get_channel(name):
    """Читает последние посты публичного канала через его веб-страницу t.me/s/ИМЯ."""
    html = requests.get(f"https://t.me/s/{name}", headers=HEADERS, timeout=30).text
    soup = BeautifulSoup(html, "html.parser")
    jobs = []
    for msg in soup.select("div.tgme_widget_message[data-post]"):
        box = msg.select_one("div.tgme_widget_message_text")
        if not box:
            continue
        text = box.get_text("\n", strip=True)
        if any(k in text.lower() for k in CHANNEL_KEYWORDS):
            post = msg["data-post"]  # вида "имя/12345"
            jobs.append({
                "id": "tg-" + post,
                "title": text[:400] + ("…" if len(text) > 400 else ""),
                "url": "https://t.me/" + post,
            })
    jobs.reverse()  # на странице старые сверху, а нам нужно новые сверху
    return jobs


def send(text):
    r = requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": text},
        timeout=30,
    )
    r.raise_for_status()


def main():
    seen = load_seen() or set()
    if any(s.startswith("crewell-") for s in seen):
        seen.add("source-crewell")  # crewell уже подключали раньше

    sources = [("crewell", "crewell.net", get_crewell)]
    sources += [(f"tg:{c}", f"Telegram: @{c}", lambda c=c: get_channel(c)) for c in CHANNELS]

    sent = 0
    for key, label, fetch in sources:
        try:
            jobs = fetch()
        except Exception as e:  # один сломавшийся источник не должен ломать остальные
            print(f"Ошибка в источнике {label}: {e}")
            continue
        print(f"{label}: найдено {len(jobs)}")

        marker = "source-" + key
        if marker not in seen:
            # Источник новый: присылаем 3 свежие, остальные просто запоминаем,
            # чтобы не завалить чат старыми вакансиями.
            send(f"✅ Подключён источник {label}. Найдено вакансий: {len(jobs)}. "
                 f"Вот до 3 самых свежих, дальше — только новые.")
            to_send = jobs[:3]
            seen.add(marker)
        else:
            to_send = [j for j in jobs if j["id"] not in seen]

        for job in reversed(to_send):  # от старых к новым
            send(f"🚢 {job['title']}\n\n{label}\n{job['url']}")
        sent += len(to_send)
        seen.update(j["id"] for j in jobs)

    save_seen(seen)
    print(f"Отправлено: {sent}")


if __name__ == "__main__":
    main()
