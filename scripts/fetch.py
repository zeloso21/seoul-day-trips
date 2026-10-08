#!/usr/bin/env python3
"""Fetch Gyeonggi / Incheon tourism data from the Korea Tourism Organization API.

Outputs (only overwritten when the corresponding fetch succeeds):
  data/en.json      English places + festivals (EngService2, supplemented by KorService2)
  data/ja.json      Japanese places + festivals (JpnService2, supplemented by KorService2)
  data/photos.json  Photo gallery (PhotoGalleryService1)

The API key is read from the TOUR_API_KEY environment variable and is never printed.
Only the Python standard library is used.
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = "https://apis.data.go.kr/B551011"
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
KST = ZoneInfo("Asia/Seoul")

# Legacy area code -> legal-dong region code (used as a fallback filter).
REGIONS = {
    "gyeonggi": {"areaCode": "31", "lDongRegnCd": "41"},
    "incheon": {"areaCode": "2", "lDongRegnCd": "28"},
}
AREA_TO_REGION = {v["areaCode"]: k for k, v in REGIONS.items()}
LDONG_TO_REGION = {v["lDongRegnCd"]: k for k, v in REGIONS.items()}

# Content type IDs of the foreign-language services.
FOREIGN_TYPES = {"attraction": "76", "culture": "78", "leisure": "75", "food": "82"}
FOREIGN_FESTIVAL_TYPE = "85"

# Major places that should always appear on the site. Coordinates and photos come from
# KorService2; names come from this table (Korean descriptions are never used).
MAJOR_PLACES = [
    # keyword (KorService2 search), region, category, English name, Japanese name
    ("수원화성", "gyeonggi", "attraction", "Suwon Hwaseong Fortress", "水原華城"),
    ("화성행궁", "gyeonggi", "attraction", "Hwaseong Haenggung Palace", "華城行宮"),
    ("한국민속촌", "gyeonggi", "attraction", "Korean Folk Village", "韓国民俗村"),
    ("에버랜드", "gyeonggi", "leisure", "Everland", "エバーランド"),
    ("남한산성", "gyeonggi", "attraction", "Namhansanseong Fortress", "南漢山城"),
    ("임진각", "gyeonggi", "attraction", "Imjingak Pyeonghwa-Nuri Park", "臨津閣平和ヌリ公園"),
    ("헤이리", "gyeonggi", "culture", "Heyri Art Valley", "ヘイリ芸術村"),
    ("쁘띠프랑스", "gyeonggi", "attraction", "Petite France", "プチフランス"),
    ("아침고요수목원", "gyeonggi", "attraction", "The Garden of Morning Calm", "朝の静けさ樹木園"),
    ("두물머리", "gyeonggi", "attraction", "Dumulmeori", "トゥムルモリ"),
    ("광명동굴", "gyeonggi", "attraction", "Gwangmyeong Cave", "光明洞窟"),
    ("서울대공원", "gyeonggi", "leisure", "Seoul Grand Park", "ソウル大公園"),
    ("제부도", "gyeonggi", "attraction", "Jebudo Island", "済扶島"),
    ("인천 차이나타운", "incheon", "attraction", "Incheon Chinatown", "仁川チャイナタウン"),
    ("송월동 동화마을", "incheon", "attraction", "Songwol-dong Fairy Tale Village", "松月洞童話村"),
    ("월미도", "incheon", "attraction", "Wolmido Island", "月尾島"),
    ("송도센트럴파크", "incheon", "attraction", "Songdo Central Park", "松島セントラルパーク"),
    ("전등사", "incheon", "attraction", "Jeondeungsa Temple", "伝灯寺"),
    ("강화 고인돌", "incheon", "attraction", "Ganghwa Dolmen Site", "江華支石墓"),
    ("을왕리해수욕장", "incheon", "attraction", "Eurwangni Beach", "乙旺里海水浴場"),
]

# Photo gallery search keywords with English / Japanese labels.
PHOTO_KEYWORDS = [
    ("수원화성", "gyeonggi", "Suwon Hwaseong", "水原華城"),
    ("남한산성", "gyeonggi", "Namhansanseong", "南漢山城"),
    ("가평", "gyeonggi", "Gapyeong", "加平"),
    ("양평", "gyeonggi", "Yangpyeong", "楊平"),
    ("파주", "gyeonggi", "Paju", "坡州"),
    ("포천", "gyeonggi", "Pocheon", "抱川"),
    ("용인", "gyeonggi", "Yongin", "龍仁"),
    ("광명동굴", "gyeonggi", "Gwangmyeong Cave", "光明洞窟"),
    ("인천", "incheon", "Incheon", "仁川"),
    ("강화", "incheon", "Ganghwa", "江華"),
    ("월미도", "incheon", "Wolmido", "月尾島"),
    ("송도", "incheon", "Songdo", "松島"),
    ("차이나타운", "incheon", "Chinatown", "チャイナタウン"),
]


class ApiError(Exception):
    pass


def get_key() -> str:
    key = os.environ.get("TOUR_API_KEY", "").strip()
    if not key:
        print("::error::TOUR_API_KEY is not set", file=sys.stderr)
        sys.exit(1)
    # data.go.kr issues both an "encoded" and a "decoded" key; normalise to decoded so
    # urlencode() does not double-encode it.
    if "%" in key:
        key = urllib.parse.unquote(key)
    return key


KEY = ""
CALLS = 0


def redact(text: str) -> str:
    if not KEY:
        return text
    for variant in {KEY, urllib.parse.quote(KEY, safe=""), urllib.parse.quote_plus(KEY)}:
        text = text.replace(variant, "***")
    return text


def call(service: str, op: str, **params) -> tuple[list[dict], int]:
    """Call one API operation and return (items, totalCount). Never logs the key."""
    global CALLS
    query = {
        "serviceKey": KEY,
        "MobileOS": "ETC",
        "MobileApp": "SeoulDayTrips",
        "_type": "json",
        **{k: v for k, v in params.items() if v is not None},
    }
    url = f"{BASE}/{service}/{op}?{urllib.parse.urlencode(query)}"
    last = None
    for attempt in range(3):
        try:
            CALLS += 1
            req = urllib.request.Request(url, headers={"User-Agent": "seoul-day-trips/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                # Gateway errors come back as XML, e.g. SERVICE_KEY_IS_NOT_REGISTERED_ERROR
                m = re.search(r"<returnAuthMsg>(.*?)</returnAuthMsg>|<resultMsg>(.*?)</resultMsg>", raw)
                msg = (m.group(1) or m.group(2)) if m else raw[:120]
                raise ApiError(f"non-JSON response: {msg}")
            if "response" not in payload:
                raise ApiError(f"unexpected payload: {str(payload)[:120]}")
            header = payload["response"].get("header", {})
            if header.get("resultCode") not in ("0000", "00", None):
                raise ApiError(f"{header.get('resultCode')} {header.get('resultMsg')}")
            body = payload["response"].get("body") or {}
            items = body.get("items") or {}
            if isinstance(items, dict):
                items = items.get("item") or []
            if isinstance(items, dict):
                items = [items]
            return list(items), int(body.get("totalCount") or 0)
        except (urllib.error.URLError, TimeoutError, ApiError, ValueError) as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise ApiError(redact(f"{service}/{op} failed: {last}"))


def call_all(service: str, op: str, page_size: int = 100, max_pages: int = 30, **params) -> list[dict]:
    out: list[dict] = []
    for page in range(1, max_pages + 1):
        items, total = call(service, op, numOfRows=page_size, pageNo=page, **params)
        out.extend(items)
        if not items or len(out) >= total:
            break
    return out


def in_region(item: dict, region: str) -> bool:
    """True unless the item's own codes say it belongs somewhere else."""
    area, ldong = str(item.get("areacode") or ""), str(item.get("lDongRegnCd") or "")
    if not area and not ldong:
        return True
    return AREA_TO_REGION.get(area) == region or LDONG_TO_REGION.get(ldong) == region


