import re, collections, requests
from bs4 import BeautifulSoup
H = {"User-Agent": "Mozilla/5.0 (oceanjob_bot; personal job alerts)"}
URLS = """https://atlasprofessionals.com/jobs
https://atlasprofessionals.com/marine
https://careers.vanoord.com/vacancies
https://careers.boskalis.com/vacancies
https://bourbon-career.talent-soft.com/job/list-of-jobs.aspx
https://dof.com/vacancies
https://esvagt.easycruit.com/
https://esvagt.com/career/list-of-jobs/
https://www.solstad.com/opportunities
https://ipspowerfulpeople.com/vacancies
https://kuokmaritimegroup.teamtailor.com/jobs
https://www.airswift.com/candidates/maritime-jobs
https://www.allseas.com/en/careers/offshore
https://www.spinnaker-global.com/jobs
https://www.halcyonrecruitment.com/jobs
https://www.tdw.com/careers/
https://www.jandenul.com/jobs
https://www.deme-group.com/jobs
https://www.islandoffshore.com/careers
https://www.sea1offshore.com/careers
https://www.vroon.nl/careers
https://www.maersksupplyservice.com/careers
https://www.eddawind.com/careers
https://www.seamariner.com/jobs
https://www.selectoffshore.com/jobs
https://www.energyjobline.com/jobs?keywords=DPO
https://www.nesfircroft.com/jobs?keywords=DPO
https://www.worldwide-rs.com/jobs
https://www.subsea7.com/en/careers.html
https://www.acta-marine.com/careers
https://www.bibbymarine.com/careers
https://www.havila.no/en/career
https://jooble.org/jobs-dpo-offshore
https://www.rem-offshore.no/careers
https://www.olympic.no/careers
https://www.ostensjo.no/careers""".split()
KW = re.compile(r"officer|mate|dpo|master|engineer|seaman|deck|vacanc|job|crew|captain", re.I)
for u in URLS:
    try:
        r = requests.get(u, headers=H, timeout=25)
    except Exception as e:
        print(f"\n### {u}\n  ERROR {type(e).__name__}"); continue
    soup = BeautifulSoup(r.text, "html.parser")
    links = soup.find_all("a", href=True)
    shapes, ex = collections.Counter(), {}
    for a in links:
        t = a.get_text(" ", strip=True)[:70]
        h = a["href"]
        s = re.sub(r"\d+", "N", re.sub(r"[?#].*", "", h))
        s = re.sub(r"/[a-z0-9]+(?:-[a-z0-9]+){2,}", "/SLUG", s, flags=re.I)[:70]
        shapes[s] += 1
        if KW.search(t) and len(ex.setdefault(s, [])) < 3:
            ex[s].append((t, h[:110]))
    print(f"\n### {u}\n  status {r.status_code} final {r.url[:90]} bytes {len(r.text)} links {len(links)}")
    for s, n in shapes.most_common(40):
        if n >= 3 and s in ex:
            print(f"  {n:3d} x {s}")
            for t, h in ex[s]:
                print(f"        {t!r} -> {h}")
