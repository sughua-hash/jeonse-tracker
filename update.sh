#!/data/data/com.termux/files/usr/bin/bash
# 최신 코드 받기 + 데몬 재시작. local_config.json 과 logs/ 는 유지됨.
# (평소에는 run_termux.sh 가 매 수집 전에 코드를 자동 갱신하므로, 데몬 자체를 바꿀 때만 필요)
{
  cd "$(dirname "$0")"
  git fetch -q origin && git reset -q --hard origin/main && chmod +x *.sh && echo "업데이트 완료 ($(git log -1 --format=%h))"
  exec ./daemon.sh restart
}
