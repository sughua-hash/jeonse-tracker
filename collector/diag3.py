"""진단 3단계: fin.land 매물 탭 HTML 전체와 JS 번들에서 API 주소 문자열을 모아 업로드."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import naver  # noqa: E402
import publish  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
NO = sys.argv[1] if len(sys.argv) > 1 else "109266"
M = {"User-Agent": naver.MOBILE_UA, "Accept": "*/*", "Accept-Language": "ko-KR,ko;q=0.9"}
s = naver.make_session()

html = s.get(f"https://fin.land.naver.com/complexes/{NO}?tab=article", headers=M, timeout=20).text
print("[diag3] html", len(html))
scripts = list(dict.fromkeys(re.findall(r'src="(https?://[^"]+\.js[^"]*)"', html)))
hits = {}
pat_url = re.compile(r"https?://[A-Za-z0-9\.\-]+(?:/[A-Za-z0-9_\-/\.{}$%?=&]*)?")
pat_path = re.compile(r"[\"'`](/[A-Za-z0-9_\-]+(?:/[A-Za-z0-9_\-{}$\.]+)+)[\"'`]")
for i, js in enumerate(scripts):
    try:
        t = s.get(js, headers=M, timeout=20).text
    except Exception as e:  # noqa: BLE001
        print("[diag3] js fail", js, e)
        continue
    urls = [u for u in set(pat_url.findall(t)) if re.search(r"naver|api", u, re.I) and not re.search(r"pstatic|w3\.org|schema\.org|sentry|google", u)]
    paths = [p for p in set(pat_path.findall(t)) if re.search(r"api|article|complex|search|trade|price|estate", p, re.I)]
    if urls or paths:
        hits[js.rsplit("/", 1)[-1]] = {"urls": sorted(urls)[:80], "paths": sorted(paths)[:150]}
    print(f"[diag3] {i+1}/{len(scripts)} {js.rsplit('/',1)[-1]} urls={len(urls)} paths={len(paths)}")

out = {"no": NO, "scripts": scripts, "hits": hits}
(ROOT / "data").mkdir(exist_ok=True)
(ROOT / "data" / "diag3.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
(ROOT / "data" / "diag_fin.html").write_text(html, encoding="utf-8")

try:
    c = publish.load_local_cfg()
    ref = publish.gh(c, "GET", f"/repos/{c['repo']}/git/ref/heads/{c['branch']}")
    head_sha = ref["object"]["sha"]
    base_tree = publish.gh(c, "GET", f"/repos/{c['repo']}/git/commits/{head_sha}")["tree"]["sha"]
    tree = []
    for name in ("diag3.json", "diag_fin.html"):
        blob = publish.gh(c, "POST", f"/repos/{c['repo']}/git/blobs", json={"content": (ROOT / "data" / name).read_text(encoding="utf-8"), "encoding": "utf-8"})
        tree.append({"path": f"data/{name}", "mode": "100644", "type": "blob", "sha": blob["sha"]})
    t = publish.gh(c, "POST", f"/repos/{c['repo']}/git/trees", json={"base_tree": base_tree, "tree": tree})
    commit = publish.gh(c, "POST", f"/repos/{c['repo']}/git/commits", json={"message": "diag3", "tree": t["sha"], "parents": [head_sha]})
    publish.gh(c, "PATCH", f"/repos/{c['repo']}/git/refs/heads/{c['branch']}", json={"sha": commit["sha"]})
    print("[diag3] 업로드 완료")
except Exception as e:  # noqa: BLE001
    print("[diag3] 업로드 실패:", e)
