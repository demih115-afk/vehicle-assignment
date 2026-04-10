# -*- coding: utf-8 -*-
"""더숲국어전문학원 차량배정 웹앱 v2"""
import streamlit as st
import json, math, os, re, ssl, urllib.parse, urllib.request
from datetime import datetime, date, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE_DIR, "data", "routes.json")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

DAY_KR = {0: "월", 1: "화", 2: "수", 3: "목", 4: "금", 5: "토", 6: "일"}

# ─── 학교 목록 (울산 중구 + 북구) ───
SCHOOLS = [
    # 고등학교
    "가온고", "강동고", "다운고", "달천고", "매곡고", "무룡고", "성신고",
    "약사고", "울산고", "울산동천고", "울산마이스터고", "울산스포츠과학고",
    "울산에너지고", "울산애니원고", "울산외국어고", "울산중앙고",
    "학성여고", "함월고", "호계고", "화봉고", "효정고",
    # 중학교
    "강동중", "고헌중", "농소중", "다운중", "달천중", "매곡중", "무룡중",
    "남외중", "상안중", "성안중", "약사중", "연암중", "외솔중", "울산스포츠과학중",
    "이화중", "장현중", "진장중", "학성여중", "화봉중", "효정중",
    # 초등학교
    "강동초", "고헌초", "굴화초", "내황초", "달천초", "매곡초",
    "명촌초", "무룡초", "무릉초", "반구초", "백양초", "병영초",
    "복산초", "상안초", "성안초", "신정초", "양사초", "약사초",
    "외솔초", "우정초", "유곡초", "이화초", "장현초", "진장초",
    "천상초", "태화초", "학성초", "함월초", "화봉초", "효정초",
]

# 학교 별칭 → 정식명
SCHOOL_ALIASES = {
    "울고": "울산고", "울산고등학교": "울산고",
    "학성고": "학성여고", "학성고등학교": "학성여고",
    "함고": "함월고", "함월고등학교": "함월고",
    "중앙고": "울산중앙고", "중앙고등학교": "울산중앙고",
    "성신고등학교": "성신고",
    "가온고등학교": "가온고",
    "약사고등학교": "약사고",
    "애니원고": "울산애니원고",
}

# 학년 목록
GRADES = [
    "초1", "초2", "초3", "초4", "초5", "초6",
    "중1", "중2", "중3",
    "고1", "고2", "고3",
    "재수생",
]

# 수업시간 (표시 → 데이터키)
TIME_SLOTS = []
for h in range(8, 23):
    for m in [0, 30]:
        ampm = "오전" if h < 12 else "오후"
        display_h = h if h <= 12 else h - 12
        if h == 12:
            display_h = 12
        label = f"{display_h}:{m:02d}"
        # 데이터 키: 12시 이하는 그대로, 13시 이상은 -12
        data_key = f"{h - 12 if h > 12 else h}:{m:02d}"
        TIME_SLOTS.append((label, data_key))

# 수업장소 (선택명 → 출력명)
LOCATIONS = {
    "본원 (더숲3관/에스지/IBSI/엠플본관)": "본원",
    "더숲1관 (신한은행 4층)": "더숲1관(신한은행 4층)",
    "더숲2관 (피자스쿨)": "더숲2관(피자스쿨)",
    "엠플2관 (피자스쿨)": "엠플2관(피자스쿨)",
    "더숲국어 (알레르망 2층)": "더숲국어(알레르망 2층, 래미안 맞은편)",
}

ALL_DAYS = ["월", "화", "수", "목", "금", "토"]


# ─── 데이터 ───
SPREADSHEET_ID = "1hfD9VdH1u2AQVER85CEMGBeB4BI-D-w3LLO2g6uH_s8"
VEHICLE_INFO = {
    0: {"number": 1, "area": "유곡동/우정동/태화동/센트리지", "driver": "박준성", "phone": "010-6677-9775"},
    1: {"number": 2, "area": "강변E편한/반구동/새치(학성동)", "driver": "서병진", "phone": "010-6566-7921"},
    2: {"number": 3, "area": "명촌동/학성초/반구동/남외동", "driver": "하수복", "phone": "010-4584-7036"},
    3: {"number": 5, "area": "복산동/약사동/래미안", "driver": "유종근", "phone": "010-6579-0441"},
    4: {"number": 6, "area": "성안동(성안초 방면)/센트리지", "driver": "김종철", "phone": "010-2850-0841"},
    5: {"number": 7, "area": "성안동(백양초 방면)/장현동", "driver": "박석칠", "phone": "010-6570-6243"},
    6: {"number": 8, "area": "서동/병영성/산전/약사아이파크", "driver": "김철현", "phone": "010-9332-2419"},
}
NAVER_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://map.naver.com/"}


