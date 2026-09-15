#!/data/data/com.termux/files/usr/bin/bash
# 백그라운드 데몬: ① 매일 RUN_AT(기본 10:00, 폰 시간)에 정기 수집
#                 ② 앱의 [⟳ 지금 수집] 요청(ntfy 채널 "<ntfy_topic>-cmd")을 30초마다 확인해 즉시 수집
# 사용: ./daemon.sh (시작) | ./daemon.sh restart (코드 갱신 후) | ./daemon.sh stop
cd "$(dirname "$0")"
mkdir -p logs
PIDF=logs/daemon.pid
stop_daemon(){
  if [ -f "$PIDF" ] && kill -0 "$(cat "$PIDF")" 2>/dev/null; then kill "$(cat "$PIDF")" 2>/dev/null; sleep 1; echo "이전 데몬 종료 (pid $(cat "$PIDF"))"; fi
  rm -f "$PIDF"
}
case "$1" in
  stop) stop_daemon; exit 0 ;;
  restart) stop_daemon ;;
  *) if [ -f "$PIDF" ] && kill -0 "$(cat "$PIDF")" 2>/dev/null; then echo "이미 실행 중 (pid $(cat "$PIDF")) · 재시작은 ./daemon.sh restart"; exit 0; fi ;;
esac
command -v termux-wake-lock >/dev/null 2>&1 && termux-wake-lock 2>/dev/null
export RUN_AT="${RUN_AT:-10:00}"
nohup bash -c '
  cd "'"$(pwd)"'"
  echo $$ > logs/daemon.pid
  topic=$(python -c "import json;print(json.load(open(\"local_config.json\")).get(\"ntfy_topic\",\"\"))" 2>/dev/null)
  cmd_topic=""; [ -n "$topic" ] && cmd_topic="${topic}-cmd"
  next=$(date -d "today $RUN_AT" +%s); [ "$next" -le "$(date +%s)" ] && next=$(date -d "tomorrow $RUN_AT" +%s)
  since=$(date +%s); last_run=0
  echo "$(date "+%F %T") 데몬 시작 · 다음 정기 수집 $(date -d @$next "+%F %T") · 즉시수집 채널 ${cmd_topic:-없음}" >> logs/daemon.log
  while true; do
    now=$(date +%s); reason=""
    if [ "$now" -ge "$next" ]; then reason="정기"; next=$(date -d "tomorrow $RUN_AT" +%s); fi
    if [ -z "$reason" ] && [ -n "$cmd_topic" ]; then
      out=$(curl -s -m 20 "https://ntfy.sh/${cmd_topic}/json?poll=1&since=${since}" 2>/dev/null)
      if [ $? -eq 0 ]; then since=$now; echo "$out" | grep -q "\"event\":\"message\"" && reason="앱 요청"; fi
    fi
    if [ -n "$reason" ]; then
      if [ "$reason" != "정기" ] && [ $((now - last_run)) -lt 120 ]; then
        echo "$(date "+%F %T") $reason 수집 요청 무시 (2분 내 재요청)" >> logs/daemon.log
      else
        last_run=$now
        echo "$(date "+%F %T") $reason 수집 시작" >> logs/daemon.log
        ./run_termux.sh >/dev/null 2>&1
        echo "$(date "+%F %T") 수집 완료" >> logs/daemon.log
      fi
    fi
    sleep 30
  done
' >/dev/null 2>&1 &
echo "자동 수집 대기 시작 (pid $!) · 매일 $RUN_AT 정기 + 앱의 [⟳ 지금 수집] 요청"
