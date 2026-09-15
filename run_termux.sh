#!/data/data/com.termux/files/usr/bin/bash
# 1회 수집: 앱에서 바꾼 단지 목록 내려받기 → 수집/알림 → GitHub 업로드
cd "$(dirname "$0")"
mkdir -p logs
LOG="logs/$(date +%Y%m%d).log"
{
  echo "===== $(date '+%Y-%m-%d %H:%M:%S') ====="
  python collector/publish.py pull
  python collector/collect.py
  python collector/publish.py push
  echo "done"
} >> "$LOG" 2>&1
tail -n 40 "$LOG"