def _get_gsheet_credentials():
    """Google Sheets 인증 (Streamlit Cloud 시크릿 또는 로컬 JSON)"""
    from google.oauth2.service_account import Credentials
    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    try:
        info = dict(st.secrets.get("gcp_service_account", {}))
        if info:
            return Credentials.from_service_account_info(info, scopes=scopes)
    except Exception:
        pass
    sa_path = os.path.join(BASE_DIR, "gen-lang-client-0025269547-abb95bd564f8.json")
    if os.path.exists(sa_path):
        return Credentials.from_service_account_info(
            json.load(open(sa_path)), scopes=scopes)
    return None


def _get_naver_coords(url):
    """네이버 지도 링크에서 좌표 추출"""
    if not url:
        return None, None
    try:
        ctx = ssl.create_default_context()
        if "/place/" in url:
            pid = re.search(r"/place/(\d+)", url).group(1)
            api = f"https://map.naver.com/p/api/place/summary/{pid}"
            req = urllib.request.Request(api, headers=NAVER_HEADERS)
            with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
                d = json.loads(resp.read())
                c = d["data"]["placeDetail"]["coordinate"]
                return c["latitude"], c["longitude"]
        elif "/bus-station/" in url:
            sid = re.search(r"/bus-station/(\d+)", url).group(1)
            api = f"https://map.naver.com/p/api/pubtrans/bus/stops/{sid}"
            req = urllib.request.Request(api, headers=NAVER_HEADERS)
            with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
                d = json.loads(resp.read())
                return d["point"]["y"], d["point"]["x"]
    except Exception:
        pass
    return None, None


def _format_schedule_key(val):
    """시간대 셀 → 스케줄 키 변환"""
    if not val:
        return None, False
    s = str(val).strip()
    is_sat = "토요일" in s
    s = s.replace("토요일", "").strip()
    m = re.search(r"(\d{1,2}):?(\d{2})?", s)
    if not m:
        return None, is_sat
    h, mn = int(m.group(1)), m.group(2) or "00"
    time_str = f"{h}:{mn}"
    day_m = re.search(r"[(\uff08]([^\)\uff09]+)[)\uff09]", s)
    day_suffix = ""
    if day_m:
        day_suffix = f"_{day_m.group(1).replace('.','').replace(',','').replace(' ','')}"
    return f"{time_str}{day_suffix}", is_sat


def _format_time_val(val):
    """엑셀 시간값 → HH:MM"""
    if not val:
        return ""
    s = str(val).strip()
    m = re.match(r"(\d{1,2}):(\d{2})", s)
    if m:
        return f"{int(m.group(1))}:{m.group(2)}"
    return s


