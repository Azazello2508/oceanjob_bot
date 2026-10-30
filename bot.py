"""Проверяет новые вакансии Chief Officer на crewell.net и присылает их в Telegram."""

import hashlib
import html
import json
import os
from datetime import datetime, timedelta, timezone
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup

TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

# Какие должности искать (без учёта регистра)
KEYWORDS = [
    "chief officer", "c/o", "chief mate", "jdpo",
    "second officer", "2nd officer", "2/o", "dp basic", "dp induction", "sdpo", "dpo",
    "2off", "2nd off", "2/off",
    # оффшорные сокращения
    "co/dpo", "co/sdpo", "2o/dpo", "ch/off", "choff",
    # русские названия
    "старпом", "старший помощник", "ст. помощник", "ст.помощник",
]
KEYWORDS_VERSION = 5


# Публичные Telegram-каналы с вакансиями: имя канала из ссылки t.me/ИМЯ
CHANNELS = [
    "maritimeforum", "seajobfinder", "onboard_su", "CREW_ARIA", "marinejobs",
    "crewingua", "jobfor_seamen", "seamenjob", "andreeyVstart", "job_for_seaman",
    "marineman_ltd", "balticcareer", "BSMCSCUKRAINE", "olive_crew", "allcrewing",
    "crewtrud", "merchantFleetJob", "JobForMariners", "seamenvacancy", "merchantNavyrealjob",
    "shipscreweu", "supermariner_ua", "SM_job_center", "offshorecv", "offshorevacancies",
    "help_seafarers", "OffshoreFleetJob", "ALPHACREW", "OnlyOffshore", "roster_marine",
    "galaxymaritimeua", "oilrigs", "vshipsoffshore",
    "OnlyYacht", "Yacht_Vacancies", "truemalina_offshore", "Crew_Radar", "Offshore_Vacancies", "Sea_format", "univis_crewing", "Merchant_Fleet", "sidantey", "passengerFleetJob", "ismira_agency", "cruiseshipjobs", "marinejobz", "rekamore_su", "shipjobsindia", "ukrcrewing_official", "TSMexp", "marinecareerorg", "findseajobs", "morehod_ru", "offshoreatsea", "gm_seaman_cv",
    "Official_SSA", "seavacancies", "oceancrewjobs", "stellamarine_public", "crs_vacancies", "sea111work", "MarineOdessa",
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


# Тексты ссылок, которые не являются названием вакансии
JUNK_TITLES = {"details & apply", "details", "apply", "view", "view & apply »", "view & apply",
               "read more", "more", "подробнее"}
# На этих сайтах у вакансий номера идут по порядку: новая вакансия = номер больше прежних
SEQUENTIAL = {"crewell", "ukrcrewing", "seajobs.ru", "seacareer.com", "maritime-union.com",
              "crewlinker.com", "rigzone.com", "seafarerjobs.com"}


def get_site(name):
    """Собирает вакансии с сайта из SITES: ищет ссылки по шаблону и фильтрует по словам."""
    site = SITES[name]
    jobs, ids = [], set()
    for page in site["pages"]:
        html = requests.get(page, headers=HEADERS, timeout=30).text
        for a in BeautifulSoup(html, "html.parser").find_all("a", href=True):
            m = re.search(site["pattern"], a["href"])
            title = a.get_text(" ", strip=True)
            if not m or not title or title.lower() in JUNK_TITLES:
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


# Самый большой номер поста, увиденный в каждом канале за эту проверку
LAST_POST = {}
# До какого номера поста листать канал назад (если сегодня канал уже читали)
STOP_AT = {}


def num(job_id):
    """Номер вакансии/поста из её id (последнее число)."""
    nums = re.findall(r"\d+", job_id)
    return int(nums[-1]) if nums else 0


def today_start():
    """Начало текущих суток по времени Батуми."""
    now = datetime.now(LOCAL_TZ)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def get_channel(name, max_pages=6):
    """Читает посты публичного канала (веб-страница t.me/s/ИМЯ) за сегодняшний день.
    Страница показывает ~20 последних постов, поэтому листаем назад, пока не дойдём до вчера."""
    url = f"https://t.me/s/{name}"
    messages = []
    for _ in range(max_pages):
        html_page = requests.get(url, headers=HEADERS, timeout=30).text
        page = BeautifulSoup(html_page, "html.parser").select("div.tgme_widget_message[data-post]")
        if not page:
            break
        messages += page
        times = [t["datetime"] for t in BeautifulSoup(html_page, "html.parser").select("time[datetime]")]
        oldest_time = min((datetime.fromisoformat(t) for t in times), default=None)
        if oldest_time is None or oldest_time < today_start():
            break
        if STOP_AT.get(name) and min(num(m["data-post"]) for m in page) <= STOP_AT[name]:
            break  # дальше — посты, которые бот уже видел
        url = f"https://t.me/s/{name}?before={min(num(m['data-post']) for m in page)}"
    if not messages:
        raise ValueError("у канала нет открытой веб-страницы или он закрытый")
    LAST_POST[f"tg:{name}"] = max(num(m["data-post"]) for m in messages)
    jobs, ids = [], set()
    for msg in messages:
        post = msg["data-post"]  # вида "имя/12345"
        box = msg.select_one("div.tgme_widget_message_text")
        if not box or post in ids:
            continue
        ids.add(post)
        text = box.get_text("\n", strip=True)
        if any(k in text.lower() for k in KEYWORDS):
            t = msg.select_one("a.tgme_widget_message_date time[datetime]") or msg.select_one("time[datetime]")
            jobs.append({
                "id": "tg-" + post,
                "title": text[:1500] + ("…" if len(text) > 1500 else ""),
                "found": [k for k in KEYWORDS if k in text.lower()],
                "url": "https://t.me/" + post,
                "fp": fingerprint(text),
                "date": datetime.fromisoformat(t["datetime"]).isoformat() if t else None,
            })
    jobs.sort(key=lambda j: num(j["id"]), reverse=True)  # новые сверху
    return jobs


def send(text, html_mode=False):
    data = {"chat_id": CHAT_ID, "text": text, "disable_web_page_preview": "true"}
    if html_mode:
        data["parse_mode"] = "HTML"
    r = requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data=data, timeout=30)
    r.raise_for_status()
    global LAST_SENT
    LAST_SENT = r.json()["result"]["message_id"]
    return LAST_SENT


