#!/data/data/com.termux/files/usr/bin/python
"""앱의 [✉ 문자 보기] 요청에 응답: 집 폰에 온 최근 문자를 ntfy 로 보낸다.
사용: python sms_report.py [개수]   (기본 10, 최대 30)
필요: termux-api 패키지 + Termux:API 앱 + SMS 권한(최초 1회 폰에서 허용)."""
import json, os, shutil, subprocess, sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
_arg = sys.argv[1] if len(sys.argv) > 1 else ""
N = max(1, min(30, int(_arg))) if _arg.isdigit() else 10
LIMIT_BYTES = 3000  # ntfy 의 FCM 경로가 4000B 를 넘으면 바이트 단위로 잘라 한글이 깨지므로 여유를 둠


def local_cfg():
    try:
        return json.load(open("local_config.json", encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def post(title, message, tags=None, priority=3):
    cfg = local_cfg()
    topic = (os.environ.get("NTFY_TOPIC") or cfg.get("ntfy_topic") or "").strip()
    if not topic:
        print("[ntfy] ntfy_topic 미설정")
        return False
    import requests
    payload = {"topic": topic, "title": title, "message": message, "priority": priority}
    if tags:
        payload["tags"] = tags
    headers = {"Content-Type": "application/json"}
    token = (cfg.get("ntfy_token") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = requests.post(os.environ.get("NTFY_SERVER", "https://ntfy.sh"),
                      data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers=headers, timeout=20)
    return r.ok


def read_sms(n):
    if not shutil.which("termux-sms-list"):
        return None, "termux-api 가 설치되지 않았습니다. 집 폰에서 `pkg install termux-api` 를 실행해 주세요."
    try:
        out = subprocess.run(["termux-sms-list", "-l", str(n), "-n", "-d", "-t", "inbox"],
                             capture_output=True, text=True, timeout=40)
    except subprocess.TimeoutExpired:
        return None, "문자 읽기 시간 초과 — 집 폰 화면에 SMS 권한 요청이 떠 있을 수 있습니다. 허용해 주세요."
    raw = (out.stdout or "").strip()
    try:
        arr = json.loads(raw)
    except Exception:  # noqa: BLE001
        return None, "문자를 읽지 못했습니다. 집 폰에서 Termux:API 의 SMS 권한을 확인해 주세요.\n" + (raw or out.stderr or "")[:300]
    return arr if isinstance(arr, list) else [], None


def fmt(arr):
    arr = sorted(arr, key=lambda m: m.get("received") or "", reverse=True)  # 최신 먼저
    parts = []
    for m in arr:
        who = m.get("number") or m.get("sender") or "?"
        when = (m.get("received") or "")[5:16]  # "2026-09-29 14:03:21" → "09-29 14:03"
        body = " ".join((m.get("body") or "").split())
        parts.append(f"■ {when} · {who}\n{body}")
    text, used = [], 0
    for p in parts:
        b = len(p.encode("utf-8")) + 2
        if used + b > LIMIT_BYTES:
            text.append("… (이하 생략)")
            break
        text.append(p)
        used += b
    return "\n\n".join(text)


def main():
    arr, err = read_sms(N)
    if err:
        post("집 폰 문자 — 읽기 실패", err, tags=["warning"], priority=4)
        print("[sms] " + err)
        return 1
    if not arr:
        post("집 폰 문자", "받은 문자가 없습니다.", tags=["envelope"])
        print("[sms] 문자 없음")
        return 0
    ok = post(f"집 폰 문자 · 최근 {len(arr)}개", fmt(arr), tags=["envelope"])
    print(f"[sms] {len(arr)}개 전송 {'성공' if ok else '실패'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