@st.cache_data(ttl=300)  # 5분 캐시
def load_data_from_sheets():
    """Google Sheets에서 실시간으로 코스표 읽기 + 좌표 매핑"""
    creds = _get_gsheet_credentials()
    if not creds:
        # fallback: 로컬 routes.json
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    from googleapiclient.discovery import build
    service = build("sheets", "v4", credentials=creds)

    # 기존 좌표 캐시 로드 (좌표는 자주 안 바뀌니까)
    coord_cache = {}
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            old = json.load(f)
            for v in old.get("vehicles", []):
                for stype in ["weekday", "saturday"]:
                    for key, stops in v[stype].items():
                        for s in stops:
                            if s.get("lat") and s.get("map_url"):
                                coord_cache[s["map_url"]] = (s["lat"], s["lng"])

    # 시트 목록
    meta = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    sheets = meta["sheets"]

    vehicles = []
    for idx, sheet in enumerate(sheets):
        info = VEHICLE_INFO.get(idx)
        if not info:
            continue
        title = sheet["properties"]["title"]

        # 전체 데이터 + 하이퍼링크 가져오기
        result = service.spreadsheets().get(
            spreadsheetId=SPREADSHEET_ID,
            ranges=[f"'{title}'!A1:L50"],
            includeGridData=True,
            fields="sheets.data.rowData.values(hyperlink,formattedValue)"
        ).execute()

        rows = result["sheets"][0]["data"][0].get("rowData", [])

        weekday = {}
        saturday = {}
        current_key = None
        is_saturday = False

        for row in rows:
            cells = row.get("values", [])
            if len(cells) < 3:
                continue

            # B열 (index 1): 시간대
            b_val = cells[1].get("formattedValue", "") if len(cells) > 1 else ""
            c_val = cells[2].get("formattedValue", "") if len(cells) > 2 else ""

            if b_val.strip():
                new_key, is_sat = _format_schedule_key(b_val)
                if new_key:
                    current_key = new_key
                    is_saturday = is_sat

            if "승차코스" in c_val and current_key:
                stops = []
                for ci in range(3, min(len(cells), 12)):
                    cell = cells[ci]
                    name = cell.get("formattedValue", "")
                    if not name or not name.strip():
                        continue
                    name = name.strip().replace("\n", " ")
                    link = cell.get("hyperlink", "")
                    stops.append({"stop": name, "map_url": link, "time": ""})

                # 다음 행: 승차시간
                # (이건 같은 API 호출 내에서 처리)

                target = saturday if is_saturday else weekday
                if current_key not in target:
                    target[current_key] = []
                target[current_key].extend(stops)

            elif "승차시간" in c_val and current_key:
                target = saturday if is_saturday else weekday
                stop_list = target.get(current_key, [])
                time_idx = 0
                for ci in range(3, min(len(cells), 12)):
                    cell = cells[ci]
                    tv = cell.get("formattedValue", "")
                    ft = _format_time_val(tv)
                    if ft:
                        # 마지막에 추가된 시간 없는 정류장에 시간 매핑
                        for s in stop_list:
                            if not s["time"]:
                                s["time"] = ft
                                break

        # 좌표 매핑
        for stype_dict in [weekday, saturday]:
            for key, stops in stype_dict.items():
                for s in stops:
                    url = s.get("map_url", "")
                    if url and url in coord_cache:
                        s["lat"], s["lng"] = coord_cache[url]
                    elif url:
                        lat, lng = _get_naver_coords(url)
                        if lat:
                            s["lat"], s["lng"] = lat, lng
                            coord_cache[url] = (lat, lng)

        vehicles.append({
            "number": info["number"], "area": info["area"],
            "driver": info["driver"], "phone": info["phone"],
            "weekday": weekday, "saturday": saturday,
        })

    return {
        "academy_name": "더숲국어전문학원",
        "vehicles": vehicles,
        "locations": {
            "본원": "더숲3관, 에스지, IBSI 영어, 엠플본관",
            "더숲1관": "신한은행 4층", "엠플2관": "피자스쿨",
            "더숲2관": "피자스쿨", "더숲국어": "알레르망 2층(래미안 맞은편)",
        },
    }


@st.cache_data
def load_data():
    """데이터 로드: Google Sheets 우선, 실패 시 로컬 fallback"""
    try:
        return load_data_from_sheets()
    except Exception:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)


@st.cache_data
def load_config():
    try:
        key = st.secrets.get("kakao_rest_api_key", "")
        if key:
            return {"kakao_rest_api_key": key}
    except Exception:
        pass
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


# ─── 유틸 ───
def haversine(lat1, lng1, lat2, lng2):
    R = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

# 울산 중구 중심 좌표 + 반경 (학원 차량 운행 범위)
ULSAN_CENTER_LNG = 129.330
ULSAN_CENTER_LAT = 35.564
ULSAN_RADIUS = 6000  # 6km

def _clean_address(address):
    """검색 전 불필요한 접미사 제거"""
    # "함월초 앞", "남외중 근처" → "함월초", "남외중"
    return re.sub(r"\s*(앞|근처|부근|옆|쪽|근방)\s*$", "", address.strip())


def geocode(address):
    config = load_config()
    key = config.get("kakao_rest_api_key", "")
    if not key:
        return None, None, None
    ctx = ssl.create_default_context()
    headers = {"Authorization": f"KakaoAK {key}"}
    cleaned = _clean_address(address)
    q = f"울산 중구 {cleaned}" if "울산" not in cleaned else cleaned
    enc = urllib.parse.quote(q)

    # 1차: 주소 검색
    try:
        url = f"https://dapi.kakao.com/v2/local/search/address.json?query={enc}&size=1"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
            docs = json.loads(resp.read()).get("documents", [])
            if docs:
                d = docs[0]
                lat, lng = float(d["y"]), float(d["x"])
                if haversine(ULSAN_CENTER_LAT, ULSAN_CENTER_LNG, lat, lng) < ULSAN_RADIUS:
                    return lat, lng, d.get("address_name", "")
    except Exception:
        pass

    # 2차: 키워드 검색 (울산 중구 중심 + 반경 제한)
    try:
        url = (f"https://dapi.kakao.com/v2/local/search/keyword.json?query={enc}&size=5"
               f"&x={ULSAN_CENTER_LNG}&y={ULSAN_CENTER_LAT}&radius={ULSAN_RADIUS}&sort=distance")
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
            docs = json.loads(resp.read()).get("documents", [])
            for d in docs:
                lat, lng = float(d["y"]), float(d["x"])
                if haversine(ULSAN_CENTER_LAT, ULSAN_CENTER_LNG, lat, lng) < ULSAN_RADIUS:
                    return lat, lng, d.get("place_name", "")
    except Exception:
        pass

    # 3차: "울산 중구" 빼고 원본으로 재시도
    for retry_q in [cleaned, address]:
        enc2 = urllib.parse.quote(retry_q)
        try:
            url = (f"https://dapi.kakao.com/v2/local/search/keyword.json?query={enc2}&size=5"
                   f"&x={ULSAN_CENTER_LNG}&y={ULSAN_CENTER_LAT}&radius={ULSAN_RADIUS}&sort=distance")
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
                docs = json.loads(resp.read()).get("documents", [])
                for d in docs:
                    lat, lng = float(d["y"]), float(d["x"])
                    if haversine(ULSAN_CENTER_LAT, ULSAN_CENTER_LNG, lat, lng) < ULSAN_RADIUS:
                        return lat, lng, d.get("place_name", "")
        except Exception:
            pass

    return None, None, None