LAST_SENT = 0
KEEP_IDS = []   # сообщения, которые чистка чата не трогает (справочник крюингов)


def clear_chat(from_id, to_id):
    """Удаляет из чата все сообщения с номерами from_id..to_id (и бота, и ваши).
    Telegram позволяет удалять только сообщения младше 48 часов — остальные пропускаются."""
    keep = set(KEEP_IDS)
    ids = [i for i in range(max(1, from_id), to_id + 1) if i not in keep]
    for i in range(0, len(ids), 100):
        batch = ids[i:i + 100]
        try:
            r = requests.post(f"https://api.telegram.org/bot{TOKEN}/deleteMessages",
                              json={"chat_id": CHAT_ID, "message_ids": batch}, timeout=30)
            ok = r.json().get("ok")
        except Exception as e:
            print(f"Пакетное удаление не сработало: {e}")
            ok = False
        if not ok:
            for mid in batch:
                delete(mid)


def delete(message_id):
    try:
        requests.post(f"https://api.telegram.org/bot{TOKEN}/deleteMessage",
                      data={"chat_id": CHAT_ID, "message_id": message_id}, timeout=30)
    except Exception as e:
        print(f"Не удалось удалить сообщение {message_id}: {e}")


# ---------- Список вакансий за день ----------
DAY_FILE = Path("day.json")
LOCAL_TZ = timezone(timedelta(hours=4))   # время Батуми
LIST_EVERY = timedelta(minutes=45)        # как часто обновлять список
MAX_LEN = 3800                            # лимит Telegram — 4096 знаков на сообщение


def load_day():
    if DAY_FILE.exists():
        return json.loads(DAY_FILE.read_text())
    return {"date": "", "jobs": [], "msg_ids": [], "last_list": ""}


def save_day(day):
    DAY_FILE.write_text(json.dumps(day, ensure_ascii=False, indent=0))


def short(text, limit=160):
    """Первая содержательная строка поста — для краткого списка."""
    for line in text.splitlines():
        line = line.strip(" -•*🔥⚓️🚢⚡️❗️")
        if len(line) > 3:
            text = line
            break
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


OFFSHORE_WORDS = ["offshore", "оффшор", "офшор", "psv", "ahts", "aht ", "aht,", "osv", "mpsv", "dsv",
                  "fsv", "fcs", "crew boat", "supply vessel", "anchor handl", "dp1", "dp2", "dp3",
                  "dp-1", "dp-2", "dp-3", "dpo", "sdpo", "jack-up", "jack up", "rig ", "platform",
                  "subsea", "rov", "wind farm", "ctv", "sov ", "walk to work", "w2w", "oil & gas",
                  "survey vessel", "cable lay", "pipe lay", "standby vessel", "erv", "fpso", "28/28",
                  "21/21", "35/35", "/day", "per day", "day rate"]