def call_region(service: str, op: str, region: str, **params) -> list[dict]:
    """Query by legacy areaCode AND by lDongRegnCd and merge the results.

    Newer records may carry only the legal-dong code, so filtering by areaCode alone
    misses them (seen with searchFestival2). Items whose own codes point to another
    region are dropped, in case a service ignores one of the filters.
    """
    codes = REGIONS[region]
    merged: dict[str, dict] = {}
    for area in ({"areaCode": codes["areaCode"]}, {"lDongRegnCd": codes["lDongRegnCd"]}):
        try:
            items = call_all(service, op, **area, **params)
        except ApiError:
            if not merged and "lDongRegnCd" in area:
                raise
            continue
        for it in items:
            if in_region(it, region):
                merged.setdefault(str(it.get("contentid")), it)
    return list(merged.values())


# ---------------------------------------------------------------- normalisation

def https(url: str | None) -> str:
    if not url:
        return ""
    return re.sub(r"^http://", "https://", url.strip())


def strip_html(text: str | None) -> str:
    if not text:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return re.sub(r"[ \t]+", " ", text).strip()


def first_href(text: str | None) -> str:
    if not text:
        return ""
    m = re.search(r'href=["\']?([^"\' >]+)', text)
    if m:
        return m.group(1)
    m = re.search(r"https?://\S+", text)
    return m.group(0) if m else ""


