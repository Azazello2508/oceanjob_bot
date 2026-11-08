"""Справочник крюингов.

Откуда берутся компании:
  1. Посты во ВСЕХ Telegram-каналах (любые должности): контакты, название, типы судов,
     сколько вакансий всего / Chief Officer / 2nd Officer / оффшорных.
  2. Один раз — старые посты каналов (несколько недель назад).
  3. Каталоги работодателей на сайтах: crewell.net, ukrcrewing.com.ua, seajobs.ru.
     Каталоги обходятся понемногу при каждой проверке и обновляются раз в неделю.

Всё хранится в crewings.json, в Telegram уходит таблица Excel с двумя листами:
«Оффшор» (компании, которые набирают в оффшор) и «Все компании».

Каждый шаг защищён: ошибка на одном сайте или канале не ломает бота.
"""

import io
import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

CREW_FILE = Path("crewings.json")
CATALOG_EVERY = timedelta(days=7)      # как часто обновлять каталоги сайтов
FETCH_PAUSE = 0.7                       # пауза между запросами к сайтам, сек
BACKFILL_PAGES = 8                      # сколько страниц старых постов читать в канале (≈160 постов)

LEGAL = r"(?:LLC|L\.L\.C\.|Ltd\.?|LTD|Limited|Inc\.?|S\.A\.|SA|GmbH|AS|A/S|B\.V\.|BV|SRL|S\.R\.L\.|Co\.|Corp\.?|PLC|Pte\.? Ltd|JSC|LLP)"
COMPANY_RE = [
    re.compile(r"\b([A-Z][A-Za-z0-9&.'\- ]{1,45}?\s" + LEGAL + r")(?=[\s,.;:)!]|$)"),
    re.compile(r"((?:ООО|АО|ПАО|ЗАО|ТОВ|ПП)\s*[«\"“][^»\"”]{2,40}[»\"”])"),
    re.compile(r"\b([A-Z][A-Za-z0-9&.'\-]+(?:\s[A-Z][A-Za-z0-9&.'\-]+){0,3}\s(?:Crewing|Crew Management|Crew Services|"
               r"Shipping|Shipmanagement|Ship Management|Maritime|Marine|Manning)(?:\s(?:Agency|Services|Company|Group))?)\b"),
]
VACANCY_WORDS = ["vacanc", "ваканс", "hiring", "required", "requirement", "требуется", "требуются", "join",
                 "officer", "engineer", "master", "капитан", "механик", "помощник", "bosun", "боцман", "a/b",
                 "able seaman", "matros", "матрос", "oiler", "моторист", "cook", "кок", "eto", "электромеханик",
                 "dpo", "crew", "экипаж", "salary", "зарплата", "contract", "контракт"]
JUNK_HANDLES = {"gmail", "mail", "yahoo", "hotmail", "outlook", "telegram", "whatsapp", "viber", "admin", "support"}


# ---------------- хранение ----------------

def load():
    if CREW_FILE.exists():
        crew = json.loads(CREW_FILE.read_text(encoding="utf-8"))
    else:
        crew = {}
    if crew.get("version") != 2:          # переход со старого формата: переносим, что было
        old = crew.get("companies", {})
        crew = {"version": 2, "companies": {}, "names": {}, "tg_hw": {}, "catalog": {},
                "queue": [], "backfill_left": None, "last_file": crew.get("last_file", ""),
                "file_msg": crew.get("file_msg")}
        for key, c in old.items():
            if "@" in key:
                rec = company(crew, free_mail=key)
            elif "." in key:
                rec = company(crew, domain=key)
            else:
                rec = company(crew, name=key)
            if rec is None:
                continue
            mine = norm_domain(key) if "@" not in key else None
            for e in c.get("emails", []):       # чужие адреса из постов-подборок — в свои компании
                d = norm_domain(e)
                if mine and d and d != mine and "." in d and d.split(".")[0] not in ("gmail", "mail", "yahoo",
                                                                                      "hotmail", "outlook", "ukr"):
                    add_list(company(crew, domain=d), "emails", [e])
                else:
                    add_list(rec, "emails", [e])
            for f in ("telegram", "phones", "vessels", "sources"):
                rec[f] = sorted(set(rec[f]) | set(c.get(f, [])))
            rec["co"] += c.get("co", 0)
            rec["so"] += c.get("so", 0)
            rec["total"] = max(rec["total"], rec["co"] + rec["so"])
            rec["last"] = max(rec["last"], c.get("last", ""))
    return crew


