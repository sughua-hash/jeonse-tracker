#!/data/data/com.termux/files/usr/bin/bash
# 백그라운드 데몬: ① 매일 RUN_AT(기본 10:00, 폰 시간) 이후, 그 시각 이후로 수집이 성공할 때까지 RETRY_SEC(기본 10분) 간격 재시도
#                    (RUN_AT 전에 앱 ⟳ 로 수집했더라도 정기 수집은 따로 돈다)
#                 ② 앱의 [⟳ 지금 수집]·[✉ 문자 보기] 요청(ntfy 채널 "<ntfy_topic>-cmd")을 30초마다 확인해 처리
#                    메시지 본문이 "sms [개수]" 면 문자 보기(sms_report.py), 그 외는 수집 요청
# 사용: ./daemon.sh (시작) | ./daemon.sh restart (코드 갱신 후) | ./daemon.sh stop
cd "$(dirname "$0")"
mkdir -p logs
PIDF=logs/daemon.pid
export DAEMON_VER=5   # run_termux.sh 가 logs/daemon.version 과 비교해 구버전 데몬이면 자동 재시작
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
export RETRY_SEC="${RETRY_SEC:-600}"
export MAX_TRIES="${MAX_TRIES:-24}"   # 하루 정기 시도 상한 (폭주 방지)
nohup bash -c '
  cd "'"$(pwd)"'"
  export PATH="/data/data/com.termux/files/usr/bin:$PATH"
  echo $$ > logs/daemon.pid
  echo "$DAEMON_VER" > logs/daemon.version
  topic=$(python -c "import json;print(json.load(open(\"local_config.json\")).get(\"ntfy_topic\",\"\"))" 2>/dev/null)
  cmd_topic=""; [ -n "$topic" ] && cmd_topic="${topic}-cmd"
  repo=$(python -c "import json;print(json.load(open(\"local_config.json\")).get(\"repo\",\"sughua-hash/jeonse-tracker\"))" 2>/dev/null)
  since=$(date +%s); last_run=0; last_try=0; tries=0; try_day=""
  echo "$(date "+%F %T") 데몬 v$DAEMON_VER 시작 · 매일 $RUN_AT 이후 성공할 때까지 ${RETRY_SEC}초 간격 재시도 · 즉시수집 채널 ${cmd_topic:-없음}" >> logs/daemon.log
  while true; do
    now=$(date +%s); today=$(date +%F); reason=""
    run_ts=$(date -d "today $RUN_AT" +%s 2>/dev/null)
    ok_ts=$(cat logs/last_success.ts 2>/dev/null); ok_ts=${ok_ts:-0}
    [ "$today" != "$try_day" ] && { try_day=$today; tries=0; }
    # 정기 수집: 예정 시각이 지났고, "그 시각 이후로" 성공한 적이 없고, 마지막 시도로부터 RETRY_SEC 이 지났으면 (재시도 포함)
    if [ -n "$run_ts" ] && [ "$now" -ge "$run_ts" ] && [ "$ok_ts" -lt "$run_ts" ] \
       && [ $((now - last_try)) -ge "$RETRY_SEC" ] && [ "$tries" -lt "$MAX_TRIES" ]; then
      reason="정기"; last_try=$now; tries=$((tries+1))
    fi
    if [ -z "$reason" ] && [ -n "$cmd_topic" ]; then
      out=$(curl -s -m 20 "https://ntfy.sh/${cmd_topic}/json?poll=1&since=${since}" 2>/dev/null)
      if [ $? -eq 0 ]; then
        since=$now
        # 메시지 본문으로 명령 구분: "sms [개수]" 는 문자 보기, 그 외(collect …)는 수집 요청
        cmds=$(printf "%s" "$out" | python -c "
import sys, json
for l in sys.stdin:
    l = l.strip()
    if not l: continue
    try: d = json.loads(l)
    except Exception: continue
    if d.get(\"event\") == \"message\": print((d.get(\"message\") or \"collect\").strip())" 2>/dev/null)
        sms_n=""
        while IFS= read -r line; do
          [ -z "$line" ] && continue
          case "$line" in
            sms*) n=$(printf "%s" "$line" | awk "{print \$2}"); sms_n=${n:-10} ;;
            *) reason="앱 요청" ;;
          esac
        done <<< "$cmds"
        if [ -n "$sms_n" ]; then
          echo "$(date "+%F %T") 문자 보기 요청 (${sms_n}개)" >> logs/daemon.log
          [ -f sms_report.py ] || curl -fsSL -m 40 -o sms_report.py "https://raw.githubusercontent.com/${repo:-sughua-hash/jeonse-tracker}/main/sms_report.py" 2>/dev/null
          python sms_report.py "$sms_n" >> logs/daemon.log 2>&1
        fi
      fi
    fi
    if [ -n "$reason" ]; then
      if [ "$reason" != "정기" ] && [ $((now - last_run)) -lt 120 ]; then
        echo "$(date "+%F %T") $reason 수집 요청 무시 (2분 내 재요청)" >> logs/daemon.log
      else
        last_run=$now
        echo "$(date "+%F %T") $reason 수집 시작" >> logs/daemon.log
        before=$(cat logs/last_success.ts 2>/dev/null); before=${before:-0}
        ./run_termux.sh >/dev/null 2>&1
        after=$(cat logs/last_success.ts 2>/dev/null); after=${after:-0}
        if [ "$after" -gt "$before" ]; then
          echo "$(date "+%F %T") 수집 완료" >> logs/daemon.log
        else
          echo "$(date "+%F %T") 수집 실패 (네트워크 등) — ${RETRY_SEC}초 뒤 재시도" >> logs/daemon.log
        fi
      fi
    fi
    sleep 30
  done
' >/dev/null 2>&1 &
echo "자동 수집 대기 시작 (pid $!) · 매일 $RUN_AT 이후 성공할 때까지 재시도 + 앱의 [⟳ 지금 수집] 요청"
