"""전월세 최저가 수집기.

사용법:
  python collector/collect.py                 # 수집 + 저장 + ntfy 알림
  python collector/collect.py --no-notify     # 알림 없이 수집만
  python collector/collect.py --dry-run       # 파일 저장/알림 없이 콘솔 출력만
  python collector/collect.py --only 위례센트럴자이

환경변수:
  NTFY_TOPIC      ntfy 채널 이름 (필수, 알림용)
  NTFY_SERVER     기본 https://ntfy.sh
  DASHBOARD_URL   알림 클릭 시 열 대시보드 주소
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Optional

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import naver  # noqa: E402
from naver import Article, TRADE_JEONSE, TRADE_WOLSE  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "complexes.json"
DATA_DIR = ROOT / "data"
HISTORY_DIR = DATA_DIR / "history"
ARTICLES_DIR = DATA_DIR / "articles"
LATEST_PATH = DATA_DIR / "latest.json"
KST = dt.timezone(dt.timedelta(hours=9))


# ---------------------------------------------------------------- 유틸
def now_kst() -> dt.datetime:
    return dt.datetime.now(tz=KST)


def load_json(path: Path, default):
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
        f.write("\n")


def fmt_money(manwon: Optional[int], signed: bool = False) -> str:
    """만원 → '7.5억' / '5,000만' / '150'"""
    if manwon is None:
        return "—"
    sign = ""
    v = int(manwon)
    if signed:
        if v == 0:
            return "="
        sign = "▲" if v > 0 else "▼"
        v = abs(v)
    if v >= 10000:
        eok = v / 10000
        s = f"{eok:.2f}".rstrip("0").rstrip(".")
        return f"{sign}{s}억"
    return f"{sign}{v:,}만"


def fmt_rent(rent: Optional[int], signed: bool = False) -> str:
    if rent is None:
        return "—"
    if signed:
        if rent == 0:
            return "="
        return ("▲" if rent > 0 else "▼") + f"{abs(rent)}"
    return f"{rent}"


def conv_price(deposit: int, rent: int, rate_pct: float) -> int:
    """월세 → 전세 환산가(만원): 보증금 + 월세*12 / 전환율"""
    if rate_pct <= 0:
        return deposit
    return int(round(deposit + rent * 12 * 100 / rate_pct))


# ---------------------------------------------------------------- 핵심 계산
# 평형대(전용면적 구간). 기본 구간(default)은 config의 area_min/max를 따른다.
DEFAULT_BANDS = [
    {"key": "84", "label": "84㎡ (전용 83~85)", "min": 83, "max": 85, "default": True},
    {"key": "100", "label": "86~105㎡", "min": 85.01, "max": 105},
    {"key": "115", "label": "106~120㎡", "min": 105.01, "max": 120},
    {"key": "130", "label": "121~140㎡", "min": 120.01, "max": 140},
    {"key": "150", "label": "141㎡ 이상", "min": 140.01, "max": 9999},
]


def area_bands(cfg: dict) -> list[dict]:
    bands = [dict(b) for b in (cfg.get("area_bands") or DEFAULT_BANDS)]
    for b in bands:
        if b.get("default"):
            b["min"], b["max"] = float(cfg.get("area_min_m2", 83)), float(cfg.get("area_max_m2", 85))
    return bands


def summarize(articles: list[Article], cfg: dict, amin: Optional[float] = None, amax: Optional[float] = None) -> dict:
    amin = float(cfg.get("area_min_m2", 83)) if amin is None else float(amin)
    amax = float(cfg.get("area_max_m2", 85)) if amax is None else float(amax)
    dep_max = int(cfg.get("wolse_deposit_max_manwon", 50000))
    rate = float(cfg.get("conversion_rate_pct", 5.5))

    in_area = [a for a in articles if amin <= a.area_exclusive <= amax]
    jeonse = [a for a in in_area if a.trade == TRADE_JEONSE and a.deposit > 0]
    wolse_all = [a for a in in_area if a.trade == TRADE_WOLSE and a.rent > 0]
    wolse = [a for a in wolse_all if a.deposit <= dep_max]

    def art(a: Article, extra=None):
        d = {
            "article_no": a.article_no, "deposit": a.deposit, "rent": a.rent,
            "area": a.area_exclusive, "floor": a.floor, "building": a.building,
            "direction": a.direction, "confirmed": a.confirmed, "price_text": a.price_text,
            "url": f"https://m.land.naver.com/article/info/{a.article_no}",
        }
        if extra:
            d.update(extra)
        return d

    # 전용면적 분포 (필터 조정 참고용): {"84.9": 12, ...}
    area_counts: dict[str, int] = {}
    for a in articles:
        if a.area_exclusive:
            k = f"{a.area_exclusive:.1f}".rstrip("0").rstrip(".")
            area_counts[k] = area_counts.get(k, 0) + 1
    areas = dict(sorted(area_counts.items(), key=lambda kv: float(kv[0]))[:20])
    rec = {
        "jeonse": None, "wolse_rent": None, "wolse_conv": None,
        "counts": {"all": len(articles), "in_area": len(in_area), "jeonse": len(jeonse),
                   "wolse": len(wolse_all), "wolse_ok": len(wolse)},
        "areas": areas,
    }
    if jeonse:
        b = min(jeonse, key=lambda a: a.deposit)
        rec["jeonse"] = {"price": b.deposit, "article": art(b)}
    if wolse:
        b = min(wolse, key=lambda a: (a.rent, a.deposit))
        rec["wolse_rent"] = {"rent": b.rent, "deposit": b.deposit, "article": art(b)}
        c = min(wolse, key=lambda a: conv_price(a.deposit, a.rent, rate))
        rec["wolse_conv"] = {"conv": conv_price(c.deposit, c.rent, rate), "rent": c.rent,
                             "deposit": c.deposit, "rate_pct": rate, "article": art(c)}
    return rec


def metric_value(rec: Optional[dict], key: str) -> Optional[int]:
    if not rec or not rec.get(key):
        return None
    m = rec[key]
    return {"jeonse": m.get("price"), "wolse_rent": m.get("rent"), "wolse_conv": m.get("conv")}[key]


def baseline(history: list[dict], today: str, days: int) -> Optional[dict]:
    """today - days 이전(포함) 중 가장 최근 기록. d1은 today 이전 아무 날이라도 가장 최근."""
    target = (dt.date.fromisoformat(today) - dt.timedelta(days=days)).isoformat()
    cands = [h for h in history if h["date"] <= target and h["date"] < today]
    if not cands:
        return None
    return max(cands, key=lambda h: h["date"])


def compute_deltas(history: list[dict], today_rec: dict, today: str) -> dict:
    out = {}
    for key in ("jeonse", "wolse_rent", "wolse_conv"):
        cur = metric_value(today_rec, key)
        row = {}
        for label, days in (("d1", 1), ("d7", 7), ("d30", 30)):
            b = baseline(history, today, days)
            prev = metric_value(b, key) if b else None
            row[label] = {
                "date": b["date"] if b else None,
                "prev": prev,
                "delta": (cur - prev) if (cur is not None and prev is not None) else None,
            }
        out[key] = row
    return out


# ---------------------------------------------------------------- 알림
def build_lines(name: str, rec: dict, deltas: dict) -> list[str]:
    lines = [f"■ {name}"]
    j = rec.get("jeonse")
    if j:
        d = deltas["jeonse"]
        lines.append(
            f"전세 {fmt_money(j['price'])} "
            f"(일{fmt_money(d['d1']['delta'], True)} 주{fmt_money(d['d7']['delta'], True)} 월{fmt_money(d['d30']['delta'], True)})"
        )
    else:
        lines.append("전세 매물 없음")
    w = rec.get("wolse_rent")
    if w:
        d = deltas["wolse_rent"]
        lines.append(
            f"월세 {fmt_money(w['deposit'])}/{w['rent']} "
            f"(일{fmt_rent(d['d1']['delta'], True)} 주{fmt_rent(d['d7']['delta'], True)} 월{fmt_rent(d['d30']['delta'], True)})"
        )
        c = rec["wolse_conv"]
        dc = deltas["wolse_conv"]
        lines.append(
            f"환산 {fmt_money(c['conv'])} ({fmt_money(c['deposit'])}/{c['rent']}) "
            f"(일{fmt_money(dc['d1']['delta'], True)} 주{fmt_money(dc['d7']['delta'], True)} 월{fmt_money(dc['d30']['delta'], True)})"
        )
    else:
        lines.append("월세(보증금 조건 내) 매물 없음")
    return lines


def is_changed(rec: dict, deltas: dict) -> bool:
    """전일 대비 변동 여부: 최저가가 바뀌었거나, 매물이 새로 생겼거나 사라진 경우."""
    for key in ("jeonse", "wolse_rent", "wolse_conv"):
        d = deltas.get(key, {}).get("d1", {})
        if d.get("date") is None:  # 비교할 전일 기록 없음
            continue
        cur, prev = metric_value(rec, key), d.get("prev")
        if (cur is None) != (prev is None):
            return True
        if cur is not None and prev is not None and cur != prev:
            return True
    return False


def chunk_messages(blocks: list[list[str]], limit_bytes: int = 2500) -> list[str]:
    """ntfy 안드로이드(FCM) 는 알림 JSON 전체가 4000바이트를 넘으면 바이트 단위로 잘라 한글이 깨짐 → 여유 있게 2500바이트 단위로 나눔."""
    msgs, cur, size = [], [], 0
    for b in blocks:
        text = "\n".join(b)
        n = len(text.encode("utf-8")) + 2
        if cur and size + n > limit_bytes:
            msgs.append("\n\n".join(cur))
            cur, size = [], 0
        cur.append(text)
        size += n
    if cur:
        msgs.append("\n\n".join(cur))
    return msgs


def local_cfg() -> dict:
    """PC 실행용 local_config.json (없으면 빈 dict)."""
    p = ROOT / "local_config.json"
    if p.exists():
        try:
            with open(p, encoding="utf-8-sig") as f:
                return json.load(f)
        except Exception:  # noqa: BLE001
            return {}
    return {}


def send_ntfy(title: str, message: str, click: Optional[str] = None, priority: int = 3, tags=None):
    topic = (os.environ.get("NTFY_TOPIC") or local_cfg().get("ntfy_topic") or "").strip()
    if not topic:
        print("[ntfy] NTFY_TOPIC 미설정 — 알림 생략")
        return False
    server = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    payload = {"topic": topic, "title": title, "message": message, "priority": priority}
    if click:
        payload["click"] = click
    if tags:
        payload["tags"] = tags
    headers = {"Content-Type": "application/json"}
    token = (os.environ.get("NTFY_TOKEN") or local_cfg().get("ntfy_token") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = requests.post(server, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                      headers=headers, timeout=20)
    print(f"[ntfy] {r.status_code} {title}")
    return r.ok


# ---------------------------------------------------------------- 메인
def run(args) -> int:
    cfg = load_json(CONFIG_PATH, None)
    if not cfg:
        print("config/complexes.json 이 없습니다")
        return 2
    session = naver.make_session()
    today = now_kst().date().isoformat()
    print(f"[start] {now_kst().isoformat(timespec='seconds')}", flush=True)
    for k, v in naver.preflight(session).items():
        print(f"[preflight] {k}: {v}", flush=True)
    dashboard = (os.environ.get("DASHBOARD_URL") or local_cfg().get("dashboard_url") or "").strip()

    bands = area_bands(cfg)
    if not cfg.get("area_bands"):
        cfg["area_bands"] = DEFAULT_BANDS
    complexes = cfg.get("complexes", [])
    if args.only:
        complexes = [c for c in complexes if args.only in c["name"]]

    latest_entries, errors, blocks, config_changed = [], [], [], False
    changed_count = new_count = collected_count = 0

    for c in complexes:
        name = c["name"]
        # 1) 단지번호 해석
        if not c.get("complexNo"):
            best, cands = None, []
            # 1-a) 앱에서 붙인 공유 링크(naver.me 등)가 있으면 먼저 따라가서 번호 추출
            if c.get("url"):
                print(f"[url] {name} ← {c['url']}")
                try:
                    no_from_url = naver.resolve_complex_url(session, c["url"])
                except Exception as e:  # noqa: BLE001
                    no_from_url = None
                    errors.append(f"{name}: 링크 해석 실패 {e}")
                if no_from_url:
                    best = {"complexNo": no_from_url}
                    try:
                        info = naver.fetch_complex_info(session, no_from_url)
                        a = info.get("address") or {}
                        best["name"] = info.get("name") or ""
                        best["address"] = " ".join(x for x in (a.get("city"), a.get("division"), a.get("sector")) if x)
                    except Exception:  # noqa: BLE001
                        pass
                else:
                    errors.append(f"{name}: 링크에서 단지번호를 찾지 못해 이름으로 검색합니다 ({c['url']})")
            # 1-b) 이름 검색
            if not best:
                kw = c.get("search") or name
                print(f"[search] {name} ← '{kw}'")
                try:
                    cands = naver.search_complex(session, kw)
                    best = naver.pick_complex(cands, name, c.get("region", ""))
                except Exception as e:  # noqa: BLE001
                    best, cands = None, []
                    errors.append(f"{name}: 검색 실패 {e}")
            if not best:
                errors.append(f"{name}: 단지번호를 찾지 못했습니다. 앱에서 네이버 부동산 단지 URL로 등록해 주세요.")
                latest_entries.append({"complexNo": None, "name": name, "error": "단지번호 미확인",
                                       "region": c.get("region", "")})
                continue
            c["complexNo"] = str(best["complexNo"])
            if best.get("address"):
                c["address"] = best["address"]
            config_changed = True
            # 이미 같은 단지번호로 등록된 단지가 있으면 중복 → 새 항목 삭제
            dup = next((x for x in cfg["complexes"] if x is not c and str(x.get("complexNo") or "") == c["complexNo"]), None)
            if dup:
                errors.append(f"{name}: '{dup['name']}'와 같은 단지({c['complexNo']})라 중복 등록을 삭제했습니다.")
                cfg["complexes"] = [x for x in cfg["complexes"] if x is not c]
                continue
            if best.get("name"):
                c["naverName"] = best["name"]
                if c.get("auto_name"):  # 링크만으로 등록된 단지: 네이버 단지명을 이름으로 채움
                    taken = {x["name"] for x in cfg["complexes"] if x is not c}
                    c["name"] = name = best["name"] if best["name"] not in taken else f"{best['name']} ({c['complexNo']})"
                    c.pop("auto_name", None)
            print(f"  → complexNo={c['complexNo']} ({best.get('name')})")
            time.sleep(0.5)
        no = str(c["complexNo"])

        # 2) 매물 수집
        try:
            articles, source = naver.fetch_articles(session, no)
        except Exception as e:  # noqa: BLE001
            msg = f"{name}({no}): 수집 실패 — {e}"
            print("[error]", msg)
            errors.append(msg)
            hist = load_json(HISTORY_DIR / f"{no}.json", [])
            last = hist[-1] if hist else None
            latest_entries.append({"complexNo": no, "name": name, "error": str(e)[:200],
                                   "region": c.get("region", ""), "last": last})
            continue

        rec = summarize(articles, cfg)
        rec["date"] = today
        rec["source"] = source
        hist = load_json(HISTORY_DIR / f"{no}.json", [])
        deltas = compute_deltas(hist, rec, today)
        rec["deltas"] = deltas
        # 다른 평형대도 같은 방식으로 요약해 rec["bands"][key]에 저장 (앱에서 평형 선택용). 알림은 기본 평형대만.
        rec["bands"] = {}
        for b in bands:
            if b.get("default"):
                continue
            rb = summarize(articles, cfg, b["min"], b["max"])
            rb.pop("areas", None)
            hist_b = [dict(h["bands"][b["key"]], date=h["date"]) for h in hist if (h.get("bands") or {}).get(b["key"])]
            rb["deltas"] = compute_deltas(hist_b, rb, today)
            rec["bands"][b["key"]] = rb
        is_new = not any(h["date"] < today for h in hist)  # 오늘 처음 기록되는(신규 등록) 단지

        # 3) 저장 (같은 날짜는 교체)
        hist = [h for h in hist if h["date"] != today] + [rec]
        hist.sort(key=lambda h: h["date"])
        if not args.dry_run:
            save_json(HISTORY_DIR / f"{no}.json", hist)
            # 모든 평형의 매물을 저장 (앱이 선택한 평형대로 걸러서 보여줌)
            filtered = [a.to_dict() for a in articles]
            filtered.sort(key=lambda a: (a["trade"], a["rent"] if a["trade"] == "B2" else a["deposit"], a["deposit"]))
            save_json(ARTICLES_DIR / f"{no}.json", {"date": today, "complexNo": no, "name": name,
                                                    "articles": filtered})

        entry = {"complexNo": no, "name": name, "region": c.get("region", ""),
                 "address": c.get("address", ""), "today": rec, "history_len": len(hist),
                 "hidden": bool(c.get("hidden"))}
        latest_entries.append(entry)
        if not c.get("hidden"):  # 숨긴 단지는 수집·기록은 하되 알림에서 제외
            collected_count += 1
            if is_new:
                new_count += 1
                blocks.append([f"■ {name} (신규)"] + build_lines(name, rec, deltas)[1:])
            elif is_changed(rec, deltas):
                changed_count += 1
                blocks.append(build_lines(name, rec, deltas))
        w = rec["wolse_rent"]
        wtxt = f"{fmt_money(w['deposit'])}/{w['rent']}" if w else "—"
        print(f"[ok] {name} ({source}) 전용필터 {rec['counts']['in_area']}건 "
              f"전세 {fmt_money(metric_value(rec, 'jeonse'))} / 월세 {wtxt}")
        time.sleep(0.8)

    latest = {
        "generated_at": now_kst().isoformat(timespec="seconds"),
        "date": today,
        "settings": {k: cfg.get(k) for k in ("area_min_m2", "area_max_m2", "wolse_deposit_max_manwon", "conversion_rate_pct", "area_bands")},
        "complexes": latest_entries,
        "errors": errors,
    }
    if not args.dry_run:
        save_json(LATEST_PATH, latest)
        if config_changed or not load_json(CONFIG_PATH, {}).get("area_bands"):
            save_json(CONFIG_PATH, cfg)
    else:
        print(json.dumps(latest, ensure_ascii=False, indent=1)[:4000])

    # 4) 알림
    if not args.no_notify and not args.dry_run:
        d = now_kst()
        title_base = f"전월세 최저가 {d.month}/{d.day}"
        # 요약 한 줄 + 변동·신규 단지만 상세. 변동이 없으면 요약만 보냄.
        head = f"전일 대비 변동 {changed_count}개 · 신규 {new_count}개 · 수집 {collected_count}개 단지"
        if errors:
            head += f" · 오류 {len(errors)}건"
        if not blocks:
            blocks = [["변동된 단지가 없습니다. 자세한 시세는 앱에서 확인하세요."]]
        msgs = chunk_messages(blocks)
        for i, m in enumerate(msgs, 1):
            title = title_base if len(msgs) == 1 else f"{title_base} ({i}/{len(msgs)})"
            if i == 1:
                m = head + "\n\n" + m
            send_ntfy(title, m, click=dashboard or None, tags=["house"])
        if errors:
            send_ntfy("수집 오류 안내", "\n".join(errors)[:3500], click=dashboard or None,
                      priority=2, tags=["warning"])
    return 0


def main():
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:  # noqa: BLE001
        pass
    p = argparse.ArgumentParser()
    p.add_argument("--no-notify", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--only", default=None)
    args = p.parse_args()
    try:
        sys.exit(run(args))
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