def to_float(v) -> float | None:
    try:
        f = float(v)
        return f if f else None
    except (TypeError, ValueError):
        return None


def region_of(item: dict, fallback: str) -> str:
    return (
        LDONG_TO_REGION.get(str(item.get("lDongRegnCd", "")))
        or AREA_TO_REGION.get(str(item.get("areacode", "")))
        or fallback
    )


def place_from(item: dict, category: str, region: str, sigungu: dict) -> dict | None:
    lat, lng = to_float(item.get("mapy")), to_float(item.get("mapx"))
    title = (item.get("title") or "").strip()
    if not title:
        return None
    reg = region_of(item, region)
    return {
        "id": str(item.get("contentid", "")),
        "title": title,
        "category": category,
        "region": reg,
        "city": city_of(sigungu, reg, str(item.get("sigungucode") or ""), str(item.get("lDongSignguCd") or "")),
        "addr": " ".join(x for x in (item.get("addr1"), item.get("addr2")) if x).strip(),
        "tel": strip_html(item.get("tel")),
        "img": https(item.get("firstimage")),
        "thumb": https(item.get("firstimage2") or item.get("firstimage")),
        "lat": lat,
        "lng": lng,
    }


def distance_m(a: dict, b: dict) -> float:
    if None in (a.get("lat"), a.get("lng"), b.get("lat"), b.get("lng")):
        return float("inf")
    r = 6371000
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    dp, dl = p2 - p1, math.radians(b["lng"] - a["lng"])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


# ---------------------------------------------------------------- fetchers

def fetch_sigungu(service: str) -> dict:
    names: dict = {}
    for region, codes in REGIONS.items():
        try:
            items, _ = call(service, "areaCode2", areaCode=codes["areaCode"], numOfRows=100, pageNo=1)
            for it in items:
                names[(region, str(it.get("code")))] = (it.get("name") or "").strip()
        except ApiError as e:
            print(f"::warning::{service} areaCode2 ({region}): {e}")
        # Newer records carry only legal-dong codes (lDongSignguCd); map those too.
        try:
            items, _ = call(service, "ldongCode2", lDongRegnCd=codes["lDongRegnCd"], lDongListYn="N",
                            numOfRows=100, pageNo=1)
            for it in items:
                code = str(it.get("lDongSignguCd") or it.get("code") or "")
                name = (it.get("lDongSignguNm") or it.get("name") or "").strip()
                if code and name:
                    names[("ld", region, code)] = name
        except ApiError as e:
            print(f"::warning::{service} ldongCode2 ({region}): {e}")
    print(f"  {service} city names: {sum(1 for k in names if k[0] != 'ld')} legacy, "
          f"{sum(1 for k in names if k[0] == 'ld')} legal-dong")
    return names


def city_of(sigungu: dict, region: str, legacy: str, ldong: str) -> str:
    return sigungu.get((region, legacy)) or sigungu.get(("ld", region, ldong)) or ""


def fetch_places(service: str, sigungu: dict) -> list[dict]:
    places: dict[str, dict] = {}
    for region in REGIONS:
        for category, ctype in FOREIGN_TYPES.items():
            items = call_region(service, "areaBasedList2", region, contentTypeId=ctype, arrange="A")
            for it in items:
                p = place_from(it, category, region, sigungu)
                if p and p["id"] not in places:
                    places[p["id"]] = p
            print(f"  {service} {region}/{category}: {len(items)}")
    return list(places.values())