def is_offshore(text):
    t = " " + text.lower() + " "
    return any(w in t for w in OFFSHORE_WORDS)


def render(day):
    """Готовит текст списка (может получиться несколько сообщений).
    Сначала — оффшорные вакансии, потом остальные; в каждой части новые сверху."""
    for j in day["jobs"]:
        j.setdefault("offshore", is_offshore(j["title"]))
    order = lambda j: (not j["new"], -datetime.fromisoformat(j["time"]).timestamp())
    off = sorted([j for j in day["jobs"] if j["offshore"]], key=order)
    rest = sorted([j for j in day["jobs"] if not j["offshore"]], key=order)
    n_new = sum(j["new"] for j in day["jobs"])
    head = (f"📋 <b>Вакансии за {day['date'][8:10]}.{day['date'][5:7]}</b> — всего {len(day['jobs'])}, "
            f"🛢 оффшор {len(off)}, новых {n_new}\n(обновлено в {datetime.now(LOCAL_TZ):%H:%M})\n")

    def block(j):
        mark = "🆕 <b>НОВАЯ</b>\n" if j["new"] else ""
        found = f"🔎 {html.escape(', '.join(j['found']))}\n" if j.get("found") else ""
        when = datetime.fromisoformat(j["time"]).astimezone(LOCAL_TZ).strftime("%H:%M")
        icon = "🛢" if j["offshore"] else "🚢"
        return (f"{mark}{found}🕒 {when} · {icon} {html.escape(j['title'])}\n"
                f"<i>{html.escape(j['source'])}</i> · <a href=\"{html.escape(j['url'])}\">открыть</a>")

    blocks = []
    if off:
        blocks.append(f"━━━━━━━━━━\n🛢 <b>ОФФШОР ({len(off)})</b>\n━━━━━━━━━━")
        blocks += [block(j) for j in off]
    if rest:
        blocks.append(f"━━━━━━━━━━\n🚢 <b>ОСТАЛЬНЫЕ ({len(rest)})</b>\n━━━━━━━━━━")
        blocks += [block(j) for j in rest]
    parts, cur = [], head
    for b in blocks:
        if len(cur) + len(b) + 2 > MAX_LEN:
            parts.append(cur)
            cur = ""
        cur += "\n" + b + "\n"
    parts.append(cur)
    return parts


def publish(day, report=None):
    parts = render(day) if day["jobs"] else ["📋 Вакансий за сегодня пока нет."]
    if report:
        parts[0] = "Подключены новые источники:\n" + html.escape("\n".join(report)) + "\n\n" + parts[0]
    new_ids = [send(part, html_mode=True) for part in parts]
    # Удаляем из чата всё, что было до нового списка: старые списки, сообщения прошлых дней
    clear_chat(day.get("cleared_upto", 0) + 1, min(new_ids) - 1)
    day["cleared_upto"] = min(new_ids) - 1
    day["msg_ids"] = new_ids
    for j in day["jobs"]:
        j["new"] = False
    day["last_list"] = datetime.now(timezone.utc).isoformat()


# ---------- Справочник крюингов ----------
CREW_FILE = Path("crewings.json")
CO_WORDS = ["chief officer", "c/o", "chief mate", "choff", "ch/off", "co/dpo", "co/sdpo",
            "старпом", "старший помощник", "ст. помощник", "ст.помощник"]
SO_WORDS = ["second officer", "2nd officer", "2/o", "2off", "2nd off", "2/off", "2o/dpo"]
VESSELS = {"Bulk": ["bulk", "балкер"], "Tanker": ["tanker", "танкер", "vlcc", "aframax"],
           "Chemical": ["chem"], "LPG/LNG": ["lpg", "lng", "gas carrier", "газовоз"],
           "Container": ["container", "контейнер"], "General cargo": ["general cargo", "mpp", "сухогруз"],
           "Offshore": ["psv", "ahts", "aht ", "offshore", "dp2", "dp1", "оффшор", "mpsv", "dsv"],
           "Tug": ["tug", "буксир"], "Ro-Ro/PCTC": ["ro-ro", "roro", "pctc", "car carrier"],
           "Reefer": ["reefer", "рефрижер"], "Passenger": ["passenger", "cruise", "пассажир"],
           "Dredger": ["dredg", "земснаряд"]}
