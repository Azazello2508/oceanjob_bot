import re, collections, requests
from bs4 import BeautifulSoup
H = {"User-Agent": "Mozilla/5.0 (oceanjob_bot; personal job alerts)"}
URLS = """https://balticcareer.eu
https://balticcareer.eu/vacancies
https://balticcareer.eu/vacancies/
https://balticcareer.eu/jobs
https://balticcareer.eu/en/vacancies""".split()
KW = re.compile(r"officer|mate|dpo|master|seaman|trainee|vacanc|job", re.I)
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
    if "findseajobs.com/seajobs/" in u and u.endswith("/seajobs/"):
        cats = {}
        for a in links:
            m = re.search(r"/seajobs/(\d+)/$", a["href"]); t = a.get_text(" ", strip=True)
            if m and re.search(r"officer|dpo|mate|dp |trainee|master", t, re.I): cats[m.group(1)] = t[:40]
        print("  CATS:", cats)
        print("  TAGS:", sorted({a["href"] for a in links if "/tags/" in a["href"]})[:40])
    seen_c = set()
    for a in links:
        h = a["href"]
        if re.search(r"career|vacanc|job|join|karriere|stilling|recruit|easycruit|teamtailor|workday|talent|hr-manager|webcruiter|jobylon|reachmee", h, re.I) and h not in seen_c and len(seen_c) < 3:
            seen_c.add(h); print("  C:", a.get_text(" ", strip=True)[:40], "->", h[:120])
    for m in set(re.findall(r"https?://[\w.-]*(?:easycruit|teamtailor|workday|talent-soft|hr-manager|webcruiter|jobylon|reachmee|recman|varbi|successfactors|avature|smartrecruiters|greenhouse|lever)[\w./-]*", r.text))[:5] if False else list(set(re.findall(r"https?://[\w.-]*(?:easycruit|teamtailor|workday|talent-soft|hr-manager|webcruiter|jobylon|reachmee|recman|varbi|successfactors|avature|smartrecruiters)[\w./?=&-]*", r.text)))[:5]:
        print("  ATS:", m[:140])
    for s, n in shapes.most_common(40):
        if n >= 2 and s in ex and not s.startswith("#"):
            print(f"  {n:3d} x {s}")
            for t, h in ex[s]:
                print(f"        {t!r} -> {h}")
