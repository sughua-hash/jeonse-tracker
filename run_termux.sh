#!/data/data/com.termux/files/usr/bin/bash
# 1회 수집: 코드 자동 업데이트 → 앱에서 바꾼 단지 목록 내려받기 → 수집/알림 → GitHub 업로드
cd "$(dirname "$0")"
mkdir -p logs
LOG="logs/$(date +%Y%m%d).log"

# 0) 수집기 코드 자동 업데이트 (GitHub의 최신 collector/*.py, *.sh 만 받음. 데이터·local_config.json 은 건드리지 않음)
#    실패(오프라인 등)해도 기존 코드로 수집은 계속 진행. 새 스크립트로 자기 자신을 한 번 다시 실행.
if [ -z "$JT_UPDATED" ]; then
  if git fetch -q origin 2>>"$LOG" && git checkout -q origin/main -- collector run_termux.sh update.sh daemon.sh termux_setup.sh 2>>"$LOG"; then
    chmod +x *.sh
    echo "$(date '+%F %T') 코드 업데이트: $(git rev-parse --short origin/main)" >> "$LOG"
  else
    echo "$(date '+%F %T') 코드 업데이트 실패 — 기존 코드로 진행" >> "$LOG"
  fi
  JT_UPDATED=1 exec bash "$0" "$@"
fi

{
  echo "===== $(date '+%Y-%m-%d %H:%M:%S') ====="
  python collector/publish.py pull
  python collector/collect.py
  python collector/publish.py push
  echo "done"
} >> "$LOG" 2>&1
tail -n 40 "$LOG"

# 3) 데몬이 구버전(또는 꺼짐)이면 새 daemon.sh 로 자동 재시작 (수집 끝난 뒤라 안전)
want=$(grep -m1 '^export DAEMON_VER=' daemon.sh | sed 's/^export DAEMON_VER=\([0-9]*\).*/\1/')
have=$(cat logs/daemon.version 2>/dev/null)
if [ -n "$want" ] && { [ "$want" != "$have" ] || ! kill -0 "$(cat logs/daemon.pid 2>/dev/null)" 2>/dev/null; }; then
  echo "$(date '+%F %T') 데몬 재시작 (v${have:-?} → v$want)" >> "$LOG"
  ./daemon.sh restart >> "$LOG" 2>&1
fi
