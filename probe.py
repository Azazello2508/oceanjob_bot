import os
os.environ.setdefault("TELEGRAM_TOKEN", "x"); os.environ.setdefault("TELEGRAM_CHAT_ID", "1")
import bot
for n in ["findseajobs.com", "marine-zone.com", "ojcrew.com", "deltamarinecrewing.nl", "kuokmaritime.com"]:
    try:
        jobs = bot.get_site(n)
        print(f"### {n}: {len(jobs)}  junior DP: {sum(bot.is_junior_dp(j['title']) for j in jobs)}")
        for j in ([x for x in jobs if bot.is_junior_dp(x['title'])][:4] + jobs[:6]):
            print("   ", j["id"][:40], "|", j["title"][:95])
    except Exception as e:
        print(f"### {n}: ERROR {e}")