def save(crew):
    CREW_FILE.write_text(json.dumps(crew, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")


def norm_domain(url_or_mail):
    s = (url_or_mail or "").strip().lower()
    if "@" in s:
        s = s.split("@", 1)[1]
    if not s:
        return None
    if "//" not in s:
        s = "http://" + s
    host = urlparse(s).netloc.split(":")[0]
    host = host[4:] if host.startswith("www.") else host
    return host if "." in host else None


def norm_name(name):
    n = (name or "").lower()
    n = re.sub(r"[«»\"“”'`.,()]", " ", n)
    n = re.sub(r"\b(llc|ltd|limited|inc|sa|gmbh|as|a/s|bv|srl|co|corp|plc|pte|jsc|llp|ооо|ао|пао|зао|тов|пп|"
               r"company|the)\b", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def company(crew, domain=None, name=None, free_mail=None):
    """Находит компанию по домену или названию, а если её нет — создаёт."""
    comps, names = crew["companies"], crew["names"]
    key = None
    if domain:
        key = domain
    elif free_mail:
        key = free_mail
    nn = norm_name(name)
    if not key and nn:
        key = names.get(nn) or "name:" + nn
    if not key:
        return None
    old = names.get(nn) if nn else None
    if key not in comps and old and old in comps:
        if domain and old.startswith("name:"):
            comps[key] = comps.pop(old)      # раньше знали только название — теперь знаем домен
            for n, k in list(names.items()):
                if k == old:
                    names[n] = key
        else:
            key = old                       # то же название, но раньше записано под другим ключом
    today = datetime.now(timezone(timedelta(hours=4))).strftime("%Y-%m-%d")
    rec = comps.setdefault(key, {"name": "", "country": "", "city": "", "address": "", "website": "",
                                 "emails": [], "telegram": [], "phones": [], "vessels": [], "sources": [],
                                 "links": {}, "total": 0, "co": 0, "so": 0, "off": 0,
                                 "offshore_hint": False, "first": today, "last": ""})
    if name and not rec["name"]:
        rec["name"] = name.strip()[:60]
    if nn:
        names.setdefault(nn, key)
    return rec


def add_list(rec, field, values, limit=8):
    rec[field] = sorted(set(rec[field]) | {v for v in values if v})[:limit]


# ---------------- 1. посты в каналах ----------------

def company_name_from(text):
    for rx in COMPANY_RE:
        m = rx.search(text)
        if m:
            name = re.sub(r"\s+", " ", m.group(1)).strip(" -.,")
            if 3 <= len(name) <= 60 and not re.match(r"(?i)(we|our|the|for|on|in|at)\s", name):
                return name
    return None


def from_post(bot, crew, text, source, count=True):
    """Разбирает пост. Если в нём контакты нескольких компаний (подборка вакансий) —
    делит его на части, и каждая компания получает только свою вакансию."""
    doms = {d.lower().rstrip(".") for d in re.findall(r"[\w.+-]+@([\w-]+\.[\w.-]+)", text)
            if d.lower().rstrip(".") not in bot.FREE_MAIL}
    if len(doms) <= 1:
        return _from_post(bot, crew, text, source, count)
    buf = ""
    for seg in re.split(r"\n\s*\n|\n?[-—_=•~*]{5,}\n?", text):
        buf += "\n" + seg
        if re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+|(?<![\w.@])@\w{4,}", seg):
            _from_post(bot, crew, buf, source, count)
            buf = ""


def _from_post(bot, crew, text, source, count=True):
    """count=False: пост уже учтён раньше, нужно только отметить UK Work Permit."""
    low = text.lower()
    uk = bool(bot.uk_permit(text))
    if not any(w in low for w in VACANCY_WORDS) or (not count and not uk):
        return
    emails = sorted({e.lower().rstrip(".") for e in re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)})
    channels = {c.lower() for c in bot.CHANNELS}
    tgs = sorted({"@" + h for h in re.findall(r"(?<![\w.@])@(\w{4,})", text)
                  if h.lower() not in channels and not h.lower().endswith("bot") and h.lower() not in JUNK_HANDLES})
    phones = sorted({re.sub(r"[^\d+]", "", p) for p in re.findall(r"\+\d[\d\s()-]{8,}\d", text)})
    sites = sorted({norm_domain(u) for u in re.findall(r"(?:https?://|www\.)[\w.-]+\.[a-z]{2,}", text, re.I)
                    if norm_domain(u) and "t.me" not in u and "telegram" not in u})
    name = company_name_from(text)
    if not (emails or tgs or phones or name):
        return
    corp = [e for e in emails if e.split("@")[1] not in bot.FREE_MAIL]
    domain = norm_domain(corp[0]) if corp else (sites[0] if sites else None)
    rec = company(crew, domain=domain, name=name,
                  free_mail=None if domain or name else (emails[0] if emails else (tgs[0].lower() if tgs else None)))
    if rec is None:
        return
    add_list(rec, "emails", emails)
    add_list(rec, "telegram", tgs)
    add_list(rec, "phones", phones)
    add_list(rec, "sources", [source], 12)
    if domain and not rec["website"] and domain in sites:
        rec["website"] = domain
    if uk:
        rec["uk"] = rec.get("uk", 0) + 1
    if not count:
        return
    rec["total"] += 1
    rec["co"] += any(w in low for w in bot.CO_WORDS)
    rec["so"] += any(w in low for w in bot.SO_WORDS)
    if bot.is_offshore(text):
        rec["off"] += 1
    add_list(rec, "vessels", [v for v, ws in bot.VESSELS.items() if any(w in low for w in ws)], 12)
    rec["last"] = max(rec["last"], datetime.now(timezone(timedelta(hours=4))).strftime("%Y-%m-%d"))


def from_channels(bot, crew, posts_by_channel):
    """Новые посты, которые бот прочитал в каналах при этой проверке."""
    low = crew.setdefault("tg_low", {})
    for ch, posts in posts_by_channel.items():
        hw = crew["tg_hw"].get(ch, 0)
        if not hw and posts:                # первый раз: запоминаем, откуда начали (для разбора старых постов)
            low[ch] = min(n for n, _ in posts)
        top = hw
        for num, text in posts:
            if num > hw:
                try:
                    from_post(bot, crew, text, "@" + ch)
                except Exception as e:
                    print(f"Справочник: не разобрал пост @{ch}/{num}: {e}")
            top = max(top, num)
        crew["tg_hw"][ch] = top


# ---------------- 2. старые посты (один раз) ----------------

def backfill(bot, crew, deadline, field="backfill_left", uk_only=False):
    """uk_only=True — разовый второй проход по истории каналов: ищет только UK Work Permit."""
    if crew.get(field) is None:
        crew[field] = list(bot.CHANNELS)
    cut = crew.get("uk_cut", {})
    while crew[field] and time.time() < deadline:
        ch = crew[field].pop(0)
        url = f"https://t.me/s/{ch}"
        try:
            for _ in range(BACKFILL_PAGES):
                page = bot.BeautifulSoup(bot.requests.get(url, headers=bot.HEADERS, timeout=30).text, "html.parser")
                msgs = page.select("div.tgme_widget_message[data-post]")
                if not msgs:
                    break
                for m in msgs:
                    box = m.select_one("div.tgme_widget_message_text")
                    n = bot.num(m["data-post"])
                    if uk_only:
                        if n > cut.get(ch, 0):
                            continue        # свежие посты и так разбирает обычная проверка
                    elif ch in crew.get("tg_low", {}) and n >= crew["tg_low"][ch]:
                        continue            # этот пост уже учтён при обычной проверке
                    if box:
                        text = box.get_text("\n", strip=True)
                        if uk_only and not bot.uk_permit(text):
                            continue
                        from_post(bot, crew, text, "@" + ch, count=not uk_only)
                url = f"https://t.me/s/{ch}?before={min(bot.num(m['data-post']) for m in msgs)}"
                time.sleep(FETCH_PAUSE)
        except Exception as e:
            print(f"Справочник: старые посты @{ch} не прочитал: {e}")
    if not crew[field]:
        crew[field] = []                  # готово, больше не повторяем


# ---------------- 3. каталоги сайтов ----------------

def _txt(el):
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)) if el else ""