def format_phone(raw):
    digits = re.sub(r"[^0-9]", "", raw)
    if len(digits) == 11:
        return f"{digits[:3]}-{digits[3:7]}-{digits[7:]}"
    elif len(digits) == 10:
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
    return raw

def _normalize(text):
    """한글/영문 변환 등 정규화"""
    t = text.lower().replace(" ", "")
    t = t.replace("이편한", "e편한").replace("이마트", "emart")
    t = t.replace("kcc", "kcc").replace("ｋｃｃ", "kcc")
    return t

# 방향/위치 힌트 키워드
HINT_KEYWORDS = ["후문", "정문", "쪽문", "앞", "옆", "뒤", "입구", "맞은편",
                 "cu", "gs25", "세븐일레븐", "이마트24", "버스정류장"]

def _extract_hints(text):
    """입력에서 방향/위치 힌트 추출"""
    t = text.lower().replace(" ", "")
    return [h for h in HINT_KEYWORDS if h in t]

def fuzzy_score(query, stop_name):
    qn = _normalize(query)
    sn = _normalize(stop_name)

    # 완전 포함
    if qn in sn or sn in qn:
        return 100

    # 키워드 분리 매칭
    keywords = [kw.strip() for kw in re.split(r"[,/\s]+", query.strip()) if kw.strip()]
    score, matched = 0, 0
    for kw in keywords:
        kn = _normalize(kw)
        ks = re.sub(r"동$", "", kn) if len(kn) > 2 else kn
        if kn in sn:
            score += 50; matched += 1
        elif ks and ks in sn:
            score += 45; matched += 1
        else:
            for l in range(len(kn), 1, -1):
                found = False
                for i in range(len(kn) - l + 1):
                    if kn[i:i+l] in sn:
                        score += min(l * 10, 40); matched += 1; found = True; break
                if found: break
    if keywords and matched == len(keywords):
        score += 20

    # 힌트 보너스: 입력에 "후문", "CU" 등이 있고 정류장명에도 있으면 가산
    input_hints = _extract_hints(query)
    if input_hints:
        stop_lower = stop_name.lower().replace(" ", "")
        hint_match = sum(1 for h in input_hints if h in stop_lower)
        score += hint_match * 15  # 힌트 1개 매칭당 15점

    return score

def _time_to_minutes(t):
    """'7:00' → 420, '5:30' → 330"""
    m = re.match(r"(\d{1,2}):(\d{2})", t)
    if not m:
        return None
    return int(m.group(1)) * 60 + int(m.group(2))


def resolve_schedule_time(user_time, data, is_saturday=False):
    """사용자 시간 → 데이터에 존재하는 가장 가까운 이전 시간대로 매핑.
    예: 6:00 → 5:30, 6:30 → 5:30, 7:30 → 7:00"""
    target_min = _time_to_minutes(user_time)
    if target_min is None:
        return user_time

    # 데이터에 존재하는 모든 schedule_time 수집
    available = set()
    for v in data["vehicles"]:
        keys_iter = v["saturday"] if is_saturday else v["weekday"]
        for k in keys_iter.keys():
            base = k.split("_")[0]  # "8:00_월수금" → "8:00"
            available.add(base)

    # target_min 이하 중 가장 큰 것
    best, best_min = None, -1
    for sched in available:
        sm = _time_to_minutes(sched)
        if sm is None:
            continue
        if sm <= target_min and sm > best_min:
            best = sched
            best_min = sm
    return best  # None이면 매칭 실패


def get_schedule_keys(schedule_time, days):
    if schedule_time == "8:00":
        keys = []
        if any(d in ["월", "수", "금"] for d in days):
            keys.append("8:00_월수금")
        if any(d in ["화", "목"] for d in days):
            keys.append("8:00_화목")
        return keys
    return [schedule_time]

KNOWN_MAPPINGS_PATH = os.path.join(BASE_DIR, "data", "known_mappings.json")

