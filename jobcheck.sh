#!/data/data/com.termux/files/usr/bin/bash
# 안드로이드 작업 스케줄러(termux-job-scheduler)가 주기적으로 부르는 점검 스크립트.
#   ① 데몬이 꺼져 있으면 되살리고
#   ② 오늘 수집이 아직 성공하지 못했으면 수집을 실행한다.
# 안드로이드가 직접 깨워주므로 Termux 프로세스가 죽거나 재부팅해도 계속 동작한다.
# 최초 등록: ./setup_job.sh
cd "$(dirname "$0")"
mkdir -p logs data
export PATH="/data/data/com.termux/files/usr/bin:$PATH"
export HOME="${HOME:-/data/data/com.termux/files/home}"
LOG="logs/$(date +%Y%m%d).log"
RUN_AT="${RUN_AT:-10:00}"

echo "$(date '+%F %T') [작업] 점검 시작" >> "$LOG"

# 1) 데몬 생존 확인 — 꺼져 있으면 재시작 (앱의 ⟳ 즉시수집 기능이 데몬을 필요로 함)
pid=$(cat logs/daemon.pid 2>/dev/null)
if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; then
  echo "$(date '+%F %T') [작업] 데몬이 꺼져 있어 재시작합니다" >> "$LOG"
  ./daemon.sh restart >> "$LOG" 2>&1
fi

# 2) 오늘 수집이 아직 성공하지 않았고 예정 시각이 지났으면 수집 실행
now=$(date +%s)
run_ts=$(date -d "today $RUN_AT" +%s 2>/dev/null)
ok=$(cat logs/last_success.date 2>/dev/null)
if [ -n "$run_ts" ] && [ "$now" -ge "$run_ts" ] && [ "$ok" != "$(date +%F)" ]; then
  echo "$(date '+%F %T') [작업] 오늘 수집이 아직 안 됐습니다 — 실행" >> "$LOG"
  ./run_termux.sh >/dev/null 2>&1
  if [ "$(cat logs/last_success.date 2>/dev/null)" = "$(date +%F)" ]; then
    echo "$(date '+%F %T') [작업] 수집 성공" >> "$LOG"
  else
    echo "$(date '+%F %T') [작업] 수집 실패 — 다음 점검 때 재시도" >> "$LOG"
  fi
else
  echo "$(date '+%F %T') [작업] 할 일 없음 (오늘 수집 완료: ${ok:-없음})" >> "$LOG"
fi
exit 0
