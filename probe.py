import os, re, json
os.environ.setdefault("TELEGRAM_TOKEN", "x"); os.environ.setdefault("TELEGRAM_CHAT_ID", "1")
import bot, requests
from bs4 import BeautifulSoup
tot = 0
for q in bot.LINKEDIN_QUERIES:
    r = requests.get(bot.LINKEDIN_URL, headers=bot.HEADERS, timeout=30, params={"keywords": q, "location": "Worldwide", "geoId": "92000000", "f_TPR": "r86400", "start": 0})
    cards = [c for c in BeautifulSoup(r.text, "html.parser").find_all("li") if c.find("a", href=re.compile(r"/jobs/view/"))]
    tot += len(cards)
    print(f"### query {q!r}: status {r.status_code}, cards {len(cards)}")
    for c in cards[:4]:
        h3 = c.find("h3"); h4 = c.find("h4")
        print("     raw:", (h3.get_text(' ', strip=True) if h3 else '?')[:60], "|", (h4.get_text(' ', strip=True) if h4 else '?')[:30])
    bot.time.sleep(2)
bot.LINKEDIN_DEEP_PER_RUN = 25
jobs = bot.get_linkedin()
print(f"### RESULT after filter: {len(jobs)} of {tot} cards")
for j in jobs: print("     keep:", j["title"][:110])
print("### kinds:", json.load(open("linkedin_checked.json")).get("kind"))