@st.cache_data
def load_known_mappings():
    if os.path.exists(KNOWN_MAPPINGS_PATH):
        with open(KNOWN_MAPPINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def find_stops(data, schedule_time, days, address, student_coords, threshold):
    is_wd = any(d in "월화수목금" for d in days)
    is_sat = "토" in days
    KEYWORD_BOOST = 80

    # 0단계: 과거 배정 이력 매칭 (최우선)
    known = load_known_mappings()
    addr_norm = _normalize(address) if address else ""
    known_stop_name = known.get(addr_norm, "")

    all_stops = []
    for v in data["vehicles"]:
        if is_wd:
            for key in get_schedule_keys(schedule_time, days):
                for idx, s in enumerate(v["weekday"].get(key, [])):
                    all_stops.append({"vehicle": v, "stop": s, "schedule_key": key,
                                      "schedule_type": "weekday", "route_order": idx})
        if is_sat:
            for idx, s in enumerate(v["saturday"].get(schedule_time, [])):
                all_stops.append({"vehicle": v, "stop": s, "schedule_key": schedule_time,
                                  "schedule_type": "saturday", "route_order": idx})

    for r in all_stops:
        sn = r["stop"]["stop"]
        r["kw"] = fuzzy_score(address, sn) if address else 0

        # 과거 이력 매칭 보너스
        if known_stop_name and _normalize(sn) == _normalize(known_stop_name):
            r["kw"] = max(r["kw"], 200)  # 이력 매칭 = 최고 점수

        if student_coords and student_coords[0] and r["stop"].get("lat"):
            r["dist"] = haversine(student_coords[0], student_coords[1], r["stop"]["lat"], r["stop"]["lng"])
        else:
            r["dist"] = None

    if student_coords and student_coords[0]:
        wd = [r for r in all_stops if r["dist"] is not None]

        # 3단계 정렬: 이력매칭(200+) > 이름매칭(80+) > 거리순
        tier1 = sorted([r for r in wd if r["kw"] >= 200], key=lambda x: x["dist"])
        tier2 = sorted([r for r in wd if 200 > r["kw"] >= KEYWORD_BOOST], key=lambda x: (-x["kw"], x["dist"]))
        tier3 = sorted([r for r in wd if r["kw"] < KEYWORD_BOOST], key=lambda x: x["dist"])
        combined = tier1 + tier2 + tier3

        # 근접 정류장 코스 뒤쪽 우선 (같은 tier 내에서만)
        i = 0
        while i < len(combined) - 1:
            j = i + 1
            while j < len(combined):
                di, dj = combined[i].get("dist", 0), combined[j].get("dist", 0)
                if abs(dj - di) > threshold:
                    break
                if (combined[j]["vehicle"]["number"] == combined[i]["vehicle"]["number"]
                        and combined[j]["route_order"] > combined[i]["route_order"]
                        and combined[j]["kw"] >= combined[i]["kw"]):
                    combined[i], combined[j] = combined[j], combined[i]
                j += 1
            i += 1
        return combined

    elif address:
        r = [x for x in all_stops if x["kw"] > 0]
        r.sort(key=lambda x: x["kw"], reverse=True)
        return r
    return []

def shorten_map_url(url):
    """네이버 지도 URL에서 불필요한 파라미터 제거"""
    if not url:
        return ""
    # /entry/place/12345?c=...&placePath=... → /entry/place/12345
    # /entry/bus-station/12345?c=... → /entry/bus-station/12345
    return url.split("?")[0]

def make_parent_msg(info, assignments, show_driver=False):
    """assignments: [(time_label, result), ...]"""
    msg = "[더숲국어전문학원 차량 안내]\n\n"
    msg += f"안녕하세요, {info['name']} 학생 차량 안내드립니다.\n\n"

    # 탑승 정보
    if len(assignments) == 1:
        time_label, r = assignments[0]
        s, v = r["stop"], r["vehicle"]
        if r.get("has_info"):
            msg += f"■ 탑승 정보\n- 장소: {s['stop']}\n- 시간: {s['time']}\n- 차량: {v['number']}호차\n"
            if show_driver:
                msg += f"- 기사님: {v['driver']} ({v['phone']})\n"
        else:
            msg += f"■ 탑승 정보\n- 장소: {s['stop']}\n"
        short_url = shorten_map_url(s.get("map_url", ""))
        if short_url:
            msg += f"\n■ 위치 확인\n{short_url}\n"
    else:
        msg += "■ 탑승 정보\n"
        for time_label, r in assignments:
            s, v = r["stop"], r["vehicle"]
            if r.get("has_info"):
                line = f"- {time_label}: {s['stop']} / {s['time']} / {v['number']}호차"
                if show_driver:
                    line += f" ({v['driver']} {v['phone']})"
                msg += line + "\n"
            else:
                msg += f"- {time_label}: {s['stop']}\n"
        msg += "\n■ 위치 확인\n"
        seen_urls = set()
        for time_label, r in assignments:
            url = shorten_map_url(r["stop"].get("map_url", ""))
            if url and url not in seen_urls:
                seen_urls.add(url)
                msg += f"- {r['stop']['stop']}: {url}\n"

    msg += f"\n■ 수업 정보\n- 수업: {info['days']}\n- 장소: {info['location']}\n- 시작일: {info['start_date']}부터\n"
    msg += "\n※ 탑승 장소에 5분 전 대기 부탁드립니다."
    return msg


def make_notice(info, assignments):
    """assignments: [(time_label, result), ...]"""
    n = f"ㅇ 학교/학년/학생명(신규/기존) : {info['school']}/{info['grade']}/{info['name']}({info['status']})\n"

    if len(assignments) == 1:
        time_label, r = assignments[0]
        s, v = r["stop"], r["vehicle"]
        if r.get("has_info"):
            n += f"ㅇ 등원 차량 : {v['number']}호차({s['stop']}/{s['time']})\n"
        else:
            n += f"ㅇ 등원 차량 : ({s['stop']})\n"
    else:
        n += "ㅇ 등원 차량 :\n"
        for time_label, r in assignments:
            s, v = r["stop"], r["vehicle"]
            if r.get("has_info"):
                n += f"  - {time_label} : {v['number']}호차({s['stop']}/{s['time']})\n"
            else:
                n += f"  - {time_label} : ({s['stop']})\n"

    n += f"ㅇ 수업시간 : {info['days']}\n"
    n += f"ㅇ 수업장소 : {info['location']}\n"
    n += f"ㅇ 탑승시작일자 : {info['start_date']}부터\n"
    n += f"ㅇ 학생 연락처 : {info['student_phone']}\n"
    n += f"ㅇ 학부모 연락처 : {info['parent_phone']}"
    return n


# ─── 페이지 설정 ───
st.set_page_config(page_title="차량배정", page_icon="🚌", layout="centered")
st.markdown("""<style>
    .block-container { max-width: 700px; padding-top: 2rem; }
    div[data-testid="stExpander"] { border: 1px solid #ddd; border-radius: 8px; margin-bottom: 0.5rem; }
</style>""", unsafe_allow_html=True)

st.title("🚌 차량배정")
data = load_data()

# 사이드바
NEARBY_THRESHOLD = 20  # 미터. 내부 설정

with st.sidebar:
    st.caption("⚙️ 설정")
    show_driver = st.toggle("기사님 연락처 포함", value=False)
    st.divider()
    from datetime import datetime as _dt
    st.caption(f"데이터: {_dt.now().strftime('%Y-%m-%d %H:%M')} 기준")
    if st.button("🔄 새로고침", use_container_width=True):
        load_data.clear()
        load_data_from_sheets.clear()
        st.rerun()
    st.caption("made by 국D w/ Claude Code")

# ─── 입력 폼 ───
with st.form("f", border=False):
    st.subheader("학생 정보")
    c1, c2, c3, c4 = st.columns([2, 2, 2, 1.5])
    name = c1.text_input("이름")
    school = c2.selectbox("학교", SCHOOLS, index=None, placeholder="검색...")
    grade = c3.selectbox("학년", GRADES, index=None, placeholder="선택")
    status = c4.selectbox("구분", ["신규", "기존"])

    c5, c6 = st.columns(2)
    student_phone = c5.text_input("학생 연락처")
    parent_phone = c6.text_input("학부모 연락처")

    st.divider()
    st.subheader("수업 정보")

    location_key = st.selectbox("수업장소", list(LOCATIONS.keys()))

    st.write("**수업 요일/시간**")
    default_time_idx = next((i for i, t in enumerate(TIME_SLOTS) if t[1] == "7:00"), 0)
    day_time_map = {}
    # 3열씩 2행
    for row_days in [ALL_DAYS[:3], ALL_DAYS[3:]]:
        cols = st.columns(len(row_days))
        for i, d in enumerate(row_days):
            with cols[i]:
                checked = st.checkbox(d, value=(d in ["월", "수", "금"]), key=f"day_{d}")
                t_idx = st.selectbox(
                    f"{d} 시간", range(len(TIME_SLOTS)),
                    format_func=lambda j: TIME_SLOTS[j][0],
                    index=default_time_idx, key=f"time_{d}",
                    label_visibility="collapsed",
                )
                if checked:
                    day_time_map[d] = TIME_SLOTS[t_idx][1]

    st.divider()
    st.subheader("탑승 정보")
    c9, c10 = st.columns(2)
    address = c9.text_input("타는 곳")
    start_date = c10.date_input("탑승 시작일", value=date.today() + timedelta(days=1))

    submitted = st.form_submit_button("🔍 정류장 검색", use_container_width=True, type="primary")

def _time_to_display(ct):
    m = re.match(r"(\d{1,2}):(\d{2})", ct)
    if m:
        return f"{m.group(1)}시" if m.group(2) == "00" else f"{m.group(1)}시 {int(m.group(2))}분"
    return ct

def _format_days_display(day_time_map):
    """요일/시간 맵 → 표시용 문자열 (같은 시간끼리 묶음)"""
    # {시간: [요일들]} 역매핑
    time_to_days = {}
    for d, t in day_time_map.items():
        if t not in time_to_days:
            time_to_days[t] = []
        time_to_days[t].append(d)

    parts = []
    for t, days in time_to_days.items():
        parts.append(f"{','.join(days)} {_time_to_display(t)}")
    return " / ".join(parts)


# ─── 검색 처리 ───
if submitted:
    selected_days = list(day_time_map.keys())

    errors = []
    if not name: errors.append("이름")
    if not school: errors.append("학교")
    if not grade: errors.append("학년")
    if not address: errors.append("타는 곳")
    if not student_phone: errors.append("학생 연락처")
    if not parent_phone: errors.append("학부모 연락처")
    if not selected_days: errors.append("수업요일")

    if errors:
        st.error(f"다음 항목을 입력해주세요: {', '.join(errors)}")
        st.stop()

    location_value = LOCATIONS[location_key]
    s_phone = format_phone(student_phone)
    p_phone = format_phone(parent_phone)
    sd = start_date
    start_str = f"{sd.month}월 {sd.day}일({DAY_KR[sd.weekday()]})"
    days_display = _format_days_display(day_time_map)

    info = {
        "name": name, "school": school, "grade": grade, "status": status,
        "time_display": days_display, "days": days_display,
        "location": location_value, "start_date": start_str,
        "student_phone": s_phone, "parent_phone": p_phone,
    }

    with st.spinner("검색 중..."):
        lat, lng, resolved = geocode(address)

    student_coords = (lat, lng) if lat else None
    if lat:
        st.caption(f"📍 {resolved}")

    # 시간대별로 따로 검색 → {time_label: [후보 정류장 목록]}
    # 같은 시간에 묶인 요일들끼리 그룹화
    time_groups = {}  # {schedule_time: [요일 리스트]}
    for d, t in day_time_map.items():
        if t not in time_groups:
            time_groups[t] = []
        time_groups[t].append(d)

    # 각 시간대별로 후보 검색
    time_candidates = {}  # {time_label: [top3 candidates]}
    manual_times = []     # 수동 배정 필요한 시간대 라벨 목록
    schedule_remap_notices = []  # 시간 매핑 알림

    for user_time, days_for_time in time_groups.items():
        is_sat = "토" in days_for_time
        # 사용자 시간 → 코스표 시간 (가장 가까운 이전)
        resolved = resolve_schedule_time(user_time, data, is_saturday=is_sat)
        time_label = f"{','.join(days_for_time)} {_time_to_display(user_time)}"

        if resolved and resolved != user_time:
            schedule_remap_notices.append(
                f"{_time_to_display(user_time)} 수업 → {_time_to_display(resolved)} 코스로 검색"
            )

        search_time = resolved if resolved else user_time
        results = find_stops(data, search_time, days_for_time, address, student_coords, NEARBY_THRESHOLD)

        # 중복 제거 + 상위 3개
        seen, cands = set(), []
        for r in results:
            key = f"{r['vehicle']['number']}_{r['stop']['stop']}"
            if key not in seen:
                seen.add(key)
                r["has_info"] = bool(r["stop"].get("time"))
                cands.append(r)
            if len(cands) >= 3:
                break

        if not cands:
            # 수동 배정 fallback - 다른 시간대 정류장 위치 참고
            fallback_days = [d for d in days_for_time if d != "토"] or ["월","수","금"]
            fallback = find_stops(data, "7:00", fallback_days, address, student_coords, NEARBY_THRESHOLD)
            seen_fb, fb_cands = set(), []
            for r in fallback:
                key = f"{r['vehicle']['number']}_{r['stop']['stop']}"
                if key not in seen_fb:
                    seen_fb.add(key)
                    r["has_info"] = False
                    fb_cands.append(r)
                if len(fb_cands) >= 3:
                    break
            time_candidates[time_label] = fb_cands
            manual_times.append(time_label)
        else:
            time_candidates[time_label] = cands

    # 시간 매핑 알림 표시
    if schedule_remap_notices:
        st.info("ℹ️ " + " · ".join(schedule_remap_notices))

    if not any(time_candidates.values()):
        st.error("매칭되는 정류장이 없습니다. 타는 곳을 다시 확인해주세요.")
        st.stop()

    # 수동 배정 안내
    if manual_times:
        st.divider()
        st.warning(
            "⚠️ **수동 배정이 필요한 시간대가 있습니다**\n\n"
            f"다음 시간대는 코스표에 없습니다: {', '.join(manual_times)}\n\n"
            "**진행 방법:**\n"
            "1. 아래에서 각 시간대마다 가장 가까운 탑승 위치를 선택하세요\n"
            "2. 내부 배정 양식을 카톡 배정방에 보내주세요\n"
            "3. 차량 담당자가 호차/시간을 배정하면\n"
            "4. 그때 학부모 안내 문자를 작성해주세요"
        )

    # 각 시간대별로 후보 표시 → 사용자가 선택
    st.divider()
    selected_per_time = {}  # {time_label: 선택된 result}

    for ti, (time_label, cands) in enumerate(time_candidates.items()):
        is_manual = time_label in manual_times
        st.subheader(f"📍 {time_label}" + (" (수동배정)" if is_manual else ""))

        if not cands:
            st.error(f"{time_label}: 매칭 정류장 없음")
            continue

        # 라디오로 선택
        options = []
        for ci, r in enumerate(cands):
            v, s = r["vehicle"], r["stop"]
            dist = f" · {r['dist']:.0f}m" if r.get("dist") else ""
            rank = ["1순위", "2순위", "3순위"][ci]
            if is_manual:
                opt = f"{rank} — {s['stop']}{dist}"
            else:
                opt = f"{rank} — {v['number']}호차 {s['stop']} ({s['time']}){dist}"
            options.append(opt)

        selected_idx = st.radio(
            f"정류장 선택 ({time_label})",
            range(len(options)),
            format_func=lambda i: options[i],
            key=f"sel_{ti}",
            label_visibility="collapsed",
        )
        selected_per_time[time_label] = cands[selected_idx]

    # 수동 배정 시간대용 호차/시간 입력
    manual_inputs = {}
    if manual_times:
        st.divider()
        st.caption("📝 수동 배정된 정보 입력 (담당자 배정 확정 후)")
        for time_label in manual_times:
            cols = st.columns(2)
            mv = cols[0].text_input(f"{time_label} 호차", placeholder="예: 3호차", key=f"mv_{time_label}")
            mt = cols[1].text_input(f"{time_label} 시간", placeholder="예: 7:35", key=f"mt_{time_label}")
            manual_inputs[time_label] = (mv, mt)

    # 모든 시간대의 선택을 합쳐 최종 메시지 생성
    st.divider()
    final_assignments = []
    for time_label, r in selected_per_time.items():
        if time_label in manual_times:
            mv, mt = manual_inputs.get(time_label, ("", ""))
            if mv and mt:
                # 수동 배정 정보로 채우기
                manual_r = dict(r)
                manual_r["has_info"] = True
                manual_r["stop"] = dict(r["stop"])
                manual_r["stop"]["time"] = mt
                manual_r["vehicle"] = dict(r["vehicle"])
                vm = re.search(r"(\d+)", mv)
                if vm:
                    vnum = int(vm.group(1))
                    manual_r["vehicle"]["number"] = vnum
                    for vdata in data["vehicles"]:
                        if vdata["number"] == vnum:
                            manual_r["vehicle"]["driver"] = vdata["driver"]
                            manual_r["vehicle"]["phone"] = vdata["phone"]
                            break
                final_assignments.append((time_label, manual_r))
            else:
                # 수동 배정 미입력 → 위치만
                final_assignments.append((time_label, r))
        else:
            final_assignments.append((time_label, r))

    notice = make_notice(info, final_assignments)
    parent_msg = make_parent_msg(info, final_assignments, show_driver=show_driver)

    # 수동 배정 시간대가 있는데 입력이 안 된 경우 → 내부 양식만 우선 표시
    has_pending_manual = any(
        tl in manual_times and not (manual_inputs.get(tl, ("",""))[0] and manual_inputs.get(tl, ("",""))[1])
        for tl in selected_per_time
    )

    if has_pending_manual:
        st.caption("📝 내부 배정 양식 (카톡 배정방에 전달)")
        st.code(notice, language=None)
        st.caption("📱 학부모 안내 문자는 위 수동 배정 정보 입력 후 자동 생성됩니다")
    else:
        t1, t2 = st.tabs(["📱 학부모 안내 문자", "📝 내부 배정 양식"])
        with t1:
            st.code(parent_msg, language=None)
        with t2:
            st.code(notice, language=None)
