"""진단 4단계: fin.land front-api 매물 목록 엔드포인트의 요청 형식 확인."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import naver  # noqa: E402
import publish  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
NO = int(sys.argv[1]) if len(sys.argv) > 1 else 109266
BASE = "https://fin.land.naver.com/front-api/v1"
H = {"User-Agent": naver.MOBILE_UA, "Accept": "application/json, text/plain, */*", "Accept-Language": "ko-KR,ko;q=0.9",
     "Referer": f"https://fin.land.naver.com/complexes/{NO}?tab=article", "Origin": "https://fin.land.naver.com"}
s = naver.make_session()
out = {"no": NO, "calls": [], "snippets": {}}


def call(name, method, path, params=None, body=None):
    rec = {"name": name, "method": method, "path": path, "params": params, "body": body}
    try:
        r = s.request(method, BASE + path, params=params, json=body, headers=H, timeout=20)
        rec.update({"status": r.status_code, "len": len(r.text), "head": r.text[:2500]})
    except Exception as e:  # noqa: BLE001
        rec["error"] = f"{type(e).__name__}: {e}"
    out["calls"].append(rec)
    print("[diag4]", name, rec.get("status", rec.get("error")), rec.get("len"))


call("pyeongList", "GET", "/complex/pyeongList", {"complexNumber": NO})
call("complex", "GET", "/complex", {"complexNumber": NO})
call("article_stats_get", "GET", "/complex/article/stats", {"complexNumber": NO})
call("article_list_get", "GET", "/complex/article/list", {"complexNumber": NO})
call("article_list_post_empty", "POST", "/complex/article/list", None, {})
call("article_list_post_min", "POST", "/complex/article/list", None, {"complexNumber": NO})
call("article_list_post_guess", "POST", "/complex/article/list", None,
     {"complexNumber": NO, "tradeTypes": ["B1", "B2"], "pyeongTypeNumbers": [], "dongNumbers": [], "userChannelType": "MOBILE",
      "articleSortType": "RANKING_DESC", "size": 20, "page": 1})
call("article_stats_post", "POST", "/complex/article/stats", None, {"complexNumber": NO, "tradeTypes": ["B1", "B2"]})

# JS 청크에서 article/list 주변 코드 추출
html = s.get(f"https://fin.land.naver.com/complexes/{NO}?tab=article", headers={"User-Agent": naver.MOBILE_UA}, timeout=20).text
scripts = list(dict.fromkeys(re.findall(r'src="(https?://[^"]+\.js[^"]*)"', html)))
for js in scripts:
    try:
        t = s.get(js, headers={"User-Agent": naver.MOBILE_UA}, timeout=20).text
    except Exception:  # noqa: BLE001
        continue
    for key in ("complex/article/list", "complex/article/stats", "articleSortType", "tradeTypes", "pyeongTypeNumbers"):
        for m in list(re.finditer(re.escape(key), t))[:2]:
            out["snippets"].setdefault(key, []).append({"js": js.rsplit("/", 1)[-1], "code": t[max(0, m.start() - 1200): m.start() + 1200]})
print("[diag4] snippets:", {k: len(v) for k, v in out["snippets"].items()})

p = ROOT / "data" / "diag4.json"
p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
try:
    c = publish.load_local_cfg()
    ref = publish.gh(c, "GET", f"/repos/{c['repo']}/git/ref/heads/{c['branch']}")
    head_sha = ref["object"]["sha"]
    base_tree = publish.gh(c, "GET", f"/repos/{c['repo']}/git/commits/{head_sha}")["tree"]["sha"]
    blob = publish.gh(c, "POST", f"/repos/{c['repo']}/git/blobs", json={"content": p.read_text(encoding="utf-8"), "encoding": "utf-8"})
    t = publish.gh(c, "POST", f"/repos/{c['repo']}/git/trees", json={"base_tree": base_tree, "tree": [{"path": "data/diag4.json", "mode": "100644", "type": "blob", "sha": blob["sha"]}]})
    commit = publish.gh(c, "POST", f"/repos/{c['repo']}/git/commits", json={"message": "diag4", "tree": t["sha"], "parents": [head_sha]})
    publish.gh(c, "PATCH", f"/repos/{c['repo']}/git/refs/heads/{c['branch']}", json={"sha": commit["sha"]})
    print("[diag4] 업로드 완료")
except Exception as e:  # noqa: BLE001
    print("[diag4] 업로드 실패:", e)
