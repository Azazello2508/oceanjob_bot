import re, collections, requests
from bs4 import BeautifulSoup
H = {"User-Agent": "Mozilla/5.0 (oceanjob_bot; personal job alerts)"}
URLS = """https://www.atlasprofessionals.com/jobs
https://www.atlasprofessionals.com/marine
http://jobs.atlasprofessionals.com
https://careers.vanoord.com/vacancies?n=100
https://bourbon-career.talent-soft.com/job/list-of-all-jobs.aspx?all=1&mode=layer
https://ipspowerfulpeople.com/vacancies/expertises-renewables-offshore/
https://ipspowerfulpeople.com/vacancies/expertises-towage/
https://www.halcyonrecruitment.com/vacancies/vacancy-search-results.aspx
https://www.allseas.com/en/careers
https://www.selectoffshore.com/job-search/
https://jobs.worldwide-rs.com/jobs/?keywords=vessel
https://www.worldwide-rs.com/our-industries/offshore-and-maritime/
https://maersksupplyservice.com
https://eddawind.com
https://www.tdw.com
https://www.sea1offshore.com
https://www.islandoffshore.com
https://www.vroon.nl
https://www.havila.no
https://www.jandenul.com
https://www.olympic.no
https://ostensjo.no
https://www.bibbymarine.com
https://www.solstad.com/opportunities
https://www.dof.com/vacancies
https://spinnaker-global.com/jobseekers/
https://esvagt.com/career/list-of-jobs/""".split()
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
    seen_c = set()
    for a in links:
        h = a["href"]
        if re.search(r"career|vacanc|job|join|karriere|stilling|recruit|easycruit|teamtailor|workday|talent|hr-manager|webcruiter|jobylon|reachmee", h, re.I) and h not in seen_c and len(seen_c) < 8:
            seen_c.add(h); print("  C:", a.get_text(" ", strip=True)[:40], "->", h[:120])
    for m in set(re.findall(r"https?://[\w.-]*(?:easycruit|teamtailor|workday|talent-soft|hr-manager|webcruiter|jobylon|reachmee|recman|varbi|successfactors|avature|smartrecruiters|greenhouse|lever)[\w./-]*", r.text))[:5] if False else list(set(re.findall(r"https?://[\w.-]*(?:easycruit|teamtailor|workday|talent-soft|hr-manager|webcruiter|jobylon|reachmee|recman|varbi|successfactors|avature|smartrecruiters)[\w./?=&-]*", r.text)))[:5]:
        print("  ATS:", m[:140])
    for s, n in shapes.most_common(40):
        if n >= 3 and s in ex:
            print(f"  {n:3d} x {s}")
            for t, h in ex[s]:
                print(f"        {t!r} -> {h}")
