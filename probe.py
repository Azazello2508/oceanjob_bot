import os, re
os.environ.setdefault("TELEGRAM_TOKEN", "x"); os.environ.setdefault("TELEGRAM_CHAT_ID", "1")
import bot, requests
from datetime import datetime
for c in ["gm_seaman_cv", "maritimeforum", "cvsenderseaman", "offshoreatsea", "offshorecv", "seajobfinder"]:
    try:
        jobs = bot.get_channel(c)
        today = [j for j in jobs if j.get("date") and datetime.fromisoformat(j["date"]) >= bot.today_start()]
        uk = [j for j in jobs if bot.uk_permit(j["title"])]
        raw = requests.get(f"https://t.me/s/{c}", headers=bot.HEADERS, timeout=20).text
        n_raw = len(re.findall(r"UK (?:right to work|work permit)|right to work in (?:the )?UK", raw, re.I))
        print(f"### {c}: wanted posts {len(jobs)}, today {len(today)}, with UK permit {len(uk)} | raw page UK mentions {n_raw}")
        for j in uk[:3]:
            print("    ", (j.get("date") or "")[:16], "|", j["title"][:90].replace("\n", " "), "|", bot.uk_permit(j["title"])[:60])
    except Exception as e:
        print(f"### {c}: ERROR {type(e).__name__} {e}")