def crewell_list(bot, crew, url, soup):
    for a in soup.find_all("a", href=re.compile(r"/en/companies/\d+/?$")):
        name = a.get_text(" ", strip=True)
        if not name or name.lower().startswith("details"):
            continue
        card = a.find_parent(["tr", "li", "div"])
        while card is not None and "Country:" not in card.get_text():
            card = card.find_parent(["tr", "li", "div"])
        text = _txt(card)
        site = next((x for x in re.findall(r"https?://[^\s|]+", text) if "crewell" not in x), "")
        rec = company(crew, domain=norm_domain(site) if site else None, name=name)
        if rec is None:
            continue
        m = re.search(r"Country:\s*([^|:]+?)\s+City:\s*([^|:]+?)\s+(?:Address:|http|Recent|$)", text)
        if m:
            rec["country"] = rec["country"] or m.group(1).strip()
            rec["city"] = rec["city"] or m.group(2).strip()
        m = re.search(r"Address:\s*(.+?)\s+(?:https?://|Recent vacancies|\d+ registered|$)", text)
        if m and not rec["address"]:
            rec["address"] = m.group(1).strip()[:80]
        if site and not rec["website"]:
            rec["website"] = norm_domain(site) or ""
        rec["links"]["crewell"] = "https://crewell.net" + a["href"] if a["href"].startswith("/") else a["href"]
        add_list(rec, "sources", ["crewell.net"], 12)
        if "Recent vacancies" in text and bot.is_offshore(text.split("Recent vacancies", 1)[1]):
            rec["offshore_hint"] = True
        if "Recent vacancies" in text and bot.uk_permit(text.split("Recent vacancies", 1)[1]):
            rec["uk_hint"] = True
    if "page=" not in url:                  # первая страница: ставим в очередь остальные
        pages = [int(x) for x in re.findall(r"/en/companies/\?page=(\d+)", str(soup))]
        crew["queue"] += [f"https://crewell.net/en/companies/?page={p}" for p in range(2, max(pages or [1]) + 1)]


