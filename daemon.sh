#!/data/data/com.termux/files/usr/bin/bash
# 매일 10:00(휴대폰 시간 기준)에 run_termux.sh 실행. 백그라운드로 계속 대기.
cd "$(dirname "$0")"
mkdir -p logs
if [ -f logs/daemon.pid ] && kill -0 "$(cat logs/daemon.pid)" 2>/dev/null; then
  echo "이미 실행 중 (pid $(cat logs/daemon.pid))"; exit 0
fi
RUN_AT="${RUN_AT:-10:00}"
nohup bash -c '
  cd "'"$(pwd)"'"
  echo $$ > logs/daemon.pid
  while true; do
    now=$(date +%s)
    target=$(date -d "today '"$RUN_AT"'" +%s)
    [ "$target" -le "$now" ] && target=$(date -d "tomorrow '"$RUN_AT"'" +%s)
    echo "$(date "+%F %T") 다음 실행: $(date -d @$target "+%F %T")" >> logs/daemon.log
    sleep $((target - now))
    ./run_termux.sh >/dev/null 2>&1
    echo "$(date "+%F %T") 수집 완료" >> logs/daemon.log
    sleep 60
  done
' >/dev/null 2>&1 &
echo "매일 $RUN_AT 자동 수집 대기 시작 (pid $!)"
