# jeonse-tracker

관심 아파트 단지의 전세·월세(보증금 5억 이하) 최저가를 매일 수집해 휴대폰 알림과 그래프로 보여주는 개인용 앱.
전용 83~85㎡ 기준. 설치 방법은 **SETUP.md** 참고.

- 수집: GitHub Actions, 매일 10:00 KST (`collector/collect.py`)
- 알림: ntfy (전일/전주/전월 대비 포함)
- 앱: GitHub Pages PWA (`index.html`) — 단지 추가/제거, 즉시 수집, 누적 그래프