def ukr_list(bot, crew, url, soup):
    seen_here = set()
    for a in soup.find_all("a", href=re.compile(r"/en/agency/[\w-]+/?$")):
        slug = a["href"].rstrip("/").split("/")[-1]
        name = a.get_text(" ", strip=True)
        if re.fullmatch(r"p\d+", slug) or slug in seen_here or not name or "vacanc" in name.lower():
            continue
        seen_here.add(slug)
        card = a.find_parent(["tr", "li", "div"])
        parts = [p.strip() for p in card.get_text("|", strip=True).split("|")] if card else []
        rec = company(crew, name=name)
        if rec is None:
            continue
        if len(parts) >= 3 and not rec["country"]:
            rec["country"], rec["city"] = parts[1], parts[2] if not parts[2].endswith(("vacancy", "vacancies")) else ""
        link = "https://ukrcrewing.com.ua/en/agency/" + slug
        rec["links"]["ukrcrewing"] = link
        add_list(rec, "sources", ["ukrcrewing.com.ua"], 12)
        if not rec["emails"] or any("vacanc" in p for p in parts):
            crew["queue"].append(link)      # страница компании: телефон, почта, сайт, вакансии
    if not re.search(r"/p\d+/?$", url):
        pages = [int(x) for x in re.findall(r"/en/agency/p(\d+)/", str(soup))]
        crew["queue"] += [f"https://ukrcrewing.com.ua/en/agency/p{p}/" for p in range(2, max(pages or [1]) + 1)]


def ukr_company(bot, crew, url, soup):
    text = soup.get_text("\n", strip=True)
    name = _txt(soup.find("h1")) or (soup.title.get_text().split(",")[0] if soup.title else "")
    emails = sorted({e.lower() for e in re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", text.split("Back")[0])
                     if "ukrcrewing" not in e})
    site = ""
    m = re.search(r"Website:\s*\n?\s*(\S+)", text)
    if m and "advert" not in m.group(1).lower():
        site = m.group(1)
    corp = [e for e in emails if e.split("@")[1] not in bot.FREE_MAIL]
    domain = norm_domain(site) or (norm_domain(corp[0]) if corp else None)
    rec = company(crew, domain=domain, name=name)
    if rec is None:
        return
    add_list(rec, "emails", emails)
    m = re.search(r"Phone number:\s*\n?\s*([+\d][\d\s()+-]{6,})", text)
    if m:
        add_list(rec, "phones", [re.sub(r"[^\d+]", "", m.group(1))])
    m = re.search(r"Address:\s*\n?\s*([^\n]{3,80})", text)
    if m and not rec["address"]:
        rec["address"] = m.group(1).strip()
    if domain and not rec["website"]:
        rec["website"] = domain
    add_list(rec, "telegram", ["@" + h for h in re.findall(r"t\.me/(\w{4,})", text) if h.lower() != "ukrcrewing_official"])
    rec["links"]["ukrcrewing"] = url
    add_list(rec, "sources", ["ukrcrewing.com.ua"], 12)
    vac = text.split("Company vacancies", 1)[1][:3000] if "Company vacancies" in text else ""
    if vac and bot.is_offshore(vac):
        rec["offshore_hint"] = True
    if vac and bot.uk_permit(vac):
        rec["uk_hint"] = True