def fetch_festivals(service: str, today: str, sigungu: dict, overview: bool = True) -> list[dict]:
    # Ask for events starting up to three years ago so long-running festivals that started
    # earlier are included, then keep only those whose end date is today or later.
    since = (datetime.strptime(today, "%Y%m%d") - timedelta(days=3 * 365)).strftime("%Y%m%d")
    out: dict[str, dict] = {}
    for region in REGIONS:
        items = call_region(service, "searchFestival2", region, eventStartDate=since, arrange="A")
        kept = 0
        for it in items:
            end = str(it.get("eventenddate") or "")
            if not re.fullmatch(r"\d{8}", end) or end < today:
                continue
            p = place_from(it, "festival", region, sigungu)
            if not p:
                continue
            p["start"] = str(it.get("eventstartdate") or "")
            p["end"] = end
            p["sigungu"] = str(it.get("sigungucode") or "")
            out[p["id"]] = p
            kept += 1
        latest = max((str(it.get("eventenddate") or "") for it in items), default="-")
        print(f"  {service} festivals {region}: {kept}/{len(items)} upcoming (latest end {latest})")
    festivals = sorted(out.values(), key=lambda f: (f["start"], f["end"]))
    # Overview + homepage for each festival (small list, so detail calls are affordable).
    for f in festivals[:150]:
        try:
            items, _ = call(service, "detailCommon2", contentId=f["id"], numOfRows=1, pageNo=1)
        except ApiError as e:
            print(f"::warning::detailCommon2 {f['id']}: {e}")
            continue
        if items:
            if overview:
                f["overview"] = strip_html(items[0].get("overview"))[:600]
            f["homepage"] = first_href(items[0].get("homepage"))
    for f in festivals:
        f.pop("sigungu", None)
    return festivals


def fetch_korean_festivals(today: str) -> list[dict]:
    """Upcoming festivals from KorService2: name, dates, location, photo and homepage only.

    The Korean overview is not kept. The sigungu code is kept so each language can
    resolve the city name from its own areaCode2 table.
    """
    since = (datetime.strptime(today, "%Y%m%d") - timedelta(days=3 * 365)).strftime("%Y%m%d")
    out: dict[str, dict] = {}
    for region in REGIONS:
        items = call_region("KorService2", "searchFestival2", region, eventStartDate=since, arrange="A")
        kept = 0
        for it in items:
            end = str(it.get("eventenddate") or "")
            if not re.fullmatch(r"\d{8}", end) or end < today:
                continue
            p = place_from(it, "festival", region, {})
            if not p:
                continue
            p.update(id=f"ko-{p['id']}", start=str(it.get("eventstartdate") or ""), end=end,
                     sigungu=str(it.get("sigungucode") or ""), ldong=str(it.get("lDongSignguCd") or ""))
            out[p["id"]] = p
            kept += 1
        latest = max((str(it.get("eventenddate") or "") for it in items), default="-")
        print(f"  KorService2 festivals {region}: {kept}/{len(items)} upcoming (latest end {latest})")
    if not out:
        # Diagnostic: is the gap regional, or does the API have no upcoming festivals at all?
        try:
            _, nationwide = call("KorService2", "searchFestival2", eventStartDate=today, numOfRows=1, pageNo=1)
            print(f"  KorService2 festivals starting today or later, nationwide: {nationwide}")
        except ApiError as e:
            print(f"::warning::KorService2 nationwide festival check: {e}")
    festivals = sorted(out.values(), key=lambda f: (f["start"], f["end"]))
    for f in festivals[:150]:
        try:
            items, _ = call("KorService2", "detailCommon2", contentId=f["id"][3:], numOfRows=1, pageNo=1)
        except ApiError as e:
            print(f"::warning::KorService2 detailCommon2 {f['id']}: {e}")
            continue
        if items:
            f["homepage"] = first_href(items[0].get("homepage"))
    return festivals


HANGUL = re.compile(r"[\uac00-\ud7a3]")


def norm_name(text: str) -> str:
    """Festival title without year / edition prefixes, spaces and punctuation."""
    text = re.sub(r"^\s*(\d{4}\s*년?|제\s*\d+\s*회)\s*", "", text)
    text = re.sub(r"^\s*(\d{4}\s*년?|제\s*\d+\s*회)\s*", "", text)  # "2026 제12회 ..."
    return re.sub(r"[\s\W_]+", "", text).lower()


def load_festival_names() -> dict[str, dict]:
    path = Path(__file__).with_name("festival_names.json")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"::warning::festival_names.json not loaded: {e}")
        return {}
    return {norm_name(k): v for k, v in raw.items() if not k.startswith("_") and isinstance(v, dict)}


