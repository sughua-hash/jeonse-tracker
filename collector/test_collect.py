"""오프라인 테스트: 네이버 API를 모의 응답으로 대체하여 파싱/필터/비교/알림 로직 검증.
실행: python collector/test_collect.py
"""
from __future__ import annotations

import datetime as dt
import json
import os
import random
import shutil
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import naver  # noqa: E402
import collect  # noqa: E402


def test_price_parsing():
    assert naver.parse_price_manwon("7억 5,000") == 75000
    assert naver.parse_price_manwon("7억5,000") == 75000
    assert naver.parse_price_manwon("1억") == 10000
    assert naver.parse_price_manwon("5,000") == 5000
    assert naver.parse_price_manwon("12억3천") == 123000
    assert naver.parse_price_info("1억/150", "B2") == (10000, 150)
    assert naver.parse_price_info("5억 5,000/120", "B2") == (55000, 120)
    assert naver.parse_price_info("7억 2,000", "B1") == (72000, 0)
    assert collect.fmt_money(75000) == "7.5억"
    assert collect.fmt_money(100000) == "10억"
    assert collect.fmt_money(5000) == "5,000만"
    assert collect.fmt_money(-3000, True) == "▼3,000만"
    assert collect.fmt_money(20000, True) == "▲2억"
    assert collect.fmt_money(0, True) == "="
    assert collect.conv_price(10000, 150, 5.5) == 10000 + round(150 * 12 * 100 / 5.5)
    print("✓ 금액 파싱/포맷")


def mobile_payload(items, more="N"):
    return {"result": {"list": items, "moreDataYn": more, "totAtclCnt": len(items)}}


def item(no, trade, prc, spc2, flr="12/25", bld="101동"):
    return {"atclNo": no, "tradTpCd": trade, "tradTpNm": "전세" if trade == "B1" else "월세", "prcInfo": prc,
            "spc1": "112", "spc2": spc2, "flrInfo": flr, "bildNm": bld, "direction": "남향", "atclCfmYmd": "26.09.14",
            "atclFetrDesc": "테스트", "rltrNm": "테스트공인"}


def test_summarize_and_filters():
    arts = [
        item("1", "B1", "7억 5,000", "84.98"),
        item("2", "B1", "7억", "84.9"),          # 최저 전세
        item("3", "B1", "6억", "59.9"),          # 면적 밖 → 제외
        item("4", "B2", "1억/150", "84.9"),      # 월세액 최저
        item("5", "B2", "3억/100", "84.9"),      # 환산가 최저 (3억+100*12/5.5% = 5.18억) vs 4번 (1억+3.27억=4.27억)
        item("6", "B2", "6억/50", "84.9"),       # 보증금 초과 → 제외
        item("7", "B2", "5,000/200", "84.9"),
    ]
    cfg = {"area_min_m2": 83, "area_max_m2": 85, "wolse_deposit_max_manwon": 50000, "conversion_rate_pct": 5.5}
    session = mock.Mock()
    with mock.patch.object(naver, "_get") as g:
        g.return_value.json.return_value = mobile_payload(arts)
        parsed = naver.fetch_articles_mobile(session, "111")
    assert len(parsed) == 7
    rec = collect.summarize(parsed, cfg)
    assert rec["jeonse"]["price"] == 70000 and rec["jeonse"]["article"]["article_no"] == "2"
    assert rec["wolse_rent"]["rent"] == 100 and rec["wolse_rent"]["deposit"] == 30000
    # 환산가: 4번 = 10000 + 150*12*100/5.5 = 42727 / 5번 = 30000+21818=51818 / 7번 = 5000+43636=48636
    assert rec["wolse_conv"]["article"]["article_no"] == "4", rec["wolse_conv"]
    assert rec["counts"] == {"all": 7, "in_area": 6, "jeonse": 2, "wolse": 4, "wolse_ok": 3}
    print("✓ 면적/보증금 필터 및 최저가 선정")


