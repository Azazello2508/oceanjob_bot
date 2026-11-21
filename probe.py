import os
os.environ.setdefault("TELEGRAM_TOKEN", "x"); os.environ.setdefault("TELEGRAM_CHAT_ID", "1")
import bot
for n in ["vanoord.com", "bourbonoffshore.com", "kuokmaritime.com", "ipspowerfulpeople.com", "jandenul.com", "worldwide-rs.com"]:
    try:
        jobs = bot.get_site(n)
        print(f"### {n}: {len(jobs)}")
        for j in jobs[:8]:
            print("   ", j["title"][:80], "|", j["url"][:90])
    except Exception as e:
        print(f"### {n}: ERROR {e}")
