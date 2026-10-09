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
scripts/festival_names.json    KorService2 축제 이름 EN/JA 번역 테이블
scripts/place_names.json       KorService2로 보완할 주요 장소 + EN/JA 이름 테이블
.github/workflows/update-and-deploy.yml   매일 수집 → 커밋 → GitHub Pages 배포
```

### 수집 내용 (`scripts/fetch.py`)

- 대상 지역: 경기(areaCode 31)·인천(2). areaCode와 법정동 코드(lDongRegnCd 41/28) 양쪽으로 조회해 합침 (신규 데이터는 법정동 코드만 있는 경우가 있음)
- EN/JA: 관광지·문화시설·레포츠·음식 (`areaBasedList2`), 축제 (`searchFestival2` + `detailCommon2`로 개요/홈페이지)
- 축제: 실행 시점의 **KST 오늘 날짜**를 계산해 종료일 ≥ 오늘인 것만 저장 (프론트에서도 한 번 더 필터)
- KorService2 축제 보완: 영문/일문판 축제와 위치(500m)·기간이 겹치지 않는 경기·인천 축제를 추가. 이름(한국어)·기간·좌표·사진·홈페이지만 사용하고 한국어 개요·주소는 넣지 않음. 시·군 이름은 각 언어판 areaCode2/ldongCode2로 변환
  - 주요 축제 이름은 `scripts/festival_names.json` 번역 테이블로 영문/일문 이름을 붙이고, 원래 한국어 이름은 작게 함께 표시
  - 테이블 키는 연도·회차("2026", "제12회")를 뺀 한국어 이름. 공백·기호는 무시하고, 키를 포함하는 제목에도 매칭(가장 긴 키 우선). 원제의 연도는 번역명 앞에 유지
  - 테이블에 없고 한글이 들어간 이름은 한국어 그대로 두고 "Korean-language listing / 韓国語情報" 표시. Actions 실행 로그의 `festivals supplemented from KorService2: N (translated X, Korean name only Y)` 줄로 확인하고, Y가 0보다 크면 다음 줄 `not in festival_names.json:`에 나온 이름을 테이블에 추가
- KorService2 주요 장소 보완: `scripts/place_names.json` 번역 테이블(한국어 검색어 → 지역·카테고리·영문/일문 이름)의 각 장소를 KorService2에서 검색해, 영문/일문판에 400m 이내 장소, 또는 5km 이내에 같은 이름(EN/JA 이름이나 한국어 원명)이 없으면 추가. 좌표·사진·한국어 이름만 사용하고 한국어 설명은 넣지 않음. 표시 이름은 테이블의 EN/JA 이름
  - 검색 결과는 관광지·문화시설·레포츠·쇼핑 유형 중 이름이 정확히 같거나 앞에 짧은 지역명이 붙은 것("화성 융건릉", "강화 고인돌 유적")만 인정. 단순히 검색어를 포함하는 매장·부속시설·코스("올리브영 송도센트럴파크점")는 버리고, 못 찾으면 건너뜀(로그의 `not found`). 정확하지 않은 매칭은 로그에 `'키' -> 'API 이름'`으로 표시
  - 경기·인천 범위를 벗어난 좌표는 영문·일문 데이터 포함 모두 제외하고 로그 `Dropped`에 표시
  - API 표기가 다르면 항목에 `"aliases": ["대체 검색어", ...]`를 넣으면 차례로 검색. 못 찾은 항목은 로그에 `unmatched; API titles: ...`로 API가 돌려준 이름이 찍히니 그걸 보고 키나 aliases를 고치면 됨
- 장소 이름 정리: 영문/일문판 제목의 "English (한국어)" 형태는 이름과 한국어 원명(`title_ko`)으로 나눠, 사이트에서 한국어 원명을 작게 함께 표시 (현지인·택시 기사에게 보여주기 용도)
- PhotoGalleryService1: `PHOTO_KEYWORDS`의 경기·인천 키워드로 사진 수집
- 실패 처리: 해당 출력 파일은 덮어쓰지 않고 기존 파일 유지 (축제만 실패하면 이전 축제 목록에서 끝난 것만 제거). 내용이 같으면 파일을 다시 쓰지 않아 불필요한 커밋이 생기지 않음
- API가 응답하지 않으면 5회 연속 실패 후 나머지 호출을 즉시 건너뛰고(전체 실행 20분 제한, Actions 작업 30분 제한) 기존 파일을 그대로 배포
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
