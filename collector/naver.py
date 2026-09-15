"""네이버 부동산 매물 조회 모듈.

1차: 모바일 API (m.land.naver.com/complex/getComplexArticleList) — 인증 불필요
2차: PC API (new.land.naver.com/api/articles/complex/{no}) — 페이지에서 Bearer 토큰 추출 시도

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


def _get(session: requests.Session, url: str, headers: dict, retries: int = 3, timeout: int = 20):
    last = None
    for i in range(retries):
        try:
            r = session.get(url, headers=headers, timeout=timeout)
            if r.status_code == 200:
                return r
            last = NaverError(f"HTTP {r.status_code} for {url}")
            if r.status_code in (403, 429):
                time.sleep(3 * (i + 1))
        except requests.RequestException as e:  # noqa: PERF203
            last = e
            time.sleep(2 * (i + 1))
    raise NaverError(str(last))


# ---------------------------------------------------------------- 모바일 API
def fetch_articles_mobile(session: requests.Session, complex_no: str, trades=(TRADE_JEONSE, TRADE_WOLSE),
                          max_pages: int = 30, sleep: float = 0.4) -> list[Article]:
    """m.land.naver.com 매물 목록 (전 페이지)."""
    trad = quote(":".join(trades))
    headers = {
        "User-Agent": MOBILE_UA,
        "Referer": f"https://m.land.naver.com/complex/info/{complex_no}",
        "X-Requested-With": "XMLHttpRequest",
    }
    out: list[Article] = []
    seen: set[str] = set()
    page = 1
    while page <= max_pages:
        url = (
            f"https://m.land.naver.com/complex/getComplexArticleList"
            f"?hscpNo={complex_no}&tradTpCd={trad}&order=price_&showR0=N&page={page}"
        )
        r = _get(session, url, headers)
        try:
            data = r.json()
        except ValueError as e:
            raise NaverError(f"JSON 파싱 실패 (모바일 API): {r.text[:200]}") from e
        result = data.get("result") or data
        items = result.get("list") or []
        for it in items:
            no = str(it.get("atclNo"))
            if no in seen:
                continue
            seen.add(no)
            trade = it.get("tradTpCd") or ("B2" if "/" in str(it.get("prcInfo", "")) else "B1")
            deposit, rent = parse_price_info(it.get("prcInfo"), trade)
            out.append(Article(
                article_no=no,
                trade=trade,
                deposit=deposit,
                rent=rent,
                area_exclusive=_to_float(it.get("spc2")) or 0.0,
                area_supply=_to_float(it.get("spc1")),
                floor=str(it.get("flrInfo") or ""),
                building=str(it.get("bildNm") or ""),
                direction=str(it.get("direction") or ""),
                confirmed=str(it.get("atclCfmYmd") or it.get("cfmYmd") or ""),
                description=str(it.get("atclFetrDesc") or ""),
                realtor=str(it.get("rltrNm") or it.get("cpNm") or ""),
                price_text=str(it.get("prcInfo") or ""),
            ))
        more = str(result.get("moreDataYn", "N")).upper() == "Y"
        if not more or not items:
            break
        page += 1
        time.sleep(sleep)
    return out


# ---------------------------------------------------------------- PC API (fallback)
_TOKEN_CACHE: dict[str, str] = {}


def _find_bearer_token(session: requests.Session, complex_no: str) -> Optional[str]:
    if "token" in _TOKEN_CACHE:
        return _TOKEN_CACHE["token"]
    headers = {"User-Agent": PC_UA, "Accept": "text/html,*/*"}
    try:
        r = _get(session, f"https://new.land.naver.com/complexes/{complex_no}", headers)
    except NaverError:
        return None
    html = r.text
    m = re.search(r"Bearer\s+(eyJ[\w\-\.]+)", html)
    if m:
        _TOKEN_CACHE["token"] = m.group(1)
        return m.group(1)
    # 번들 JS 안에 있는 경우
    for js in re.findall(r'src="([^"]+\.js[^"]*)"', html)[:12]:
        url = js if js.startswith("http") else "https://new.land.naver.com" + js
        try:
            rj = _get(session, url, headers, retries=1)
        except NaverError:
            continue
        m = re.search(r"Bearer\s+(eyJ[\w\-\.]+)", rj.text)
        if m:
            _TOKEN_CACHE["token"] = m.group(1)
            return m.group(1)
    return None


def fetch_articles_pc(session: requests.Session, complex_no: str, trades=(TRADE_JEONSE, TRADE_WOLSE),
                      real_estate_type: str = "APT:PRE:ABYG:JGC:OPST", max_pages: int = 30,
                      sleep: float = 0.4) -> list[Article]:
    token = _find_bearer_token(session, complex_no)
    headers = {
        "User-Agent": PC_UA,
        "Referer": f"https://new.land.naver.com/complexes/{complex_no}",
        "Accept": "*/*",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    out: list[Article] = []
    seen: set[str] = set()
    page = 1
    while page <= max_pages:
        url = (
            f"https://new.land.naver.com/api/articles/complex/{complex_no}"
            f"?realEstateType={quote(real_estate_type)}&tradeType={quote(':'.join(trades))}"
            f"&tag=%3A%3A%3A%3A%3A%3A%3A%3A&rentPriceMin=0&rentPriceMax=900000000&priceMin=0&priceMax=900000000"
            f"&areaMin=0&areaMax=900000000&showArticle=false&sameAddressGroup=false&priceType=RETAIL"
            f"&page={page}&complexNo={complex_no}&type=list&order=prc"
        )
        r = _get(session, url, headers)
        try:
            data = r.json()
        except ValueError as e:
            raise NaverError(f"JSON 파싱 실패 (PC API): {r.text[:200]}") from e
        items = data.get("articleList") or []
        for it in items:
            no = str(it.get("articleNo"))
            if no in seen:
                continue
            seen.add(no)
            trade = it.get("tradeTypeCode") or "B1"
            deposit = parse_price_manwon(it.get("dealOrWarrantPrc"))
            rent = parse_price_manwon(it.get("rentPrc")) if trade == TRADE_WOLSE else 0
            price_text = str(it.get("dealOrWarrantPrc") or "")
            if rent:
                price_text += f"/{rent}"
            out.append(Article(
                article_no=no,
                trade=trade,
                deposit=deposit,
                rent=rent,
                area_exclusive=_to_float(it.get("area2")) or 0.0,
                area_supply=_to_float(it.get("area1")),
                floor=str(it.get("floorInfo") or ""),
                building=str(it.get("buildingName") or ""),
                direction=str(it.get("direction") or ""),
                confirmed=str(it.get("articleConfirmYmd") or ""),
                description=str(it.get("articleFeatureDesc") or ""),
                realtor=str(it.get("realtorName") or ""),
                price_text=price_text,
            ))
        if not data.get("isMoreData") or not items:
            break
        page += 1
        time.sleep(sleep)
    return out


def fetch_articles(session: requests.Session, complex_no: str) -> tuple[list[Article], str]:
    """모바일 API 우선, 실패 시 PC API. (매물목록, 사용한 소스) 반환."""
    errors = []
    try:
        return fetch_articles_mobile(session, complex_no), "mobile"
    except Exception as e:  # noqa: BLE001
        errors.append(f"mobile: {e}")
    try:
        return fetch_articles_pc(session, complex_no), "pc"
    except Exception as e:  # noqa: BLE001
        errors.append(f"pc: {e}")
    raise NaverError(" | ".join(errors))


# ---------------------------------------------------------------- 단지 검색 (이름 → 단지번호)
def search_complex(session: requests.Session, keyword: str) -> list[dict]:
    """키워드로 단지 후보 검색. [{complexNo, name, address}] 반환."""
    results: list[dict] = []
    # 1) PC 검색 API
    try:
        r = _get(session, f"https://new.land.naver.com/api/search?keyword={quote(keyword)}",
                 {"User-Agent": PC_UA, "Referer": "https://new.land.naver.com/"}, retries=1)
        data = r.json()
        for c in data.get("complexes") or []:
            results.append({
                "complexNo": str(c.get("complexNo")),
                "name": c.get("complexName"),
                "address": c.get("cortarAddress") or c.get("address") or "",
            })
        if results:
            return results
    except Exception:  # noqa: BLE001
        pass
    # 2) 모바일 검색 페이지 (HTML) — 단지 링크 추출
    try:
        r = session.get(f"https://m.land.naver.com/search/result/{quote(keyword)}",
                        headers={"User-Agent": MOBILE_UA, "Accept": "text/html,*/*"},
                        timeout=20, allow_redirects=True)
        m = re.search(r"/complex/info/(\d+)", r.url)
        if m:
            return [{"complexNo": m.group(1), "name": keyword, "address": ""}]
        for no in dict.fromkeys(re.findall(r"/complex/info/(\d+)", r.text)):
            results.append({"complexNo": no, "name": keyword, "address": ""})
    except Exception:  # noqa: BLE001
        pass
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