def seajobs_list(bot, crew, url, soup):
    for a in soup.find_all("a", href=re.compile(r"/en/company/\d+/")):
        card = a.find_parent(["div", "li", "article"])
        while card is not None and "Member since" not in card.get_text():
            card = card.find_parent(["div", "li", "article"])
        if card is None:
            continue
        name = a.get_text(" ", strip=True)
        if not name or name.lower().startswith("view"):
            continue
        text = _txt(card)
        rec = company(crew, name=name)
        if rec is None:
            continue
        m = re.search(r"(?:ago|\d{2}\.\d{2}\.\d{4})\s+(.+?)\s+Member since", text)
        if m and not rec["country"]:
            rec["country"] = m.group(1).strip()[:40]
        rec["links"]["seajobs"] = a["href"]
        add_list(rec, "sources", ["seajobs.ru"], 12)
    if "page=" not in url or url.endswith("page=1"):
        pages = [int(x) for x in re.findall(r"/en/companies\?page=(\d+)", str(soup))]
        crew["queue"] += [f"https://seajobs.ru/en/companies?page={p}" for p in range(2, max(pages or [1]) + 1)]


PARSERS = [
    (re.compile(r"crewell\.net/en/companies/(\?page=\d+)?$"), crewell_list),
    (re.compile(r"ukrcrewing\.com\.ua/en/agency(/p\d+)?/?$"), ukr_list),
    (re.compile(r"ukrcrewing\.com\.ua/en/agency/[\w-]+$"), ukr_company),
    (re.compile(r"seajobs\.ru/en/companies(\?page=\d+)?$"), seajobs_list),
]
CATALOG_START = ["https://crewell.net/en/companies/", "https://ukrcrewing.com.ua/en/agency",
                 "https://seajobs.ru/en/companies?page=1"]


def catalogs(bot, crew, deadline):
    now = datetime.now(timezone.utc)
    last = crew["catalog"].get("started")
    if not crew["queue"] and (not last or now - datetime.fromisoformat(last) >= CATALOG_EVERY):
        crew["queue"] = list(CATALOG_START)            # раз в неделю — обход каталогов заново
        crew["catalog"]["started"] = now.isoformat()
    done = 0
    while crew["queue"] and time.time() < deadline:
        url = crew["queue"].pop(0)
        if url in crew["queue"]:
            continue
        try:
            r = bot.requests.get(url, headers=bot.HEADERS, timeout=30)
            soup = bot.BeautifulSoup(r.text, "html.parser")
            for rx, fn in PARSERS:
                if rx.search(url):
                    fn(bot, crew, url, soup)
                    break
            done += 1
        except Exception as e:
            print(f"Справочник: не открылась {url}: {e}")
        time.sleep(FETCH_PAUSE)
    if done:
        print(f"Справочник: страниц каталогов обработано {done}, в очереди {len(crew['queue'])}")
    if not crew["queue"] and crew["catalog"].get("started") and \
            crew["catalog"].get("finished_for") != crew["catalog"]["started"]:
        crew["catalog"]["finished_for"] = crew["catalog"]["started"]
        if not crew["catalog"].get("first_sent"):     # первый полный обход — сразу присылаем файл
            crew["catalog"]["first_sent"] = True
            crew["send_now"] = True


def update(bot, crew, posts_by_channel, seconds=240):
    """Всё обновление справочника за одну проверку (ограничено по времени)."""
    deadline = time.time() + seconds
    if "uk_cut" not in crew:      # граница для разового UK-прохода по истории: что новее — разберёт обычная проверка
        crew["uk_cut"] = dict(crew["tg_hw"])
    for step in (lambda: from_channels(bot, crew, posts_by_channel),
                 lambda: backfill(bot, crew, deadline),
                 lambda: backfill(bot, crew, deadline, "uk_backfill_left", uk_only=True),
                 lambda: catalogs(bot, crew, deadline)):
        try:
            step()
        except Exception as e:
            print(f"Справочник: ошибка шага: {e}")