def test_deltas():
    hist = [
        {"date": "2026-08-10", "jeonse": {"price": 80000}, "wolse_rent": {"rent": 160}, "wolse_conv": {"conv": 60000}},
        {"date": "2026-09-05", "jeonse": {"price": 76000}, "wolse_rent": {"rent": 150}, "wolse_conv": None},
        {"date": "2026-09-14", "jeonse": {"price": 73000}, "wolse_rent": None, "wolse_conv": {"conv": 55000}},
    ]
    today = {"jeonse": {"price": 70000}, "wolse_rent": {"rent": 150}, "wolse_conv": {"conv": 50000}}
    d = collect.compute_deltas(hist, today, "2026-09-15")
    assert d["jeonse"]["d1"] == {"date": "2026-09-14", "prev": 73000, "delta": -3000}
    assert d["jeonse"]["d7"]["date"] == "2026-09-05" and d["jeonse"]["d7"]["delta"] == -6000
    assert d["jeonse"]["d30"]["date"] == "2026-08-10" and d["jeonse"]["d30"]["delta"] == -10000
    assert d["wolse_rent"]["d1"]["delta"] is None          # 전일 월세 매물 없음 → 비교 불가
    assert d["wolse_conv"]["d7"]["delta"] is None          # 9/5 환산 없음
    assert d["wolse_conv"]["d30"]["delta"] == -10000
    print("✓ 전일/전주/전월 비교")


def test_search_pick():
    cands = [{"complexNo": "1", "name": "위례센트럴자이", "address": "경기도 성남시 수정구 창곡동"},
             {"complexNo": "2", "name": "센트럴자이", "address": "서울시 강남구"}]
    assert naver.pick_complex(cands, "위례센트럴자이", "경기 성남시 수정구")["complexNo"] == "1"
    assert naver.pick_complex(cands, "센트럴자이 (강남)", "서울 강남구")["complexNo"] == "2"
    print("✓ 단지 검색 후보 선택")


def test_notification_chunking():
    blocks = [["■ 단지%d" % i, "전세 7억 (일= 주= 월=)", "월세 1억/150 (일= 주= 월=)", "환산 4.3억 (일= 주= 월=)"] for i in range(26)]
    msgs = collect.chunk_messages(blocks, 3600)
    assert all(len(m.encode("utf-8")) <= 3600 for m in msgs)
    assert sum(m.count("■") for m in msgs) == 26
    print(f"✓ 알림 분할: {len(msgs)}개 메시지")


