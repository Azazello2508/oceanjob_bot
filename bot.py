"""Проверяет новые вакансии Chief Officer на crewell.net и присылает их в Telegram."""

import hashlib
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
    "OnlyYacht", "Yacht_Vacancies", "truemalina_offshore", "Crew_Radar", "Offshore_Vacancies", "Sea_format", "univis_crewing", "Merchant_Fleet", "sidantey", "passengerFleetJob", "ismira_agency", "cruiseshipjobs", "marinejobz", "rekamore_su", "shipjobsindia", "ukrcrewing_official",
    # @cwyjh и @teamspirit — группы, у них нет открытой веб-страницы, читать нельзя
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


def get_ukrcrewing():
    """Блок «New Vacancies» на главной ukrcrewing: 10 самых свежих вакансий."""
    html = requests.get("https://ukrcrewing.com.ua/en", headers=HEADERS, timeout=30).text
    soup = BeautifulSoup(html, "html.parser")
    jobs, ids = [], set()
    for a in soup.find_all("a", href=True):
        m = re.search(r"/vacancy/(\d+)", a["href"])
        title = a.get_text(" ", strip=True)
        if not m or not title:
            continue
        job_id = "ukrcrewing-" + m.group(1)
        if job_id in ids or not any(k in title.lower() for k in KEYWORDS):
            continue
        ids.add(job_id)
        row = a.find_parent("tr")  # строка таблицы: судно, срок, дата, зарплата
        if row:
            title = row.get_text(" · ", strip=True)
        jobs.append({"id": job_id, "title": title,
                     "url": f"https://ukrcrewing.com.ua/en/vacancy/{m.group(1)}"})
    return jobs


# Простые сайты: страницы со списком вакансий и шаблон ссылки на одну вакансию
SITES = {
    "martide.com": {
        "pages": ["https://www.martide.com/en/jobs/chief-officer",
                  "https://www.martide.com/en/jobs/second-officer"],
        "pattern": r"/en/jobs/[\w-]+-(\d+)/?$",
        "base": "https://www.martide.com",
    },
    "seacareer.com": {
        "pages": ["https://www.seacareer.com/chief-officer-sdpo-jobs/",
                  "https://www.seacareer.com/deck-officer-jobs/",
                  "https://www.seacareer.com/junior-deck-officer-jobs/",
                  "https://www.seacareer.com/offshore-jobs/"],
        "pattern": r"/i(\d+)/[\w-]+/?$",
        "base": "https://www.seacareer.com",
    },
    "crewlinker.com": {
        "pages": ["https://www.crewlinker.com/job-openings"],
        "pattern": r"/job-posting/(\d+)",
        "base": "https://www.crewlinker.com",
    },
    "seajobs.ru": {
        "pages": ["https://www.seajobs.ru/ru/vacancies?page=1",
                  "https://www.seajobs.ru/ru/vacancies?page=2"],
        "pattern": r"/vacancy/(\d+)",
        "base": "https://seajobs.ru",
    },
    "maritime-union.com": {
        "pages": ["https://maritime-union.com/jobs",
                  "https://maritime-union.com/jobs?p=2"],
        "pattern": r"/job/(\d+)",
        "base": "https://maritime-union.com",
    },
    "seafarerjobs.com": {
        "pages": ["https://www.seafarerjobs.com/hot-jobs"],
        "pattern": r"/hot-jobs/(\d+)",
        "base": "https://www.seafarerjobs.com",
    },
    "rigzone.com": {
        "pages": [f"https://www.rigzone.com/oil/jobs/search/?sk={q}"
                  for q in ["chief+officer", "chief+mate", "second+officer", "dpo"]],
        "pattern": r"/oil/jobs/postings/(\d+)_",
        "base": "https://www.rigzone.com",
    },
}


def get_site(name):
    """Собирает вакансии с сайта из SITES: ищет ссылки по шаблону и фильтрует по словам."""
    site = SITES[name]
    jobs, ids = [], set()
    for page in site["pages"]:
        html = requests.get(page, headers=HEADERS, timeout=30).text
        for a in BeautifulSoup(html, "html.parser").find_all("a", href=True):
            m = re.search(site["pattern"], a["href"])
            title = a.get_text(" ", strip=True)
            if not m or not title:
                continue
            job_id = f"{name}-{m.group(1)}"
            # Ищем слова и в тексте ссылки, и в самом адресе (там часто есть должность)
            where = (title + " " + a["href"].replace("-", " ")).lower()
            if job_id in ids or not any(k in where for k in KEYWORDS):
                continue
            ids.add(job_id)
            url = a["href"] if a["href"].startswith("http") else site["base"] + a["href"]
            jobs.append({"id": job_id, "title": title, "url": url})
    return jobs


def fingerprint(text):
    """«Отпечаток» текста вакансии: одинаков у одного и того же поста в разных каналах.
    Убираем ссылки, @имена, эмодзи и знаки — оставляем буквы и цифры."""
    t = re.sub(r"https?://\S+|@\w+", " ", text.lower())
    t = re.sub(r"[^\w]+", " ", t).strip()
    if len(t) < 60:  # слишком короткий текст — легко спутать разные вакансии
        return None
    return "fp-" + hashlib.md5(t[:300].encode()).hexdigest()[:16]


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
                "title": text[:1500] + ("…" if len(text) > 1500 else ""),
                "found": [k for k in KEYWORDS if k in text.lower()],
                "url": "https://t.me/" + post,
                "fp": fingerprint(text),
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

    sources = [("crewell", "crewell.net", get_crewell),
               ("ukrcrewing", "ukrcrewing.com.ua", get_ukrcrewing)]
    sources += [(name, name, lambda name=name: get_site(name)) for name in SITES]
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
            fp = job.get("fp")
            if fp and fp in seen:
                print(f"Дубль, пропускаю: {job['url']}")
                continue
            found = job.get("found")
            head = f"🔎 Найдено: {', '.join(found)}\n\n" if found else ""
            send(f"{head}🚢 {job['title']}\n\n{label}\n{job['url']}")
            sent += 1
            if fp:
                seen.add(fp)
        seen.update(j["id"] for j in jobs)
        # Запоминаем отпечатки и уже известных постов, чтобы их копии в других каналах не пришли
        seen.update(j["fp"] for j in jobs if j.get("fp"))

    if report:
        send("Подключены новые источники. Старые посты не присылаю, дальше — только новые.\n\n"
             + "\n".join(report))

    save_seen(seen)
    print(f"Отправлено: {sent}")


if __name__ == "__main__":
    main()
