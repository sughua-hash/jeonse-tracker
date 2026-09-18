#!/data/data/com.termux/files/usr/bin/bash
# 1회 수집: 코드 자동 업데이트 → 앱에서 바꾼 단지 목록 내려받기 → 수집/알림 → GitHub 업로드
# 성공하면 logs/last_success.date 에 오늘 날짜를 기록한다 (데몬·작업 스케줄러가 재시도 판단에 사용)
cd "$(dirname "$0")"
mkdir -p logs data
export PATH="/data/data/com.termux/files/usr/bin:$PATH"
LOG="logs/$(date +%Y%m%d).log"

# 0) 중복 실행 방지 — 데몬과 안드로이드 작업 스케줄러가 동시에 부를 수 있음
LOCKPID=$(cat logs/run.lock 2>/dev/null)
if [ -n "$LOCKPID" ] && [ "$LOCKPID" != "$$" ] && kill -0 "$LOCKPID" 2>/dev/null; then
  echo "$(date '+%F %T') 이미 수집 중 (pid $LOCKPID) — 이번 호출은 건너뜀" >> "$LOG"
  exit 0
fi
echo $$ > logs/run.lock
trap 'rm -f logs/run.lock' EXIT

# 1) 네트워크 준비 대기 — 절전(Doze)에서 깨어난 직후엔 DNS 가 잠시 안 되는 경우가 있음 (최대 2분)
if [ -z "$JT_UPDATED" ]; then
  for i in 1 2 3 4 5 6 7 8; do
    curl -fsS -m 8 -o /dev/null "https://api.github.com/zen" 2>/dev/null && break
    [ "$i" = 1 ] && echo "$(date '+%F %T') 네트워크 대기 중…" >> "$LOG"
    sleep 15
  done
fi

# 2) 수집기 코드 자동 업데이트 — git 없이 GitHub raw 에서 파일을 직접 받음 (인증·터미널 불필요, 오프라인이면 기존 코드로 진행)
REPO=$(python -c "import json;print(json.load(open('local_config.json')).get('repo','sughua-hash/jeonse-tracker'))" 2>/dev/null)
RAW="https://raw.githubusercontent.com/${REPO:-sughua-hash/jeonse-tracker}/main"
FILES="collector/collect.py collector/naver.py collector/publish.py run_termux.sh update.sh daemon.sh termux_setup.sh jobcheck.sh setup_job.sh"
if [ -z "$JT_UPDATED" ]; then
  ok=0; fail=0; changed=""
  for f in $FILES; do
    tmp="$f.new"
    if curl -fsSL --retry 2 -m 40 -H 'Cache-Control: no-cache' "$RAW/$f?t=$(date +%s)" -o "$tmp" 2>>"$LOG" && [ -s "$tmp" ]; then
      case "$f" in *.py) if ! python -m py_compile "$tmp" 2>>"$LOG"; then rm -f "$tmp"; fail=$((fail+1)); continue; fi ;; esac
      if cmp -s "$tmp" "$f"; then rm -f "$tmp"; else mv -f "$tmp" "$f"; changed="$changed $f"; fi
      ok=$((ok+1))
    else
      rm -f "$tmp"; fail=$((fail+1))
    fi
  done
  chmod +x *.sh 2>/dev/null
  UPDATE_MSG="확인 ${ok}개 · 실패 ${fail}개 · 변경:${changed:- 없음}"
  echo "$(date '+%F %T') 코드 업데이트: $UPDATE_MSG" >> "$LOG"
  JT_UPDATED=1 JT_UPDATE_MSG="$UPDATE_MSG" exec bash "$0" "$@"
fi

RC=1; PRC=1
{
  echo "===== $(date '+%Y-%m-%d %H:%M:%S') ====="
  python collector/publish.py pull
  python collector/collect.py; RC=$?
  # 수집기 상태 파일 (앱/원격 진단용) — 데이터와 함께 업로드됨
  python - "$RC" "${JT_UPDATE_MSG:-}" <<'PY'
import json, sys, hashlib, datetime, os
def md5(p):
    try: return hashlib.md5(open(p,'rb').read()).hexdigest()[:8]
    except Exception: return None
def rd(p):
    try: return open(p).read().strip()
    except Exception: return None
json.dump({
  "at": datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat(timespec="seconds"),
  "collect_exit": int(sys.argv[1]), "update": sys.argv[2],
  "daemon_version": rd("logs/daemon.version"), "daemon_pid_alive": (lambda p: bool(p) and os.path.exists(f"/proc/{p}"))(rd("logs/daemon.pid")),
  "prev_success": rd("logs/last_success.date"),
  "files": {f: md5(f) for f in ["collector/collect.py","collector/naver.py","collector/publish.py","run_termux.sh","daemon.sh","jobcheck.sh"]},
}, open("data/collector_status.json","w"), ensure_ascii=False, indent=1)
PY
  python collector/publish.py push; PRC=$?
  if [ "$RC" = 0 ] && [ "$PRC" = 0 ]; then
    date +%F > logs/last_success.date
    echo "done (수집 성공 · 업로드 성공)"
  else
    echo "done (collect exit $RC · push exit $PRC) — 실패, 나중에 자동 재시도됩니다"
  fi
} >> "$LOG" 2>&1
tail -n 40 "$LOG"

# 3) 데몬이 구버전(또는 꺼짐)이면 새 daemon.sh 로 자동 재시작 (수집 끝난 뒤라 안전)
want=$(grep -m1 '^export DAEMON_VER=' daemon.sh | sed 's/^export DAEMON_VER=\([0-9]*\).*/\1/')
have=$(cat logs/daemon.version 2>/dev/null)
if [ -n "$want" ] && { [ "$want" != "$have" ] || ! kill -0 "$(cat logs/daemon.pid 2>/dev/null)" 2>/dev/null; }; then
  echo "$(date '+%F %T') 데몬 재시작 (v${have:-?} → v$want)" >> "$LOG"
  ./daemon.sh restart >> "$LOG" 2>&1
fi
