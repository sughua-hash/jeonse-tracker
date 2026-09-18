#!/data/data/com.termux/files/usr/bin/bash
# 안드로이드 작업 스케줄러에 점검 작업을 등록한다 (최초 1회만 실행).
# 준비물: F-Droid 에서 "Termux:API" 앱 설치 → 이 스크립트 실행
# 해제하려면: termux-job-scheduler --cancel --job-id 1001
cd "$(dirname "$0")"
DIR="$(pwd)"
export PATH="/data/data/com.termux/files/usr/bin:$PATH"

if ! command -v termux-job-scheduler >/dev/null 2>&1; then
  echo "termux-api 패키지를 설치합니다..."
  pkg install -y termux-api
fi
if ! command -v termux-job-scheduler >/dev/null 2>&1; then
  echo
  echo "termux-job-scheduler 를 찾지 못했습니다."
  echo "F-Droid 에서 'Termux:API' 앱을 설치한 뒤 이 스크립트를 다시 실행해 주세요."
  exit 1
fi

chmod +x jobcheck.sh daemon.sh run_termux.sh 2>/dev/null

termux-job-scheduler \
  --script "$DIR/jobcheck.sh" \
  --job-id 1001 \
  --period-ms 900000 \
  --persisted true \
  --network any \
  --battery-not-low false

echo
echo "── 등록된 작업 ──"
termux-job-scheduler --pending
echo
echo "완료: 안드로이드가 15분마다 깨워서 점검합니다 (재부팅해도 유지됩니다)."
echo "네트워크가 연결된 상태에서만 실행되므로 DNS 실패로 헛도는 일이 없습니다."
