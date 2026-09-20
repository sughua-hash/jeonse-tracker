#!/data/data/com.termux/files/usr/bin/bash
# 최신 코드 받기 + 데몬 재시작 (수집은 하지 않음). local_config.json 과 logs/ 는 그대로 유지된다.
# 이 폰은 git fetch 가 동작하지 않아 예전의 `git reset --hard` 방식은 오히려 옛 코드로 되돌리는 사고를 냈다.
# 그래서 run_termux.sh 와 똑같이 GitHub raw 에서 파일을 직접 받는 방식으로 바꿨다.
# 자기 자신(update.sh)도 갱신 대상이므로 전체를 { } 로 묶어 실행 중 파일이 바뀌어도 안전하게 한다.
{
  cd "$(dirname "$0")"
  export PATH="/data/data/com.termux/files/usr/bin:$PATH"
  REPO=$(python -c "import json;print(json.load(open('local_config.json')).get('repo','sughua-hash/jeonse-tracker'))" 2>/dev/null)
  RAW="https://raw.githubusercontent.com/${REPO:-sughua-hash/jeonse-tracker}/main"
  FILES="collector/collect.py collector/naver.py collector/publish.py run_termux.sh update.sh daemon.sh termux_setup.sh jobcheck.sh setup_job.sh"
  ok=0; fail=0; changed=""
  for f in $FILES; do
    tmp="$f.new"
    if curl -fsSL --retry 2 -m 40 -H 'Cache-Control: no-cache' "$RAW/$f?t=$(date +%s)" -o "$tmp" && [ -s "$tmp" ]; then
      case "$f" in *.py) if ! python -m py_compile "$tmp" >/dev/null 2>&1; then rm -f "$tmp"; fail=$((fail+1)); continue; fi ;; esac
      if cmp -s "$tmp" "$f"; then rm -f "$tmp"; else mv -f "$tmp" "$f"; changed="$changed $f"; fi
      ok=$((ok+1))
    else
      rm -f "$tmp"; fail=$((fail+1))
    fi
  done
  chmod +x *.sh 2>/dev/null
  echo "업데이트: 확인 ${ok}개 · 실패 ${fail}개 · 변경:${changed:- 없음}"
  [ "$fail" -gt 0 ] && echo "(일부 파일을 못 받았습니다. 인터넷 확인 후 다시 실행해 주세요 — 기존 코드는 그대로 둡니다)"
  exec ./daemon.sh restart
}
