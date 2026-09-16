"""네이버 부동산 매물 조회 모듈.

매물: fin.land.naver.com/front-api/v1/complex/article/list (POST, seed/lastInfo 페이징)
검색: m.land 검색 리다이렉트 → new.land /api/search 폴백

모든 금액 단위는 '만원'.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, asdict
from typing import Iterable, Optional
from urllib.parse import quote

import requests

MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 14; SM-S911N) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"
)
PC_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

TRADE_JEONSE = "B1"
TRADE_WOLSE = "B2"


class NaverError(Exception):
    pass


@dataclass
class Article:
    article_no: str
    trade: str            # "B1" 전세 / "B2" 월세
    deposit: int          # 만원 (전세는 전세보증금)
    rent: int             # 만원/월 (전세는 0)
    area_exclusive: float  # 전용 m²
    area_supply: Optional[float]
    floor: str            # "12/25"
    building: str         # "101동"
    direction: str
    confirmed: str        # 확인일자 "25.09.14"
    description: str
    realtor: str
    price_text: str       # 원문 "1억/150"

    def to_dict(self):
        return asdict(self)


# ---------------------------------------------------------------- 금액 파싱
_NUM = re.compile(r"[\d,]+")


def parse_price_manwon(text: str) -> int:
    """'7억 5,000' -> 75000, '5,000' -> 5000, '1억' -> 10000, '12억3천' -> 123000"""
    if text is None:
        return 0
    t = str(text).replace(" ", "").replace(",", "")
    if not t:
        return 0
    total = 0
    m = re.match(r"^(\d+)억(.*)$", t)
    if m:
        total += int(m.group(1)) * 10000
        t = m.group(2)
    m = re.match(r"^(\d+)천(.*)$", t)
    if m:
        total += int(m.group(1)) * 1000
        t = m.group(2)
    if t:
        m = re.match(r"^(\d+)", t)
        if m:
            total += int(m.group(1))
    return total


def parse_price_info(prc_info: str, trade: str) -> tuple[int, int]:
    """'1억/150' -> (10000, 150). 전세는 (보증금, 0)."""
    if prc_info is None:
        return (0, 0)
    s = str(prc_info)
    if "/" in s:
        dep, rent = s.split("/", 1)
        return parse_price_manwon(dep), parse_price_manwon(rent)
    if trade == TRADE_WOLSE:
        # 월세인데 '/'가 없으면 판단 불가 → 보증금만 있는 것으로 처리
        return parse_price_manwon(s), 0
    return parse_price_manwon(s), 0


def _to_float(v) -> Optional[float]:
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- 세션
def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    })
    return s


def _get(session: requests.Session, url: str, headers: dict, retries: int = 2, timeout: int = 12):
    last = None
    for i in range(retries):
        try:
            r = session.get(url, headers=headers, timeout=timeout)
            if r.status_code == 200:
                return r
            last = NaverError(f"HTTP {r.status_code} for {url}")
            if r.status_code in (403, 404, 429):
                break  # 차단/없음은 재시도해도 소용없음
        except requests.RequestException as e:  # noqa: PERF203
            last = e
            time.sleep(1.5 * (i + 1))
    raise NaverError(str(last))


def preflight(session: requests.Session) -> dict:
    """네이버 접근 가능 여부를 빠르게 점검. {mobile: 'ok'|오류, pc: ...}"""
    out = {}
    for name, url, ua in (
        ("fin", "https://fin.land.naver.com/front-api/v1/complex/article/stats?complexNumber=109266", MOBILE_UA),
    ):
        t = time.time()
        try:
            r = session.get(url, headers={"User-Agent": ua, "Referer": "https://fin.land.naver.com/complexes/109266"}, timeout=12)
            body = r.text[:120].replace("\n", " ")
            out[name] = f"HTTP {r.status_code} ({time.time()-t:.1f}s) {body!r}"
        except Exception as e:  # noqa: BLE001
            out[name] = f"실패 ({time.time()-t:.1f}s): {type(e).__name__}: {e}"
    return out


# ---------------------------------------------------------------- fin.land (신규 모바일) API — 2026.09 기준 동작 확인
FIN_BASE = "https://fin.land.naver.com/front-api/v1"


def _fin_headers(complex_no: str) -> dict:
    return {
        "User-Agent": MOBILE_UA,
        "Accept": "application/json, text/plain, */*",
        "Referer": f"https://fin.land.naver.com/complexes/{complex_no}?tab=article",
        "Origin": "https://fin.land.naver.com",
    }


def _fin_article(it: dict) -> Optional[Article]:
    """fin.land 매물 항목(representativeArticleInfo 또는 articleInfoList 원소) → Article"""
    if not it:
        return None
    price = it.get("priceInfo") or {}
    trade = it.get("tradeType") or "B1"
    won = lambda v: int(round((v or 0) / 10000))  # noqa: E731  원 → 만원
    deposit = won(price.get("warrantyPrice"))
    rent = won(price.get("rentPrice")) if trade in (TRADE_WOLSE, "B3") else 0
    space = it.get("spaceInfo") or {}
    det = it.get("articleDetail") or {}
    ver = it.get("verificationInfo") or {}
    broker = it.get("brokerInfo") or {}
    return Article(
        article_no=str(it.get("articleNumber") or ""),
        trade=trade,
        deposit=deposit,
        rent=rent,
        area_exclusive=_to_float(space.get("exclusiveSpace")) or 0.0,
        area_supply=_to_float(space.get("supplySpace")),
        floor=str(det.get("floorInfo") or ""),
        building=str(it.get("dongName") or ""),
        direction=str(det.get("direction") or ""),
        confirmed=str(ver.get("articleConfirmDate") or ""),
        description=str(det.get("articleFeatureDescription") or ""),
        realtor=str(broker.get("brokerageName") or broker.get("brokerName") or ""),
        price_text=(f"{deposit}/{rent}" if rent else str(deposit)),
    )


def fetch_articles_fin(session: requests.Session, complex_no: str, trades=(TRADE_JEONSE, TRADE_WOLSE),
                       max_pages: int = 40, sleep: float = 0.5, include_duplicates: bool = True) -> list[Article]:
    """POST /complex/article/list 를 seed/lastInfo 로 페이징하며 전부 수집."""
    url = f"{FIN_BASE}/complex/article/list"
    body = {
        "complexNumber": int(complex_no), "tradeTypes": list(trades), "pyeongTypeNumbers": [], "dongNumbers": [],
        "userChannelType": "MOBILE", "articleSortType": "PRICE_ASC", "size": 30, "lastInfo": [],
    }
    out: list[Article] = []
    seen: set[str] = set()
    hdr = _fin_headers(complex_no)
    for _ in range(max_pages):
        last = None
        for attempt in range(3):
            try:
                r = session.post(url, json=body, headers=hdr, timeout=20)
                if r.status_code == 200:
                    break
                last = NaverError(f"HTTP {r.status_code} {r.text[:120]}")
                if r.status_code in (400, 404):
                    raise last
                time.sleep(3 * (attempt + 1))
            except requests.RequestException as e:
                last = e
                time.sleep(2 * (attempt + 1))
        else:
            raise NaverError(str(last))
        data = r.json()
        if not data.get("isSuccess"):
            raise NaverError(f"fin API 실패: {str(data)[:200]}")
        res = data.get("result") or {}
        items = res.get("list") or []
        for row in items:
            cands = [row.get("representativeArticleInfo")]
            if include_duplicates:
                cands += (row.get("duplicatedArticleInfo") or {}).get("articleInfoList") or []
            for it in cands:
                a = _fin_article(it)
                if a and a.article_no and a.article_no not in seen:
                    seen.add(a.article_no)
                    out.append(a)
        if not res.get("hasNextPage") or not items:
            break
        body["seed"] = res.get("seed")
        body["lastInfo"] = res.get("lastInfo") or []
        time.sleep(sleep)
    return out


def fetch_complex_info(session: requests.Session, complex_no: str) -> dict:
    r = session.get(f"{FIN_BASE}/complex", params={"complexNumber": int(complex_no)}, headers=_fin_headers(complex_no), timeout=15)
    r.raise_for_status()
    return (r.json() or {}).get("result") or {}


def fetch_articles(session: requests.Session, complex_no: str) -> tuple[list[Article], str]:
    """(매물목록, 사용한 소스) 반환."""
    return fetch_articles_fin(session, complex_no), "fin"


# ---------------------------------------------------------------- 공유 링크(naver.me 등) → 단지번호
_NO_PATTERNS = (
    r"/complex(?:es|/info)/(\d+)",
    r"[?&](?:complexNo|hscpNo|complexNumber)=(\d+)",
    r"complexNo\"?\s*[:=]\s*\"?(\d{3,8})",
    r"complexNumber\"?\s*[:=]\s*\"?(\d{3,8})",
)


def resolve_complex_url(session: requests.Session, url: str) -> Optional[str]:
    """네이버 부동산 공유 링크(https://naver.me/xxxx, m.land.naver.com/..., new.land.naver.com/complexes/...)를
    따라가 단지번호를 뽑아낸다. 못 찾으면 None."""
    for pat in _NO_PATTERNS[:2]:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    r = session.get(url, headers={"User-Agent": MOBILE_UA, "Accept": "text/html,*/*"}, timeout=15, allow_redirects=True)
    chain = [h.headers.get("Location", "") for h in r.history] + [r.url]
    for u in chain:
        for pat in _NO_PATTERNS[:2]:
            m = re.search(pat, u or "")
            if m:
                return m.group(1)
    body = r.text or ""
    for pat in _NO_PATTERNS:
        m = re.search(pat, body)
        if m:
            return m.group(1)
    return None


# ---------------------------------------------------------------- 단지 검색 (이름 → 단지번호)
def search_complex(session: requests.Session, keyword: str) -> list[dict]:
    """키워드로 단지 후보 검색. [{complexNo, name, address}] 반환."""
    results: list[dict] = []
    # 1) 모바일 검색: 결과가 하나면 fin.land 단지 페이지로 리다이렉트됨 → URL에서 번호 추출
    try:
        r = session.get(f"https://m.land.naver.com/search/result/{quote(keyword)}",
                        headers={"User-Agent": MOBILE_UA, "Accept": "text/html,*/*"},
                        timeout=15, allow_redirects=True)
        m = re.search(r"/complex(?:es|/info)/(\d+)", r.url)
        if m:
            no = m.group(1)
            name, addr = keyword, ""
            try:
                info = fetch_complex_info(session, no)
                name = info.get("name") or keyword
                a = info.get("address") or {}
                addr = " ".join(x for x in (a.get("city"), a.get("division"), a.get("sector")) if x)
            except Exception:  # noqa: BLE001
                pass
            return [{"complexNo": no, "name": name, "address": addr}]
        for no in dict.fromkeys(re.findall(r"/complex(?:es|/info)/(\d+)", r.text)):
            results.append({"complexNo": no, "name": keyword, "address": ""})
        if results:
            return results
    except Exception:  # noqa: BLE001
        pass
    # 2) PC 검색 API (요청 과다 시 429 → 잠시 대기 후 재시도)
    for attempt in range(3):
        try:
            r = session.get(f"https://new.land.naver.com/api/search?keyword={quote(keyword)}",
                            headers={"User-Agent": PC_UA, "Referer": "https://new.land.naver.com/", "Accept": "application/json"},
                            timeout=15)
            if r.status_code == 429:
                time.sleep(8 * (attempt + 1))
                continue
            if r.status_code != 200:
                break
            data = r.json()
            for c in data.get("complexes") or []:
                results.append({
                    "complexNo": str(c.get("complexNo")),
                    "name": c.get("complexName"),
                    "address": c.get("cortarAddress") or c.get("address") or "",
                })
            break
        except Exception:  # noqa: BLE001
            break
    return results


def pick_complex(cands: list[dict], name: str, region_hint: str = "") -> Optional[dict]:
    """후보 중 이름/지역이 가장 잘 맞는 단지 선택."""
    if not cands:
        return None
    norm = lambda s: re.sub(r"[\s\(\)\-·]", "", str(s or "")).lower()  # noqa: E731
    n = norm(name)
    hint_tokens = [t for t in re.split(r"\s+", region_hint or "") if len(t) >= 2]

    def score(c):
        s = 0
        cn = norm(c.get("name"))
        if cn == n:
            s += 100
        elif n in cn or cn in n:
            s += 60
        addr = str(c.get("address") or "")
        s += sum(10 for t in hint_tokens if t in addr)
        return s

    best = max(cands, key=score)
    return best if score(best) > 0 or len(cands) == 1 else cands[0]


def dumps(articles: Iterable[Article]) -> str:
    return json.dumps([a.to_dict() for a in articles], ensure_ascii=False, indent=1)
