# 전월세 최저가 추적 앱 — 설치 가이드

관심 단지(기본 26곳)의 **전용 83~85㎡ 전세·월세(보증금 5억 이하) 최저가**를 매일 오전 10시에 수집해
휴대폰으로 알림(전일·전주·전월 대비 포함)을 보내고, 누적 데이터를 그래프로 보여주는 개인용 앱입니다.

```
┌ GitHub Actions (매일 10:00 KST) ┐      ┌ ntfy 앱 (Android) ┐
│ collector/collect.py            │ ───▶ │ 최저가 알림        │
│  · 네이버 부동산 매물 조회       │      └───────────────────┘
│  · 전용면적/보증금 필터          │
│  · 전일/전주/전월 비교           │      ┌ 홈화면 앱 (PWA, GitHub Pages) ┐
│  · data/ 에 누적 저장 → commit   │ ───▶ │ 카드 목록 · 추이 그래프        │
└─────────────────────────────────┘      │ 단지 추가/제거 · 즉시 수집     │
                                         └────────────────────────────────┘
```

전부 무료 서비스만 사용하며, PC를 켜 두지 않아도 동작합니다. 준비물은 **GitHub 계정** 하나입니다.

---

## 1. GitHub 저장소 만들기 (약 5분)

1. https://github.com 로그인 → 우측 상단 **＋ → New repository**
2. Repository name: `jeonse-tracker` (다른 이름도 가능하지만 이 가이드는 이 이름 기준)
   - **Public** 선택 (GitHub Pages 무료 사용 조건)
   - 나머지 체크박스는 모두 비운 채 **Create repository**
3. 이 폴더(`jeonse-tracker`)의 파일을 업로드합니다. 두 가지 방법 중 하나:

   **방법 A — 웹 업로드 (Git 몰라도 됨)**
   저장소 화면의 *uploading an existing file* 링크 클릭 → 이 폴더 안의 **모든 파일과 폴더**를 드래그 → *Commit changes*.
   > `.github` 폴더처럼 점(.)으로 시작하는 폴더가 탐색기에서 숨김 처리되어 있으면 함께 선택되는지 확인하세요.
   > 웹 업로드로 `.github/workflows/daily.yml` 이 올라가지 않으면, 저장소에서 **Add file → Create new file** 로
   > 파일명 `.github/workflows/daily.yml` 을 만들고 내용을 붙여 넣으세요.

   **방법 B — Git 명령 (PC에 Git 설치된 경우)**
   ```bat
   cd jeonse-tracker
   git init
   git add .
   git commit -m "init"
   git branch -M main
   git remote add origin https://github.com/<내아이디>/jeonse-tracker.git
   git push -u origin main
   ```

## 2. GitHub Pages 켜기 (앱 주소 만들기)

저장소 → **Settings → Pages** → *Build and deployment* → Source: **Deploy from a branch** →
Branch: **main** / **/(root)** → Save.
1~2분 후 앱 주소가 생깁니다: `https://<내아이디>.github.io/jeonse-tracker/`

## 3. ntfy 알림 채널 만들기

1. Play 스토어에서 **ntfy** 설치 (무료, 광고 없음)
2. 앱에서 **＋ → Subscribe to topic** → 채널 이름 입력. 남이 추측하기 어려운 이름으로 만드세요.
   예: `jeonse-hong-7x3kq9`
3. GitHub 저장소 → **Settings → Secrets and variables → Actions → New repository secret**
   - Name: `NTFY_TOPIC`  /  Secret: 위에서 정한 채널 이름 → Add secret
4. (선택) 알림이 늦게 오면 ntfy 앱 설정에서 **Instant delivery** 를 켜세요 (배터리 최적화 예외).

## 4. 첫 수집 실행

저장소 → **Actions** 탭 → 좌측 **daily-collect** → 우측 **Run workflow → Run workflow**.
2~4분 뒤 완료되면:
- `config/complexes.json` 의 단지번호가 자동으로 채워지고
- `data/` 에 첫 기록이 생기며
- 휴대폰에 첫 알림이 옵니다 (첫날은 비교 데이터가 없어 `일— 주— 월—` 로 표시).

> Actions 탭에 "Workflows aren't being run on this forked repository" 같은 메시지가 있거나 워크플로가 보이지 않으면
> **Actions → I understand my workflows, go ahead and enable them** 을 누르세요.

## 5. 휴대폰 홈화면에 앱 설치

Android Chrome에서 `https://<내아이디>.github.io/jeonse-tracker/` 접속 → 메뉴(⋮) → **홈 화면에 추가** (또는 *앱 설치*).

## 6. 앱에서 단지 추가/제거·즉시 수집 쓰기 (GitHub 토큰 1회 등록)

앱이 저장소의 설정 파일을 직접 수정하려면 토큰이 필요합니다.

1. GitHub → 우측 상단 프로필 → **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**
2. Token name: `jeonse-app` / Expiration: 원하는 기간(최대 1년; 만료되면 재발급)
3. Repository access: **Only select repositories → jeonse-tracker**
4. Permissions → Repository permissions:
   - **Contents: Read and write**
   - **Actions: Read and write**