def test_end_to_end_with_fake_history(days=45):
    """가짜 히스토리를 만들어 전체 run() 흐름 검증 + 대시보드용 샘플 데이터 생성."""
    tmp = Path(tempfile.mkdtemp())
    cfg = json.loads((Path(__file__).parent.parent / "config" / "complexes.json").read_text(encoding="utf-8"))
    cfg["complexes"] = cfg["complexes"][:6]
    for i, c in enumerate(cfg["complexes"]):
        c["complexNo"] = str(100000 + i) if i != 5 else None   # 마지막 하나는 검색 경로 테스트
    (tmp / "config").mkdir(); (tmp / "config" / "complexes.json").write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")

    random.seed(7)
    today = dt.date(2026, 9, 15)
    # 과거 히스토리 생성
    for i, c in enumerate(cfg["complexes"][:5]):
        no = c["complexNo"]; hist = []
        base_j = random.randint(60000, 95000); base_r = random.randint(120, 220); base_d = random.randint(10000, 40000)
        for k in range(days, 0, -1):
            d = today - dt.timedelta(days=k)
            if random.random() < 0.1:
                continue
            j = base_j + random.randint(-8, 8) * 500
            r = base_r + random.randint(-3, 3) * 5
            rec = {"date": d.isoformat(), "source": "fake",
                   "jeonse": {"price": j, "article": {"article_no": "0", "building": "101동", "floor": "10/20"}},
                   "wolse_rent": {"rent": r, "deposit": base_d, "article": {"article_no": "0", "building": "102동", "floor": "5/20"}},
                   "wolse_conv": {"conv": collect.conv_price(base_d, r, 5.5), "rent": r, "deposit": base_d, "rate_pct": 5.5, "article": {"article_no": "0", "building": "102동", "floor": "5/20"}},
                   "counts": {"all": 30, "in_area": 20, "jeonse": 12, "wolse": 8, "wolse_ok": 6}}
            if random.random() < 0.08:
                rec["wolse_rent"] = None; rec["wolse_conv"] = None
            hist.append(rec)
        collect.save_json(tmp / "data" / "history" / f"{no}.json", hist)

    def fake_fetch(session, no):
        base = 60000 + (int(no) % 7) * 5000
        arts = [naver.Article(f"{no}-{k}", "B1", base + k * 1000, 0, 84.9, 112.0, f"{k+3}/25", f"10{k}동", "남향", "26.09.15", "", "테스트", "") for k in range(4)]
        arts += [naver.Article(f"{no}-w{k}", "B2", 10000 + k * 10000, 130 + k * 20, 84.7, 112.0, f"{k+2}/25", f"20{k}동", "남향", "26.09.15", "", "테스트", "1억/150") for k in range(3)]
        arts.append(naver.Article(f"{no}-x", "B1", 30000, 0, 59.9, 80.0, "3/25", "105동", "남향", "26.09.15", "", "", ""))
        if no == "100002":
            raise naver.NaverError("모의 오류")
        return arts, "mobile"

    sent = []
    with mock.patch.multiple(collect, CONFIG_PATH=tmp / "config" / "complexes.json", DATA_DIR=tmp / "data",
                             HISTORY_DIR=tmp / "data" / "history", ARTICLES_DIR=tmp / "data" / "articles",
                             LATEST_PATH=tmp / "data" / "latest.json"), \
         mock.patch.object(naver, "fetch_articles", side_effect=fake_fetch), \
         mock.patch.object(naver, "search_complex", return_value=[{"complexNo": "100005", "name": "남양주월산사랑으로부영2단지", "address": "경기도 남양주시 화도읍"}]), \
         mock.patch.object(collect, "send_ntfy", side_effect=lambda t, m, **k: sent.append((t, m)) or True), \
         mock.patch.object(collect, "now_kst", return_value=dt.datetime(2026, 9, 15, 10, 0, tzinfo=collect.KST)), \
         mock.patch.dict(os.environ, {"NTFY_TOPIC": "test"}):
        args = mock.Mock(only=None, dry_run=False, no_notify=False)
        assert collect.run(args) == 0

    latest = json.loads((tmp / "data" / "latest.json").read_text(encoding="utf-8"))
    assert latest["date"] == "2026-09-15"
    assert len(latest["complexes"]) == 6
    assert any(e.get("error") for e in latest["complexes"]), "오류 단지가 latest에 기록되어야 함"
    new_cfg = json.loads((tmp / "config" / "complexes.json").read_text(encoding="utf-8"))
    assert new_cfg["complexes"][5]["complexNo"] == "100005", "검색으로 찾은 단지번호가 config에 기록되어야 함"
    h0 = json.loads((tmp / "data" / "history" / "100000.json").read_text(encoding="utf-8"))
    assert h0[-1]["date"] == "2026-09-15" and h0[-1]["deltas"]["jeonse"]["d1"]["delta"] is not None
    assert sent and sent[0][0].startswith("전월세 최저가 9/15")
    assert any("수집 오류" in t for t, _ in sent)
    print("✓ 전체 실행 흐름 (수집→저장→비교→알림)")
    print("--- 알림 미리보기 ---")
    print(sent[0][1][:700])
    print("...")
    return tmp


if __name__ == "__main__":
    test_price_parsing()
    test_summarize_and_filters()
    test_deltas()
    test_search_pick()
    test_notification_chunking()
    out = test_end_to_end_with_fake_history()
    if "--keep" in sys.argv:
        dest = Path(sys.argv[sys.argv.index("--keep") + 1])
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(out, dest)
        print("샘플 데이터 →", dest)
    print("\n모든 테스트 통과")
