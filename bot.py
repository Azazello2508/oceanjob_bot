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
KEYWORDS = [
    "chief officer", "c/o", "chief mate", "jdpo",
    "second officer", "2nd officer", "2/o", "dp basic",
]
KEYWORDS_VERSION = 2


# Публичные Telegram-каналы с вакансиями: имя канала из ссылки t.me/ИМЯ
CHANNELS = [
    "maritimeforum", "seajobfinder", "onboard_su", "CREW_ARIA", "marinejobs",
    "crewingua", "jobfor_seamen", "seamenjob", "andreeyVstart", "job_for_seaman",
    "marineman_ltd", "balticcareer", "BSMCSCUKRAINE", "olive_crew", "allcrewing",
    "crewtrud", "merchantFleetJob", "JobForMariners", "seamenvacancy", "merchantNavyrealjob",
    "shipscreweu", "supermariner_ua", "SM_job_center", "offshorecv", "offshorevacancies",
    "help_seafarers", "OffshoreFleetJob", "ALPHACREW", "OnlyOffshore", "roster_marine",
    "galaxymaritimeua", "oilrigs", "vshipsoffshore",
]

# Страницы crewell: старшие офицеры (Chief Officer) и вахтенные (2nd Officer)
CREWELL_URLS = [
    "https://crewell.net/en/vacancies/?positionGroup=109",
    "https://crewell.net/en/vacancies/?positionGroup=110",
]

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
    links = []
    for page in CREWELL_URLS:
        html = requests.get(page, headers=HEADERS, timeout=30).text
        links += BeautifulSoup(html, "html.parser").find_all("a", href=True)
    jobs, ids = [], set()
    for a in links:
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
    messages = soup.select("div.tgme_widget_message[data-post]")
    if not messages:
        raise ValueError("у канала нет открытой веб-страницы или он закрытый")
    jobs = []
    for msg in messages:
        box = msg.select_one("div.tgme_widget_message_text")
        if not box:
            continue
        text = box.get_text("\n", strip=True)
        if any(k in text.lower() for k in KEYWORDS):
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

    sources = [("crewell", "crewell.net", get_crewell)]
    sources += [(f"tg:{c}", f"Telegram: @{c}", lambda c=c: get_channel(c)) for c in CHANNELS]

    sent = 0
    report = []  # отчёт о новых источниках — придёт одним сообщением
    for key, label, fetch in sources:
        # Версия набора ключевых слов. При смене слов увеличиваем её — тогда
        # все источники подключаются заново и старые посты не присылаются разом.
        marker = f"source-v{KEYWORDS_VERSION}-" + key
        try:
            jobs = fetch()
        except Exception as e:  # один сломавшийся источник не должен ломать остальные
            print(f"Ошибка в источнике {label}: {e}")
            if marker not in seen and "fail-" + key not in seen:
                report.append(f"❌ {label} — не открылся (сообщу об этом один раз)")
                seen.add("fail-" + key)
            continue
        print(f"{label}: найдено {len(jobs)}")

        if marker not in seen:
            # Источник новый: старые вакансии не присылаем, просто запоминаем.
            report.append(f"✅ {label} — подходящих постов сейчас: {len(jobs)}")
            to_send = []
            seen.add(marker)
        else:
            to_send = [j for j in jobs if j["id"] not in seen]

        for job in reversed(to_send):  # от старых к новым
            send(f"🚢 {job['title']}\n\n{label}\n{job['url']}")
        sent += len(to_send)
        seen.update(j["id"] for j in jobs)

    if report:
        send("Подключены новые источники. Старые посты не присылаю, дальше — только новые.\n\n"
             + "\n".join(report))

    save_seen(seen)
    print(f"Отправлено: {sent}")


if __name__ == "__main__":
    main()
