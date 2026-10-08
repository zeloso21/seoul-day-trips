# Seoul Day Trips

외국인 여행자를 위한 서울 근교(경기도·인천) 관광 정적 사이트입니다. English / 日本語.

데이터: 한국관광공사 Tour API (EngService2, JpnService2, KorService2, PhotoGalleryService1)
— Source: Korea Tourism Organization (KOGL)

## 구조

```
index.html                     단일 페이지 (탐색·지도 / 축제 / 사진 / 서울에서 가는 법)
assets/app.js                  바닐라 JS: 언어 전환, 필터, 지도, 축제, 갤러리
assets/i18n.js                 UI 문구 + "Getting there" 교통 안내 (EN/JA)
assets/style.css               모바일 우선 반응형 스타일
assets/vendor/leaflet/         Leaflet 1.9.4 + markercluster 1.5.3 (CDN 의존 없이 포함)
data/en.json, data/ja.json     장소(places)·축제(festivals) — fetch.py가 생성
data/photos.json               사진 갤러리 — fetch.py가 생성
scripts/fetch.py               API 수집 스크립트 (표준 라이브러리만 사용)
.github/workflows/update-and-deploy.yml   매일 수집 → 커밋 → GitHub Pages 배포
```

### 수집 내용 (`scripts/fetch.py`)

- 대상 지역: 경기(areaCode 31)·인천(2). areaCode와 법정동 코드(lDongRegnCd 41/28) 양쪽으로 조회해 합침 (신규 데이터는 법정동 코드만 있는 경우가 있음)
- EN/JA: 관광지·문화시설·레포츠·음식 (`areaBasedList2`), 축제 (`searchFestival2` + `detailCommon2`로 개요/홈페이지)
- 축제: 실행 시점의 **KST 오늘 날짜**를 계산해 종료일 ≥ 오늘인 것만 저장 (프론트에서도 한 번 더 필터)
- KorService2 축제 보완: 영문/일문판 축제와 위치(500m)·기간이 겹치지 않는 경기·인천 축제를 추가. 이름(한국어)·기간·좌표·사진·홈페이지만 사용하고 한국어 개요·주소는 넣지 않음. 사이트에는 "Korean-language listing / 韓国語情報" 표시. 시·군 이름은 각 언어판 areaCode2로 변환
- KorService2: 영문/일문판에 없는 주요 장소(스크립트 내 `MAJOR_PLACES`)를 보완. 좌표·사진만 사용하고 이름은 표의 EN/JA 이름 사용, 한국어 설명은 넣지 않음
- PhotoGalleryService1: `PHOTO_KEYWORDS`의 경기·인천 키워드로 사진 수집
- 실패 처리: 해당 출력 파일은 덮어쓰지 않고 기존 파일 유지 (축제만 실패하면 이전 축제 목록에서 끝난 것만 제거). 내용이 같으면 파일을 다시 쓰지 않아 불필요한 커밋이 생기지 않음
- 인증키는 `TOUR_API_KEY` 환경변수에서만 읽고, 오류 메시지에서도 마스킹

## 수동 실행

### 로컬

```bash
export TOUR_API_KEY='발급받은 키'   # Encoding/Decoding 키 모두 가능
python3 scripts/fetch.py
python3 -m http.server 8000       # http://localhost:8000
```

### GitHub Actions

저장소 Secret `TOUR_API_KEY`가 필요합니다.

- 자동: 매일 04:17 KST (`cron: 17 19 * * *` UTC)
- 수동: **Actions → Update data & deploy → Run workflow** (workflow_dispatch)
- `main`에 사이트 파일을 푸시해도 실행됩니다 (`data/`, README 변경은 제외)

워크플로는 fetch → `data/` 변경 시 봇 커밋 → Pages 배포 순으로 동작합니다.
Pages 소스는 **Settings → Pages → Build and deployment → Source: GitHub Actions** 입니다.

## 라이선스 / 출처

- 관광 데이터·사진: 한국관광공사, 공공누리(KOGL) 조건에 따라 출처 표시
- 지도: © OpenStreetMap contributors
- Leaflet (BSD-2-Clause), Leaflet.markercluster (MIT) — `assets/vendor/leaflet/LICENSE-*`
