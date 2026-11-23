import os, re, time
os.environ.setdefault("TELEGRAM_TOKEN", "x"); os.environ.setdefault("TELEGRAM_CHAT_ID", "1")
import bot, requests
from bs4 import BeautifulSoup
Q = ['"Dynamic Positioning Officer"', '"Dynamic Positioning Operator"', '"DPO" offshore vessel', 'DPO PSV', '"Second Officer" DPO',
     '"2nd Officer" offshore', '"Second Officer" offshore', '"Chief Officer" offshore vessel', '"Chief Mate" offshore',
     '"Junior DPO"', '"Trainee DPO"', '"DP Trainee"', 'deck officer DP vessel offshore', '"Second Mate" DP', '"Chief Mate"', '"Second Officer" vessel']
seen = set()
for q in Q:
    got, good = 0, []
    for start in (0, 10, 20):
        r = requests.get(bot.LINKEDIN_URL, headers=bot.HEADERS, timeout=30, params={"keywords": q, "location": "Worldwide", "geoId": "92000000", "f_TPR": "r604800", "sortBy": "DD", "start": start})
        if r.status_code != 200:
            print("   status", r.status_code); break
        cards = [c for c in BeautifulSoup(r.text, "html.parser").find_all("li") if c.find("a", href=re.compile(r"/jobs/view/"))]
        got += len(cards)
        for c in cards:
            h3, h4 = c.find("h3"), c.find("h4"); a = c.find("a", href=re.compile(r"/jobs/view/"))
            t = h3.get_text(" ", strip=True) if h3 else ""; co = h4.get_text(" ", strip=True) if h4 else ""
            m = re.search(r"(\d+)(?:\?|$)", a["href"]); i = m.group(1) if m else t
            if re.search(r"\bofficer\b|\bmate\b|\bdpo\b|dynamic pos|\bmaster\b", t, re.I) and not bot.LINKEDIN_SKIP_RE.search(t + " " + co) and bot.wanted(t):
                good.append((i in seen, t[:55], co[:25])); seen.add(i)
        time.sleep(2)
        if len(cards) < 10: break
    print(f"### {q}: cards {got}, wanted-title {len(good)}, new {sum(not g[0] for g in good)}")
    for g in [x for x in good if not x[0]][:7]:
        print("     +", g[1], "|", g[2])
print("### unique wanted:", len(seen))