FESTIVAL_NAMES: dict[str, dict] = {}


def translate_festival(title: str, lang: str) -> str | None:
    """English/Japanese name from festival_names.json, or None if there is no entry."""
    n = norm_name(title)
    if not n:
        return None
    key = n if n in FESTIVAL_NAMES else max(
        (k for k in FESTIVAL_NAMES if len(k) >= 3 and k in n), key=len, default=None)
    name = FESTIVAL_NAMES.get(key, {}).get(lang) if key else None
    if not name:
        return None
    year = (re.match(r"\s*(?:제\s*\d+\s*회\s*)?(20\d\d)(?!\d)", title)
            or re.search(r"(?<!\d)(20\d\d)\s*$", title))
    return f"{year.group(1)} {name}" if year else name


def supplement_festivals(festivals: list[dict], korean: list[dict], sigungu: dict, lang: str) -> int:
    """Add KorService2 festivals that the foreign-language list does not already have."""
    added = 0
    for k in korean:
        dup = any(distance_m(k, f) < 500 and f["start"] <= k["end"] and k["start"] <= f["end"]
                  for f in festivals)
        if dup:
            continue
        f = {key: v for key, v in k.items() if key not in ("sigungu", "ldong")}
        f["city"] = city_of(sigungu, k["region"], k["sigungu"], k["ldong"])
        f["addr"] = ""  # Korean-only address is not useful to the target audience
        f["source"] = "kor"
        f.pop("ko", None)
        name = translate_festival(k["title"], lang)
        if name:
            f["title"], f["title_ko"] = name, k["title"]
        elif HANGUL.search(k["title"]):
            f["ko"] = True  # shown with its Korean name and a "Korean-language listing" note
        festivals.append(f)
        added += 1
    festivals.sort(key=lambda f: (f["start"], f["end"]))
    return added


def fetch_korean_major() -> list[dict]:
    """Coordinates / photos for MAJOR_PLACES from KorService2 (no Korean text kept)."""
    found = []
    missing: list[str] = []
    for keyword, region, category, en, ja in MAJOR_PLACES:
        items: list[dict] = []
        codes = REGIONS[region]
        # Try the keyword as written and without spaces, by areaCode then by lDongRegnCd.
        for kw in dict.fromkeys((keyword, keyword.replace(" ", ""))):
            for area in ({"areaCode": codes["areaCode"]}, {"lDongRegnCd": codes["lDongRegnCd"]}):
                try:
                    items, _ = call("KorService2", "searchKeyword2", keyword=kw, arrange="A",
                                    numOfRows=10, pageNo=1, **area)
                except ApiError as e:
                    print(f"::warning::KorService2 '{keyword}': {e}")
                    items = []
                if items:
                    break
            if items:
                break
        if not items:
            missing.append(keyword)
            continue
        needle = keyword.replace(" ", "")
        best = next((it for it in items if needle in (it.get("title") or "").replace(" ", "")), items[0])
        lat, lng = to_float(best.get("mapy")), to_float(best.get("mapx"))
        if lat is None or lng is None:
            continue
        found.append({
            "id": f"ko-{best.get('contentid')}",
            "names": {"en": en, "ja": ja},
            "category": category,
            "region": region,
            "img": https(best.get("firstimage")),
            "thumb": https(best.get("firstimage2") or best.get("firstimage")),
            "lat": lat,
            "lng": lng,
        })
    print(f"  KorService2 major places resolved: {len(found)}/{len(MAJOR_PLACES)}"
          + (f" (not found: {', '.join(missing)})" if missing else ""))
    return found


def supplement(places: list[dict], major: list[dict], lang: str) -> int:
    added = 0
    for m in major:
        if any(distance_m(m, p) < 400 for p in places):
            continue  # already covered by the foreign-language service
        places.append({
            "id": m["id"],
            "title": m["names"][lang],
            "category": m["category"],
            "region": m["region"],
            "city": "",
            "addr": "",
            "tel": "",
            "img": m["img"],
            "thumb": m["thumb"],
            "lat": m["lat"],
            "lng": m["lng"],
            "supplement": True,
        })
        added += 1
    return added


