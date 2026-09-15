#!/data/data/com.termux/files/usr/bin/bash
# 최신 코드 받기 (데이터 파일 충돌 없이). local_config.json 과 logs/ 는 유지됨.
cd "$(dirname "$0")"
git fetch -q origin && git reset -q --hard origin/main && chmod +x *.sh && echo "업데이트 완료 ($(git log -1 --format=%h))"
