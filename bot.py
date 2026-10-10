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


def send(text):
    r = requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": text},
        timeout=30,
    )
    r.raise_for_status()


def main():
    jobs = get_crewell()
    print(f"Найдено вакансий: {len(jobs)}")
    seen = load_seen()

    if seen is None:
        # Первый запуск: присылаем 3 свежие и запоминаем все остальные,
        # чтобы не завалить чат старыми вакансиями.
        send(f"✅ Бот запущен. Сейчас на crewell {len(jobs)} вакансий Chief Officer. "
             f"Вот 3 самые свежие, дальше буду присылать только новые.")
        to_send = jobs[:3]
        seen = set()
    else:
        to_send = [j for j in jobs if j["id"] not in seen]

    for job in reversed(to_send):  # от старых к новым
        send(f"🚢 {job['title']}\ncrewell.net\n{job['url']}")

    seen.update(j["id"] for j in jobs)
    save_seen(seen)
    print(f"Отправлено: {len(to_send)}")


if __name__ == "__main__":
    main()
