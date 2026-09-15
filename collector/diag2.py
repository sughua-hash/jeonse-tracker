"""진단 2단계: 실제 단지(109266 위례센트럴자이)로 매물 API 후보들을 확인하고 data/diag2.json 업로드."""
from __future__ import annotations

import json
import re
import sys
import datetime as dt
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
import naver  # noqa: E402
import publish  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
NO = sys.argv[1] if len(sys.argv) > 1 else "109266"
M = {"User-Agent": naver.MOBILE_UA, "Accept": "*/*", "Accept-Language": "ko-KR,ko;q=0.9"}
P = {"User-Agent": naver.PC_UA, "Accept": "*/*", "Accept-Language": "ko-KR,ko;q=0.9"}
out = {"no": NO, "at": dt.datetime.now().isoformat(timespec="seconds"), "steps": []}
s = naver.make_session()


def step(name, url, headers, head=2500, extra=None):
    rec = {"name": name, "url": url}
    try:
        r = s.get(url, headers=headers, timeout=15)
        rec.update({"status": r.status_code, "final_url": r.url, "ctype": r.headers.get("content-type", ""), "len": len(r.text), "head": r.text[:head]})
        if extra:
            rec.update(extra(r.text))
    except Exception as e:  # noqa: BLE001
        rec["error"] = f"{type(e).__name__}: {e}"
    out["steps"].append(rec)
    print("[diag2]", name, rec.get("status", rec.get("error")), rec.get("len"))
    return rec


def api_paths(text):
    paths = re.findall(r"[\"'`](/(?:front-)?api/[A-Za-z0-9_\-/\.{}$]+)", text)
    full = re.findall(r"https?://[a-z0-9\.\-]*land\.naver\.com/[A-Za-z0-9_\-/\.{}$]*api[A-Za-z0-9_\-/\.{}$]*", text)
    keep = [p for p in dict.fromkeys(paths + full) if re.search(r"article|complex|search|trade|price", p, re.I)]
    return {"api_paths": keep[:80], "scripts": list(dict.fromkeys(re.findall(r'src="(https?://[^"]+\.js[^"]*)"', text)))[:40]}


# 1) 구 모바일 API (실제 단지번호)
step("m_article_list", f"https://m.land.naver.com/complex/getComplexArticleList?hscpNo={NO}&tradTpCd=B1%3AB2&order=price_&showR0=N&page=1",
     {**M, "Referer": f"https://m.land.naver.com/complex/info/{NO}", "X-Requested-With": "XMLHttpRequest"})
step("m_complex_info_redirect", f"https://m.land.naver.com/complex/info/{NO}", M, head=300)

# 2) fin.land 단지 페이지 + 매물 탭 → API 경로 후보 추출
fin = step("fin_page", f"https://fin.land.naver.com/complexes/{NO}", M, head=1500, extra=api_paths)
step("fin_page_article_tab", f"https://fin.land.naver.com/complexes/{NO}?tab=article", M, head=1500, extra=api_paths)
# JS 청크에서 api 경로 긁기
found = set()
for js in (fin.get("scripts") or [])[:12]:
    try:
        r = s.get(js, headers=M, timeout=15)
        for p in api_paths(r.text)["api_paths"]:
            found.add(p)
    except Exception:  # noqa: BLE001
        pass
out["fin_js_api_paths"] = sorted(found)[:150]
print("[diag2] fin js api paths:", len(found))

# 3) fin.land API 후보 직접 호출 (추측)
for name, url in [
    ("fin_api_articles_a", f"https://fin.land.naver.com/front-api/v1/complex/article/list?complexNumber={NO}&tradeTypes=B1,B2&page=1"),
    ("fin_api_articles_b", f"https://fin.land.naver.com/front-api/v1/complex/{NO}/articles?tradeTypes=B1,B2"),
    ("fin_api_complex", f"https://fin.land.naver.com/front-api/v1/complex/{NO}"),
]:
    step(name, url, {**M, "Referer": f"https://fin.land.naver.com/complexes/{NO}"}, head=1200)

# 4) new.land: 페이지/JS에서 Bearer 토큰 찾고 API 호출
tok = None
r = s.get(f"https://new.land.naver.com/complexes/{NO}", headers={**P, "Accept": "text/html"}, timeout=15)
html = r.text
m = re.search(r"Bearer\s+(eyJ[\w\-\.]+)", html)
if m:
    tok = m.group(1)
srcs = re.findall(r'src="([^"]+\.js[^"]*)"', html)
out["newland_scripts"] = srcs[:20]
if not tok:
    for js in srcs[:15]:
        u = js if js.startswith("http") else "https://new.land.naver.com" + js
        try:
            t = s.get(u, headers=P, timeout=15).text
            m = re.search(r"Bearer\s+(eyJ[\w\-\.]+)", t) or re.search(r"[\"'](eyJ[\w\-]{20,}\.[\w\-]+\.[\w\-]+)[\"']", t)
            if m:
                tok = m.group(1)
                out["newland_token_src"] = u
                break
        except Exception:  # noqa: BLE001
            pass
out["newland_token_found"] = bool(tok)
out["newland_token_head"] = (tok or "")[:40]
hdr = {**P, "Referer": f"https://new.land.naver.com/complexes/{NO}"}
if tok:
    hdr["Authorization"] = f"Bearer {tok}"
step("newland_articles", f"https://new.land.naver.com/api/articles/complex/{NO}?realEstateType=APT%3APRE%3AABYG%3AJGC%3AOPST&tradeType=B1%3AB2&tag=%3A%3A%3A%3A%3A%3A%3A%3A&rentPriceMin=0&rentPriceMax=900000000&priceMin=0&priceMax=900000000&areaMin=0&areaMax=900000000&showArticle=false&sameAddressGroup=false&priceType=RETAIL&page=1&complexNo={NO}&type=list&order=prc", hdr, head=1500)
step("newland_search", "https://new.land.naver.com/api/search?keyword=%ED%91%B8%EB%A5%B8%EB%A7%88%EC%9D%84", hdr, head=1500)

# 5) 모호한 이름 검색 시 리다이렉트 형태
step("m_search_ambiguous", "https://m.land.naver.com/search/result/" + quote("푸른마을"), M, head=600,
     extra=lambda t: {"complex_links": list(dict.fromkeys(re.findall(r"complexes/(\d+)", t)))[:30]})

path = ROOT / "data" / "diag2.json"
path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
try:
    c = publish.load_local_cfg()
    ref = publish.gh(c, "GET", f"/repos/{c['repo']}/git/ref/heads/{c['branch']}")
    head_sha = ref["object"]["sha"]
    base_tree = publish.gh(c, "GET", f"/repos/{c['repo']}/git/commits/{head_sha}")["tree"]["sha"]
    blob = publish.gh(c, "POST", f"/repos/{c['repo']}/git/blobs", json={"content": path.read_text(encoding="utf-8"), "encoding": "utf-8"})
    tree = publish.gh(c, "POST", f"/repos/{c['repo']}/git/trees", json={"base_tree": base_tree, "tree": [{"path": "data/diag2.json", "mode": "100644", "type": "blob", "sha": blob["sha"]}]})
    commit = publish.gh(c, "POST", f"/repos/{c['repo']}/git/commits", json={"message": "diag2", "tree": tree["sha"], "parents": [head_sha]})
    publish.gh(c, "PATCH", f"/repos/{c['repo']}/git/refs/heads/{c['branch']}", json={"sha": commit["sha"]})
    print("[diag2] 업로드 완료 → data/diag2.json")
except Exception as e:  # noqa: BLE001
    print("[diag2] 업로드 실패:", e)