5. Generate → 토큰 문자열 복사 (`github_pat_…`)
6. 휴대폰 앱 → ⚙ 설정 → GitHub 토큰 붙여넣기, ntfy 채널 이름 입력 → 저장

이후 앱에서:
- **＋** : 단지 추가. 네이버 부동산 앱에서 단지 페이지 **공유 → 링크 복사**해 붙이면 가장 정확 (이름만 넣어도 다음 수집 때 자동 검색)
- 단지 상세 맨 아래 **추적 중단(제거)**
- ⚙ → **지금 수집 실행** / **ntfy 테스트 알림**
- ⚙ → **전월세 전환율** 변경 (환산가 계산 기준, 기본 5.5%)

---

## 알림 내용 읽는 법

```
■ 위례센트럴자이
전세 7.2억 (일▼3,000만 주▼5,000만 월=)      ← 전세 최저 보증금, 전일/전주/전월 대비
월세 1억/150 (일= 주▲10 월▲20)              ← 보증금 5억 이하 중 월세액 최저 (보증금/월세, 만원)
환산 4.27억 (1억/150) (일= 주▲0.2억 월▲…)    ← 보증금+월세×12÷전환율 로 전세가로 환산한 값이 최저인 매물
```
▼ 는 내려감(싸짐), ▲ 는 올라감, = 는 변동 없음, — 는 비교할 이전 데이터 없음.
비교 기준일은 정확히 1일/7일/30일 전이 아니어도 그 이전 가장 최근 기록을 사용합니다.

## 조건 바꾸기

`config/complexes.json` 상단 값을 수정하면 다음 수집부터 반영됩니다.

| 키 | 기본값 | 의미 |
|---|---|---|
| `area_min_m2` / `area_max_m2` | 83 / 85 | 전용면적 범위(㎡) |
| `wolse_deposit_max_manwon` | 50000 | 월세 보증금 상한(만원) = 5억 |
| `conversion_rate_pct` | 5.5 | 전월세 전환율(%) |

수집 시각을 바꾸려면 `.github/workflows/daily.yml` 의 `cron: "0 1 * * *"` (UTC 기준, 01:00 UTC = 10:00 KST)을 수정하세요.

## 문제 해결

**단지 하나가 "단지번호 확인 중"으로 남아 있음**
이름 검색으로 단지를 특정하지 못한 경우입니다. 네이버 부동산에서 해당 단지 링크를 복사해 앱의 ＋(단지 추가)에 URL로 다시 등록하거나,
`config/complexes.json` 에서 `"complexNo": "123456"` 을 직접 채워 넣으세요. 단지번호는 URL의 `complexes/123456` 또는 `complex/info/123456` 부분입니다.

**Actions 로그에 `HTTP 403` / 수집 실패가 전 단지에서 발생**
네이버가 GitHub 서버(해외 IP)의 접근을 막는 경우입니다. 이때는 같은 코드를 PC에서 돌립니다:
1. PC에 Python 3.10+ 설치 (python.org, *Add to PATH* 체크) 후 `pip install -r collector\requirements.txt`
2. `run_local.bat` 을 메모장으로 열어 `NTFY_TOPIC`, `DASHBOARD_URL` 값을 채움
3. Windows **작업 스케줄러** → 기본 작업 만들기 → 매일 10:00 → 프로그램: `run_local.bat` (시작 위치: 이 폴더)
4. `.github/workflows/daily.yml` 의 `schedule:` 두 줄을 지워 GitHub 쪽 자동 실행을 끕니다.
   (PC 실행도 결과를 GitHub에 push 하므로 앱과 알림은 그대로 동작합니다. PC가 꺼져 있는 날은 수집이 빠집니다.)

**알림이 안 옴**
GitHub → Settings → Secrets → `NTFY_TOPIC` 이름이 정확한지, ntfy 앱에서 같은 채널을 구독 중인지 확인. 앱 ⚙ → *ntfy 테스트 알림*으로 채널 자체를 점검할 수 있습니다.

**GitHub Actions 예약 실행이 몇 분~수십 분 늦음**
GitHub 예약 작업의 특성입니다(무료 플랜에서 지연 흔함). 저장소에 60일간 커밋이 없으면 예약이 자동 중지되는데, 이 앱은 매일 데이터를 커밋하므로 해당하지 않습니다.

## 파일 구성

```
index.html / manifest.webmanifest / sw.js / icons/ / vendor/   ← 휴대폰 앱 (GitHub Pages)
collector/collect.py   수집·비교·알림 본체        collector/naver.py   네이버 API 조회
collector/test_collect.py   오프라인 테스트 (python collector/test_collect.py)
config/complexes.json  추적 단지 목록과 조건 (앱에서 편집됨)
data/latest.json       최신 요약   data/history/<단지번호>.json  일별 누적   data/articles/  당일 매물
.github/workflows/daily.yml   매일 10:00 KST 실행
run_local.bat          PC에서 직접 수집할 때
```