FREE_MAIL = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "mail.ru", "ukr.net",
             "yandex.ru", "i.ua", "icloud.com", "bk.ru", "inbox.ru", "list.ru", "meta.ua", "yandex.ua"}


def load_crew():
    return json.loads(CREW_FILE.read_text()) if CREW_FILE.exists() else {"companies": {}, "last_file": ""}


def add_crewing(crew, text, source):
    """Достаёт из текста вакансии контакты крюинга и обновляет справочник."""
    low = text.lower()
    emails = sorted({e.lower().rstrip(".") for e in re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)})
    channels = {c.lower() for c in CHANNELS}
    tgs = sorted({"@" + h for h in re.findall(r"(?<![\w.])@(\w{4,})", text)
                  if h.lower() not in channels and not h.lower().endswith("bot")})
    phones = sorted({re.sub(r"[^\d+]", "", p) for p in re.findall(r"\+\d[\d\s()-]{8,}\d", text)})
    if not emails and not tgs:
        return
    if emails:
        domain = emails[0].split("@")[1]
        key = emails[0] if domain in FREE_MAIL else domain
    else:
        key = tgs[0].lower()
    c = crew["companies"].setdefault(key, {"emails": [], "telegram": [], "phones": [], "co": 0,
                                           "so": 0, "vessels": [], "last": "", "sources": []})
    for field, values in (("emails", emails), ("telegram", tgs), ("phones", phones), ("sources", [source])):
        c[field] = sorted(set(c[field]) | set(values))[:8]
    c["co"] += any(w in low for w in CO_WORDS)
    c["so"] += any(w in low for w in SO_WORDS)
    c["vessels"] = sorted(set(c["vessels"]) | {v for v, ws in VESSELS.items() if any(w in low for w in ws)})
    c["last"] = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d")


def send_crew_file(crew):
    """Присылает в чат таблицу крюингов (CSV — открывается в Excel и Google Таблицах)."""
    import csv, io
    rows = sorted(crew["companies"].items(), key=lambda kv: (kv[1]["co"], kv[1]["so"]), reverse=True)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Компания", "E-mail", "Telegram", "Телефон", "Вакансий Chief Officer",
                "Вакансий 2nd Officer", "Типы судов", "Последняя вакансия", "Где публикует"])
    for key, c in rows:
        w.writerow([key, ", ".join(c["emails"]), ", ".join(c["telegram"]), ", ".join(c["phones"]),
                    c["co"], c["so"], ", ".join(c["vessels"]), c["last"], ", ".join(c["sources"])])
    data = buf.getvalue().encode("utf-8-sig")
    name = f"crewings_{datetime.now(LOCAL_TZ):%Y-%m-%d}.csv"
    r = requests.post(f"https://api.telegram.org/bot{TOKEN}/sendDocument",
                      data={"chat_id": CHAT_ID, "caption": f"📇 Справочник крюингов: {len(rows)} компаний. "
                            "Сверху — кто чаще ищет Chief Officer."},
                      files={"document": (name, data, "text/csv")}, timeout=60)
    r.raise_for_status()
    return r.json()["result"]["message_id"]


