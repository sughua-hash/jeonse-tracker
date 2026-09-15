@echo off
REM PC에서 직접 수집할 때 (GitHub Actions가 네이버에 차단될 경우 대안)
REM 사용 전: pip install -r collector\requirements.txt
cd /d %~dp0
set NTFY_TOPIC=여기에_ntfy_채널이름
set DASHBOARD_URL=https://사용자이름.github.io/jeonse-tracker/
python collector\collect.py
git add data config
git commit -m "data: local %date% %time%"
git pull --rebase origin main
git push