# ---------------- выгрузка в Excel ----------------

def is_offshore_company(c):
    return c["off"] > 0 or c.get("offshore_hint")


def is_uk_company(c):
    return c.get("uk", 0) > 0 or c.get("uk_hint")


def to_xlsx(crew):
    try:
        import openpyxl  # noqa: F401
    except ImportError:                     # на случай, если библиотека ещё не установлена
        import subprocess
        import sys
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "openpyxl"], check=False)
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    cols = ["Компания", "Оффшор-вакансий", "Вакансий с UK Work Permit", "Вакансий Chief Officer", "Вакансий 2nd Officer", "Всего вакансий (TG)",
            "Последняя вакансия", "Страна", "Город", "Сайт", "E-mail", "Telegram", "Телефон", "Типы судов",
            "Где публикует", "Профиль на сайте", "В справочнике с"]
    widths = [32, 10, 12, 10, 10, 10, 12, 14, 14, 24, 34, 22, 18, 26, 30, 40, 12]

    def row(key, c):
        name = c["name"] or (key if not key.startswith("name:") else key[5:].title())
        site = c["website"] or (key if "." in key and "@" not in key and not key.startswith("name:") else "")
        return [name, c["off"] or ("да" if c.get("offshore_hint") else 0),
                c.get("uk") or ("да" if c.get("uk_hint") else 0), c["co"], c["so"], c["total"], c["last"],
                c["country"], c["city"], site, ", ".join(c["emails"]), ", ".join(c["telegram"]),
                ", ".join(c["phones"]), ", ".join(c["vessels"]), ", ".join(c["sources"]),
                " ".join(c["links"].values()), c["first"]]

    def order(kv):
        c = kv[1]
        return (-(c["off"] + (1 if c.get("offshore_hint") else 0)), -c["co"], -c["total"], -(len(c["emails"]) > 0),
                kv[0])

    def uk_order(kv):
        c = kv[1]
        return (-(c.get("uk", 0) + (1 if c.get("uk_hint") else 0)),) + order(kv)

    items = sorted(crew["companies"].items(), key=order)
    wb = Workbook()
    head_fill = PatternFill("solid", fgColor="1F4E78")
    off_fill = PatternFill("solid", fgColor="DDEBF7")
    uk_fill = PatternFill("solid", fgColor="FFF2CC")
    sheets = [("Оффшор", [kv for kv in items if is_offshore_company(kv[1])]),
              ("UK Work Permit", sorted([kv for kv in items if is_uk_company(kv[1])], key=uk_order)),
              ("Все компании", items)]
    for idx, (title, rows) in enumerate(sheets):
        ws = wb.active if idx == 0 else wb.create_sheet()
        ws.title = title
        ws.append(cols)
        for cell in ws[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = head_fill
            cell.alignment = Alignment(wrap_text=True, vertical="center")
        for key, c in rows:
            ws.append(row(key, c))
            if title == "Все компании" and (is_uk_company(c) or is_offshore_company(c)):
                for cell in ws[ws.max_row]:
                    cell.fill = uk_fill if is_uk_company(c) else off_fill
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = w
        ws.freeze_panes = "B2"
        ws.auto_filter.ref = ws.dimensions
        ws.row_dimensions[1].height = 32
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue(), len(sheets[0][1]), len(items), len(sheets[1][1])


def send_file(bot, crew):
    data, n_off, n_all, n_uk = to_xlsx(crew)
    name = f"crewings_{datetime.now(bot.LOCAL_TZ):%Y-%m-%d}.xlsx"
    caption = (f"📇 Справочник крюингов: {n_all} компаний, из них набирают в оффшор: {n_off}, "
               f"упоминают UK Work Permit: {n_uk}.\n"
               "Листы «Оффшор» и «UK Work Permit» — отдельные подборки. На листе «Все компании» "
               "оффшор выделен голубым, UK Work Permit — жёлтым.")
    r = bot.requests.post(f"https://api.telegram.org/bot{bot.TOKEN}/sendDocument",
                          data={"chat_id": bot.CHAT_ID, "caption": caption},
                          files={"document": (name, data,
                                              "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                          timeout=60)
    r.raise_for_status()
    return r.json()["result"]["message_id"]
