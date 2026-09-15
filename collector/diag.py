"""진단: 네이버 검색/매물 API 응답을 그대로 기록해 GitHub(data/diag.json)에 올린다.
실행: python collector/diag.py [검색어]
"""
from __future__ import annotations

import json
import re
import sys
import datetime as dt
from pathlib import Path
from urllib.parse import quote

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import naver  # noqa: E402
import publish  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
KW = sys.argv[1] if len(sys.argv) > 1 else "위례센트럴자이"


def probe(s, name, url, headers, allow_redirects=True):
    rec = {"name": name, "url": url}
    try:
        r = s.get(url, headers=headers, timeout=15, allow_redirects=allow_redirects)
        rec.update({"status": r.status_code, "final_url": r.url, "ctype": r.headers.get("content-type", ""),
                    "len": len(r.text), "head": r.text[:1500]})
        ids = list(dict.fromkeys(re.findall(r"(?:complexNo|hscpNo|complex/info/|complexes/)[=/\"':\s]*(\d{3,8})", r.text)))[:20]
        rec["ids_found"] = ids
        # 링크형 후보도
        rec["links"] = list(dict.fromkeys(re.findall(r"https?://[^\s\"'<>]*complex[^\s\"'<>]*", r.text)))[:10]
    except Exception as e:  # noqa: BLE001
        rec["error"] = f"{type(e).__name__}: {e}"
    return rec


def main():
    s = naver.make_session()
    q = quote(KW)
    M = {"User-Agent": naver.MOBILE_UA, "Referer": "https://m.land.naver.com/"}
    P = {"User-Agent": naver.PC_UA, "Referer": "https://new.land.naver.com/"}
    out = {"kw": KW, "at": dt.datetime.now().isoformat(timespec="seconds"), "probes": []}
    tests = [
        ("pc_api_search", f"https://new.land.naver.com/api/search?keyword={q}", P),
        ("pc_api_search_json", f"https://new.land.naver.com/api/search?keyword={q}", {**P, "Accept": "application/json"}),
        ("m_search_result", f"https://m.land.naver.com/search/result/{q}", M),
        ("m_search_result_noredirect", f"https://m.land.naver.com/search/result/{q}", M, False),
        ("m_autocomplete", f"https://m.land.naver.com/search/autoComplete?keyword={q}", M),
        ("m_ac", f"https://m.land.naver.com/ac?q={q}&q_enc=utf-8&st=1", M),
        ("map_search", f"https://map.naver.com/p/api/search/allSearch?query={q}&type=all&searchCoord=&boundary=", {"User-Agent": naver.PC_UA, "Referer": "https://map.naver.com/"}),
        ("pc_complex_page", "https://new.land.naver.com/complexes/111515", {"User-Agent": naver.PC_UA, "Accept": "text/html"}),
        ("m_article_list", "https://m.land.naver.com/complex/getComplexArticleList?hscpNo=111515&tradTpCd=B1%3AB2&order=price_&showR0=N&page=1",
         {**M, "Referer": "https://m.land.naver.com/complex/info/111515", "X-Requested-With": "XMLHttpRequest"}),
        ("pc_article_list", "https://new.land.naver.com/api/articles/complex/111515?realEstateType=APT&tradeType=B1%3AB2&page=1&complexNo=111515&type=list&order=prc", P),
    ]
    for t in tests:
        name, url, hdr = t[0], t[1], t[2]
        allow = t[3] if len(t) > 3 else True
        out["probes"].append(probe(s, name, url, hdr, allow))
        print("[diag]", name, out["probes"][-1].get("status", out["probes"][-1].get("error")))
    path = ROOT / "data" / "diag.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        c = publish.load_local_cfg()
        ref = publish.gh(c, "GET", f"/repos/{c['repo']}/git/ref/heads/{c['branch']}")
        head = ref["object"]["sha"]
        base_tree = publish.gh(c, "GET", f"/repos/{c['repo']}/git/commits/{head}")["tree"]["sha"]
        blob = publish.gh(c, "POST", f"/repos/{c['repo']}/git/blobs", json={"content": path.read_text(encoding="utf-8"), "encoding": "utf-8"})
        tree = publish.gh(c, "POST", f"/repos/{c['repo']}/git/trees", json={"base_tree": base_tree, "tree": [
            {"path": "data/diag.json", "mode": "100644", "type": "blob", "sha": blob["sha"]}]})
        commit = publish.gh(c, "POST", f"/repos/{c['repo']}/git/commits", json={"message": "diag", "tree": tree["sha"], "parents": [head]})
        publish.gh(c, "PATCH", f"/repos/{c['repo']}/git/refs/heads/{c['branch']}", json={"sha": commit["sha"]})
        print("[diag] 업로드 완료 → data/diag.json")
    except Exception as e:  # noqa: BLE001
        print("[diag] 업로드 실패:", e)


if __name__ == "__main__":
    main()
