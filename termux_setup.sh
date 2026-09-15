#!/data/data/com.termux/files/usr/bin/bash
# 여유 안드로이드폰(Termux)에서 전월세 수집기를 돌리기 위한 1회 설정 스크립트.
# Termux에서:  curl -sL https://raw.githubusercontent.com/sughua-hash/jeonse-tracker/main/termux_setup.sh | bash
set -e
REPO_URL="https://github.com/sughua-hash/jeonse-tracker.git"
DIR="$HOME/jeonse-tracker"
export DEBIAN_FRONTEND=noninteractive

echo
echo "=== [1/5] 패키지 설치 (python, git) — 몇 분 걸릴 수 있습니다 ==="
yes | pkg update >/dev/null 2>&1 || true
yes | pkg install -y python git
python -m pip install --quiet --upgrade requests

echo
echo "=== [2/5] 프로그램 내려받기 ==="
if [ -d "$DIR/.git" ]; then
  git -C "$DIR" pull -q --rebase || true
else
  git clone -q "$REPO_URL" "$DIR"
fi
cd "$DIR"
chmod +x run_termux.sh daemon.sh 2>/dev/null || true

echo
echo "=== [3/5] 설정 ==="
if [ -f local_config.json ] && ! grep -q "여기에" local_config.json; then
  echo "기존 local_config.json 사용"
else
  echo "GitHub 토큰(github_pat_...)을 붙여넣고 엔터:"
  echo "  (붙여넣기: 화면 길게 누르기 → Paste / PASTE)"
  read -r TOKEN < /dev/tty
  TOKEN="$(echo "$TOKEN" | tr -d '[:space:]')"
  cat > local_config.json <<EOF
{
  "repo": "sughua-hash/jeonse-tracker",
  "branch": "main",
  "github_token": "$TOKEN",
  "ntfy_topic": "jeonse-4cdk3gbuv8",
  "dashboard_url": "https://sughua-hash.github.io/jeonse-tracker/"
}
EOF
  echo "저장됨: $DIR/local_config.json"
fi

echo
echo "=== [4/5] 재부팅 후 자동 시작 등록 (Termux:Boot 앱이 있으면 동작) ==="
mkdir -p "$HOME/.termux/boot"
cat > "$HOME/.termux/boot/jeonse.sh" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
termux-wake-lock
cd "$DIR" && ./daemon.sh
EOF
chmod +x "$HOME/.termux/boot/jeonse.sh"

echo
echo "=== [5/5] 첫 수집 실행 + 매일 10:00 대기 시작 ==="
termux-wake-lock 2>/dev/null || true
./run_termux.sh
./daemon.sh
echo
echo "완료! 이 Termux 창은 닫지 말고 홈 버튼으로 나가세요 (알림창에 Termux가 떠 있으면 정상)."
echo "로그: $DIR/logs/   상태 확인: cat ~/jeonse-tracker/logs/daemon.log"