def main():
    seen = load_seen() or set()
    crew = load_crew()
    if crew.get("file_msg"):
        KEEP_IDS.append(crew["file_msg"])
    day = load_day()
    today = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d")
    new_day = day["date"] != today
    if new_day:
        # Новый день: очищаем чат за прошлые дни и начинаем новый список
        day = {"date": today, "jobs": [], "msg_ids": [], "last_list": "",
               "cleared_upto": day.get("cleared_upto", 0), "force": True}

    # (ключ, подпись, функция, начало id вакансий этого источника)
    sources = [("crewell", "crewell.net", get_crewell, "crewell-"),
               ("ukrcrewing", "ukrcrewing.com.ua", get_ukrcrewing, "ukrcrewing-")]
    sources += [(n, n, lambda n=n: get_site(n), f"{n}-") for n in SITES]
    sources += [(f"tg:{c}", f"Telegram: @{c}", lambda c=c: get_channel(c), f"tg-{c}/")
                for c in CHANNELS]

    sent = 0
    report = []  # отчёт о новых источниках — придёт одним сообщением
    for key, label, fetch, prefix in sources:
        # Версия набора ключевых слов. При смене слов увеличиваем её — тогда
        # все источники подключаются заново и старые посты не присылаются разом.
        marker = f"source-v{KEYWORDS_VERSION}-" + key
        hw_old = [x for x in seen if x.startswith(f"hw|{key}|")]
        covered = f"cov|{key}|{today}" in seen
        if key.startswith("tg:") and covered and hw_old:
            STOP_AT[key[3:]] = int(hw_old[0].rsplit("|", 1)[1])
        try:
            jobs = fetch()
        except Exception as e:  # один сломавшийся источник не должен ломать остальные
            print(f"Ошибка в источнике {label}: {e}")
            if marker not in seen and "fail-" + key not in seen:
                report.append(f"❌ {label} — не открылся (сообщу об этом один раз)")
                seen.add("fail-" + key)
            continue
        print(f"{label}: найдено {len(jobs)}")

        is_channel = key.startswith("tg:")
        first_time = marker not in seen
        if first_time:
            was_connected = any(x.startswith("source-v") and x.endswith("-" + key) for x in seen)
            if not was_connected:
                report.append(f"✅ {label} — подходящих постов сейчас: {len(jobs)}")
            seen.add(marker)

        site_max = max([num(x) for x in seen if x.startswith(prefix)] or [0])
        day_urls = {j["url"] for j in day["jobs"]}
        day_fps = {j.get("fp") for j in day["jobs"] if j.get("fp")}
        for job in reversed(jobs):  # от старых к новым
            known = job["id"] in seen
            if is_channel:
                # У постов в каналах есть дата — берём всё, что опубликовано сегодня
                when = datetime.fromisoformat(job["date"]) if job.get("date") else None
                if not when or when < today_start():
                    continue
            else:
                # У сайтов даты нет — «сегодняшняя» = впервые увидели сегодня.
                # При первом подключении сайта его старые вакансии не берём.
                if first_time and not was_connected:
                    continue
                if known and job["id"] not in day.get("today_ids", []):
                    continue
                if not known and key in SEQUENTIAL and num(job["id"]) <= site_max:
                    continue  # старая вакансия, которую сайт снова показал — не сегодняшняя
                when = datetime.now(timezone.utc)
            fp = job.get("fp")
            if job["url"] in day_urls or (fp and fp in day_fps):
                continue  # уже в списке (или точная копия из другого канала)
            if not known and fp and fp in seen:
                continue  # точная копия поста, который был раньше
            day["jobs"].append({
                "title": short(job["title"]), "url": job["url"], "source": label,
                "found": job.get("found") or [], "fp": fp,
                "offshore": is_offshore(job["title"] + " " + job["url"].replace("-", " ")),
                "new": not known,
                "time": when.astimezone(timezone.utc).isoformat(),
            })
            day_urls.add(job["url"])
            if fp:
                day_fps.add(fp)
            if not known:
                sent += 1
            if is_channel and (not known or crew.get("backfill")):
                add_crewing(crew, job["title"], label.replace("Telegram: ", ""))
        seen.update(j["id"] for j in jobs)
        seen.update(j["fp"] for j in jobs if j.get("fp"))
        # Запоминаем самый новый пост и то, что сегодня канал уже прочитан целиком
        top = max([LAST_POST.get(key, 0)] + [num(j["id"]) for j in jobs]
                  + [int(x.rsplit("|", 1)[1]) for x in hw_old])
        seen.difference_update(hw_old)
        seen.add(f"hw|{key}|{top}")
        seen.difference_update({x for x in seen if x.startswith(f"cov|{key}|")})
        seen.add(f"cov|{key}|{today}")


    # Список обновляем раз в 45 минут, и только если появились новые вакансии
    has_new = any(j["new"] for j in day["jobs"])
    last = datetime.fromisoformat(day["last_list"]) if day["last_list"] else None
    due = last is None or datetime.now(timezone.utc) - last >= LIST_EVERY - timedelta(minutes=10)
    if (has_new and due) or report or day.pop("force", False):
        publish(day, report)
        print("Список обновлён")

    now = datetime.now(LOCAL_TZ)
    this_week = now.strftime("%G-%V")
    if (now.weekday() == 0 and now.hour >= 9 and crew["last_file"] != this_week
            and crew["companies"]) or crew.pop("send_now", False):
        try:
            crew["file_msg"] = send_crew_file(crew)
            crew["last_file"] = this_week
        except Exception as e:
            print(f"Не удалось отправить справочник: {e}")
    crew.pop("backfill", None)
    CREW_FILE.write_text(json.dumps(crew, ensure_ascii=False, indent=0))

    if LAST_SENT:
        day["last_msg_id"] = LAST_SENT
    save_day(day)
    save_seen(seen)
    print(f"Новых вакансий: {sent}")


if __name__ == "__main__":
    main()