def fetch_photos() -> list[dict]:
    photos: dict[str, dict] = {}
    for keyword, region, en, ja in PHOTO_KEYWORDS:
        try:
            items, _ = call("PhotoGalleryService1", "gallerySearchList1",
                            keyword=keyword, arrange="A", numOfRows=12, pageNo=1)
        except ApiError as e:
            print(f"::warning::PhotoGallery '{keyword}': {e}")
            continue
        for it in items:
            gid = str(it.get("galContentId") or "")
            img = https(it.get("galWebImageUrl"))
            if not gid or not img or gid in photos:
                continue
            photos[gid] = {
                "id": gid,
                "img": img,
                "region": region,
                "label": {"en": en, "ja": ja},
                "month": str(it.get("galPhotographyMonth") or ""),
                "photographer": (it.get("galPhotographer") or "").strip(),
            }
    print(f"  PhotoGallery: {len(photos)} photos")
    return list(photos.values())


# ---------------------------------------------------------------- output

def load_json(name: str) -> dict:
    try:
        return json.loads((DATA / name).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def write_json(name: str, data: dict) -> None:
    path = DATA / name
    old = load_json(name)
    # Don't bump "updated" (and create a commit) when nothing but the timestamp changed.
    if old and {k: v for k, v in old.items() if k != "updated"} == {k: v for k, v in data.items() if k != "updated"}:
        print(f"  {name}: unchanged")
        return
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"  {name}: written")


def is_kor(f: dict) -> bool:
    return f.get("source") == "kor" or bool(f.get("ko")) or str(f.get("id", "")).startswith("ko-")


def main() -> int:
    global KEY
    KEY = get_key()
    FESTIVAL_NAMES.update(load_festival_names())
    DATA.mkdir(exist_ok=True)
    now = datetime.now(KST)
    today = now.strftime("%Y%m%d")
    updated = now.isoformat(timespec="minutes")
    print(f"Run date (KST): {today}")
    failures = 0

    try:
        major = fetch_korean_major()
    except Exception as e:  # noqa: BLE001
        print(f"::warning::KorService2 failed: {redact(str(e))}")
        major = []

    try:
        korean_festivals = fetch_korean_festivals(today)
    except Exception as e:  # noqa: BLE001
        print(f"::warning::KorService2 festivals failed, reusing previous: {redact(str(e))}")
        korean_festivals = None

    for lang, service in (("en", "EngService2"), ("ja", "JpnService2")):
        print(f"[{lang}] {service}")
        try:
            sigungu = fetch_sigungu(service)
            places = fetch_places(service, sigungu)
            try:
                festivals = fetch_festivals(service, today, sigungu)
            except ApiError as e:
                # Keep the previous festival list, minus events that have ended since.
                print(f"::warning::{lang} festivals kept from previous run: {e}")
                festivals = [f for f in load_json(f"{lang}.json").get("festivals", [])
                             if f.get("end", "") >= today and not is_kor(f)]
            if not places:
                raise ApiError("no places returned")
            if korean_festivals is None:
                # Reuse last run's Korean-sourced festivals that have not ended yet.
                festivals += [f for f in load_json(f"{lang}.json").get("festivals", [])
                              if is_kor(f) and f.get("end", "") >= today
                              and f["id"] not in {x["id"] for x in festivals}]
            else:
                n = supplement_festivals(festivals, korean_festivals, sigungu, lang)
                named = sum(1 for f in festivals if f.get("title_ko"))
                print(f"  festivals supplemented from KorService2: {n} ({named} with translated names)")
            added = supplement(places, major, lang)
            print(f"  supplemented from KorService2: {added}")
            places.sort(key=lambda p: (p["region"], p["category"], p["title"]))
            write_json(f"{lang}.json", {"updated": updated, "places": places, "festivals": festivals})
        except Exception as e:  # noqa: BLE001 - keep the previous file on any failure
            failures += 1
            print(f"::warning::{lang}.json kept as-is: {redact(str(e))}")

    print("[photos] PhotoGalleryService1")
    try:
        photos = fetch_photos()
        if not photos:
            raise ApiError("no photos returned")
        write_json("photos.json", {"updated": updated, "photos": photos})
    except Exception as e:  # noqa: BLE001
        failures += 1
        print(f"::warning::photos.json kept as-is: {redact(str(e))}")

    print(f"API calls: {CALLS}, failed outputs: {failures}")
    # Exit 0 so the (possibly older) site still deploys; failures show up as warnings.
    return 0


if __name__ == "__main__":
    sys.exit(main())
