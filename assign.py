# -*- coding: utf-8 -*-
"""더숲국어전문학원 차량배정 자동화 스크립트"""
import json
import math
import os
import re
import ssl
import sys
import subprocess
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "routes.json")
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

# 요일 매핑
DAY_NAMES = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6}
DAY_NAMES_KR = {0: "월", 1: "화", 2: "수", 3: "목", 4: "금", 5: "토", 6: "일"}

# 수업시간 → 코스표 시간대 매핑
CLASS_TO_SCHEDULE = {
    "2:30": "2:30",
    "4:00": "4:00",
    "4시": "4:00",
    "5:30": "5:30",
    "5시30분": "5:30",
    "5시반": "5:30",
    "7:00": "7:00",
    "7시": "7:00",
    "8:00": "8:00",
    "8시": "8:00",
    "9:00": "9:00",
    "9시": "9:00",
    "10:00": "10:00",
    "10시": "10:00",
    "11:00": "11:00",
    "11시": "11:00",
    "12:00": "12:00",
    "12시": "12:00",
}


NAVER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://map.naver.com/",
}


def load_data():
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def haversine(lat1, lng1, lat2, lng2):
    """두 좌표 간 직선거리(미터)"""
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def load_config():
    """config.json에서 API 키 등 설정 로드"""
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def geocode_kakao(address, api_key):
    """카카오 Local API로 주소/장소명 → 좌표 변환 (주소검색 → 키워드검색 순)"""
    ctx = ssl.create_default_context()
    headers = {"Authorization": f"KakaoAK {api_key}"}
    query = f"울산 {address}" if "울산" not in address else address
    encoded = urllib.parse.quote(query)

    # 1차: 주소 검색 (도로명/지번 주소)
    try:
        url = f"https://dapi.kakao.com/v2/local/search/address.json?query={encoded}&size=1"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
            data = json.loads(resp.read())
            docs = data.get("documents", [])
            if docs:
                d = docs[0]
                return float(d["y"]), float(d["x"]), d.get("address_name", "")
    except Exception:
        pass

    # 2차: 키워드 검색 (아파트명, 건물명 등)
    try:
        url = f"https://dapi.kakao.com/v2/local/search/keyword.json?query={encoded}&size=1"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
            data = json.loads(resp.read())
            docs = data.get("documents", [])
            if docs:
                d = docs[0]
                return float(d["y"]), float(d["x"]), d.get("place_name", "")
    except Exception:
        pass

    return None, None, None


def geocode_nominatim(address):
    """Nominatim(OpenStreetMap) fallback"""
    nom_query = urllib.parse.quote(f"울산 {address}")
    url = f"https://nominatim.openstreetmap.org/search?q={nom_query}&format=json&limit=1&countrycodes=kr"
    req = urllib.request.Request(url, headers={"User-Agent": "VehicleAssignment/1.0"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        results = json.loads(resp.read())
        if results:
            return float(results[0]["lat"]), float(results[0]["lon"]), results[0].get("display_name", "")
    return None, None, None


def geocode_address(address):
    """주소/장소명 → 좌표 변환 (카카오 > Nominatim 순서)"""
    config = load_config()
    kakao_key = config.get("kakao_rest_api_key", "")

    # 1차: 카카오 API (키가 있으면)
    if kakao_key:
        try:
            lat, lng, name = geocode_kakao(address, kakao_key)
            if lat:
                return lat, lng, name
        except Exception:
            pass

    # 2차: Nominatim fallback
    try:
        return geocode_nominatim(address)
    except Exception:
        pass

    return None, None, None


def copy_to_clipboard(text):
    """클립보드에 텍스트 복사 (Windows)"""
    try:
        process = subprocess.Popen(["clip"], stdin=subprocess.PIPE)
        process.communicate(text.encode("utf-16le"))
        return True
    except Exception:
        return False


def normalize_time_input(raw):
    """사용자 입력을 정규화된 시간대로 변환"""
    raw = raw.strip().replace(" ", "")
    # 직접 매핑 확인
    if raw in CLASS_TO_SCHEDULE:
        return CLASS_TO_SCHEDULE[raw]
    # "7시" → "7:00" 패턴
    m = re.match(r"(\d{1,2})시(\d{2}분?)?", raw)
    if m:
        hour = m.group(1)
        minute = m.group(2) or "00"
        minute = minute.replace("분", "")
        return f"{hour}:{minute}"
    # "7:00" 패턴
    m = re.match(r"(\d{1,2}):(\d{2})", raw)
    if m:
        return f"{int(m.group(1))}:{m.group(2)}"
    return raw


def parse_days(raw):
    """요일 문자열 파싱 (예: '월,수,금' → ['월','수','금'])"""
    raw = raw.strip().replace(" ", "").replace(".", ",")
    days = []
    for ch in raw:
        if ch in DAY_NAMES:
            days.append(ch)
    return days if days else ["월", "화", "수", "목", "금"]


def is_weekday_schedule(days):
    """평일 스케줄인지 확인"""
    return any(d in ["월", "화", "수", "목", "금"] for d in days)


def is_saturday_schedule(days):
    """토요일 스케줄인지 확인"""
    return "토" in days


def get_schedule_keys(schedule_time, days):
    """수업시간과 요일로 코스표 스케줄 키 목록 반환"""
    keys = []
    if schedule_time == "8:00":
        mwf = any(d in ["월", "수", "금"] for d in days)
        tth = any(d in ["화", "목"] for d in days)
        if mwf:
            keys.append("8:00_월수금")
        if tth:
            keys.append("8:00_화목")
    else:
        keys.append(schedule_time)
    return keys


def _normalize(text):
    """한글/영문 변환 등 정규화"""
    t = text.lower().replace(" ", "")
    t = t.replace("이편한", "e편한").replace("이마트", "emart")
    return t


def fuzzy_match_score(query, stop_name):
    """주소 키워드와 정류장명의 유사도 점수 계산"""
    # 원본 보존 후 정규화
    query_norm = _normalize(query)
    stop_norm = _normalize(stop_name)

    # 완전 포함
    if query_norm in stop_norm or stop_norm in query_norm:
        return 100

    # 키워드 분리 (공백 기준, 제거 전)
    keywords = re.split(r"[,/\s]+", query.strip())
    keywords = [kw.strip() for kw in keywords if kw.strip()]

    score = 0
    matched_keywords = 0
    for kw in keywords:
        kw_norm = kw.lower().replace(" ", "")
        # '동' 접미사 제거 (유곡동 → 유곡)
        kw_stripped = re.sub(r"동$", "", kw_norm) if len(kw_norm) > 2 else kw_norm

        if kw_norm in stop_norm:
            score += 50
            matched_keywords += 1
        elif kw_stripped and kw_stripped in stop_norm:
            score += 45
            matched_keywords += 1
        else:
            # 부분 매칭: 2글자 이상 연속 매칭 (한글은 2자, 숫자포함은 더 길게)
            best_sub = 0
            for length in range(len(kw_norm), 1, -1):
                for i in range(len(kw_norm) - length + 1):
                    substr = kw_norm[i : i + length]
                    if substr in stop_norm:
                        best_sub = max(best_sub, length * 10)
                        break
                if best_sub > 0:
                    break
            if best_sub > 0:
                score += min(best_sub, 40)
                matched_keywords += 1

    # 모든 키워드가 매칭되면 보너스
    if keywords and matched_keywords == len(keywords):
        score += 20

    return score


def collect_stops_for_schedule(data, schedule_time, days):
    """해당 시간대/요일에 운행하는 모든 정류장 수집 (코스 내 순서 포함)"""
    results = []
    for vehicle in data["vehicles"]:
        if is_weekday_schedule(days):
            for key in get_schedule_keys(schedule_time, days):
                stops = vehicle["weekday"].get(key, [])
                for idx, stop in enumerate(stops):
                    results.append({
                        "vehicle": vehicle, "stop": stop,
                        "schedule_key": key, "schedule_type": "weekday",
                        "route_order": idx,
                    })
        if is_saturday_schedule(days):
            stops = vehicle["saturday"].get(schedule_time, [])
            for idx, stop in enumerate(stops):
                results.append({
                    "vehicle": vehicle, "stop": stop,
                    "schedule_key": schedule_time, "schedule_type": "saturday",
                    "route_order": idx,
                })
    return results


def find_matching_stops(data, schedule_time, days, address, student_coords=None):
    """주소와 시간대에 맞는 정류장 후보 찾기 (거리 + 키워드 하이브리드)"""
    all_stops = collect_stops_for_schedule(data, schedule_time, days)

    for r in all_stops:
        s = r["stop"]
        # 키워드 점수
        r["keyword_score"] = fuzzy_match_score(address, s["stop"])

        # 거리 계산 (좌표가 있는 경우)
        if student_coords and student_coords[0] and s.get("lat"):
            r["distance"] = haversine(student_coords[0], student_coords[1], s["lat"], s["lng"])
        else:
            r["distance"] = None

    NEARBY_THRESHOLD = 20  # 미터. 이 이내 차이는 비슷한 거리로 간주
    KEYWORD_BOOST_THRESHOLD = 80  # 이름이 완전히 포함되는 경우(100점)만 거리보다 우선

    if student_coords and student_coords[0]:
        with_dist = [r for r in all_stops if r["distance"] is not None]

        # 키워드 강매칭 정류장을 최우선으로 끌어올리기
        # "남외중" 입력 → "남외중 정문 앞" 정류장은 이름이 직접 매칭되므로 거리와 무관하게 우선
        strong_match = [r for r in with_dist if r["keyword_score"] >= KEYWORD_BOOST_THRESHOLD]
        weak_match = [r for r in with_dist if r["keyword_score"] < KEYWORD_BOOST_THRESHOLD]

        # 강매칭: 키워드 점수순 → 거리순
        strong_match.sort(key=lambda x: (-x["keyword_score"], x["distance"]))
        # 약매칭: 거리순
        weak_match.sort(key=lambda x: x["distance"])

        # 합치기: 강매칭 먼저, 그 다음 거리순
        combined = strong_match + weak_match

        # 같은 호차 내 근접 정류장 → 코스 뒤쪽 우선
        i = 0
        while i < len(combined) - 1:
            j = i + 1
            while j < len(combined):
                di = combined[i].get("distance", 0)
                dj = combined[j].get("distance", 0)
                if abs(dj - di) > NEARBY_THRESHOLD:
                    break
                if (combined[j]["vehicle"]["number"] == combined[i]["vehicle"]["number"]
                        and combined[j].get("route_order", 0) > combined[i].get("route_order", 0)
                        and combined[j]["keyword_score"] >= combined[i]["keyword_score"]):
                    combined[i], combined[j] = combined[j], combined[i]
                j += 1
            i += 1

        return combined
    else:
        results = [r for r in all_stops if r["keyword_score"] > 0]
        results.sort(key=lambda x: x["keyword_score"], reverse=True)
        return results


def find_nearest_stop_any_schedule(data, days, address):
    """수동배정용: 모든 시간대에서 주소에 가장 가까운 정류장 찾기 (위치만 필요)"""
    best = None
    best_score = 0

    for vehicle in data["vehicles"]:
        # 모든 평일 시간대 검색
        if is_weekday_schedule(days):
            for key, stops in vehicle["weekday"].items():
                for stop in stops:
                    score = fuzzy_match_score(address, stop["stop"])
                    if score > best_score:
                        best_score = score
                        best = {
                            "vehicle": vehicle,
                            "stop": stop,
                            "schedule_key": key,
                            "schedule_type": "weekday",
                            "score": score,
                            "manual": True,
                        }

        # 토요일
        if is_saturday_schedule(days):
            for key, stops in vehicle["saturday"].items():
                for stop in stops:
                    score = fuzzy_match_score(address, stop["stop"])
                    if score > best_score:
                        best_score = score
                        best = {
                            "vehicle": vehicle,
                            "stop": stop,
                            "schedule_key": key,
                            "schedule_type": "saturday",
                            "score": score,
                            "manual": True,
                        }

    return best


def format_date_with_day(date_str):
    """날짜 문자열에 요일 추가 (예: '4월 10일' → '4월 10일(목)')"""
    # 이미 요일이 포함된 경우 그대로 반환
    if "(" in date_str and ")" in date_str:
        return date_str
    # 날짜 파싱 시도
    m = re.match(r"(\d{1,2})월\s*(\d{1,2})일", date_str)
    if m:
        month = int(m.group(1))
        day = int(m.group(2))
        try:
            year = datetime.now().year
            dt = datetime(year, month, day)
            day_kr = DAY_NAMES_KR[dt.weekday()]
            return f"{month}월 {day}일({day_kr})"
        except ValueError:
            pass
    return date_str


def generate_parent_message(info, result):
    """학부모 안내 문자 생성"""
    stop = result["stop"]
    vehicle = result["vehicle"]

    msg = f"[더숲국어전문학원 차량 안내]\n\n"
    msg += f"안녕하세요, {info['name']} 학생 차량 안내드립니다.\n\n"

    if stop.get("time") and result.get("has_vehicle_info", True):
        msg += f"■ 탑승 정보\n"
        msg += f"- 장소: {stop['stop']}\n"
        msg += f"- 시간: {stop['time']}\n"
        msg += f"- 차량: {vehicle['number']}호차\n"
        msg += f"- 기사님: {vehicle['driver']} ({vehicle['phone']})\n"
    else:
        msg += f"■ 탑승 정보\n"
        msg += f"- 장소: {stop['stop']}\n"

    if stop.get("map_url"):
        msg += f"\n■ 위치 확인\n{stop['map_url']}\n"

    msg += f"\n■ 수업 정보\n"
    msg += f"- 수업: {info['days']} {info['class_time_display']}\n"
    msg += f"- 장소: {info['location']}\n"
    msg += f"- 시작일: {info['start_date']}부터\n"

    msg += f"\n※ 탑승 장소에 5분 전 대기 부탁드립니다."

    return msg


def generate_internal_notice(info, result):
    """내부 차량배정공지방 양식 생성"""
    stop = result["stop"]
    vehicle = result["vehicle"]

    notice = ""
    notice += f"ㅇ 학교/학년/학생명(신규/기존) : {info['school']}/{info['grade']}/{info['name']}({info['status']})\n"

    if stop.get("time") and result.get("has_vehicle_info", True):
        notice += f"ㅇ 등원 차량 : {vehicle['number']}호차({stop['stop']}/{stop['time']})\n"
    else:
        notice += f"ㅇ 등원 차량 : ({stop['stop']})\n"

    notice += f"ㅇ 수업시간 : {info['days']} {info['class_time_display']}\n"
    notice += f"ㅇ 수업장소 : {info['location']}\n"
    notice += f"ㅇ 탑승시작일자 : {info['start_date']}부터\n"
    notice += f"ㅇ 학생 연락처 : {info['student_phone']}\n"
    notice += f"ㅇ 학부모 연락처 : {info['parent_phone']}"

    return notice


def require_input(prompt, default=None):
    """필수 입력. 빈 값이면 반복 요청. default가 있으면 빈 값 시 default 사용."""
    while True:
        suffix = f" (기본: {default})" if default else ""
        val = input(f"{prompt}{suffix}: ").strip()
        if val:
            return val
        if default is not None:
            return default
        print("  → 필수 항목입니다. 입력해주세요.")


def interactive_input():
    """대화형 입력"""
    print("=" * 50)
    print("  더숲국어전문학원 차량배정 자동화")
    print("=" * 50)
    print()

    info = {}
    info["name"] = require_input("학생명")
    info["school"] = require_input("학교")
    info["grade"] = require_input("학년")
    info["status"] = require_input("신규/기존", default="신규")
    info["class_time_raw"] = require_input("수업시간 (예: 7시, 5시30분)")
    info["days_raw"] = require_input("수업요일 (예: 월,수,금)")
    info["location"] = require_input("수업장소 (예: 본원, 더숲1관)", default="본원")
    info["address"] = require_input("학생 주소/동네 (예: 유곡동 에뜰3차, 센트리지 4단지)")
    info["start_date"] = require_input("탑승시작일자 (예: 4월 10일)")
    info["student_phone"] = require_input("학생 연락처")
    info["parent_phone"] = require_input("학부모 연락처")

    # 정규화
    info["class_time"] = normalize_time_input(info["class_time_raw"])
    info["days_list"] = parse_days(info["days_raw"])
    info["days"] = ",".join(info["days_list"])
    info["start_date"] = format_date_with_day(info["start_date"])

    # 수업시간 표시용 (예: "7:00" → "7시", "5:30" → "5시 30분")
    ct = info["class_time"]
    m = re.match(r"(\d{1,2}):(\d{2})", ct)
    if m:
        h, mn = m.group(1), m.group(2)
        info["class_time_display"] = f"{h}시" if mn == "00" else f"{h}시 {int(mn)}분"
    else:
        info["class_time_display"] = ct

    return info


def show_candidates_and_select(results, schedule_time):
    """후보 정류장 표시 + 사용자 선택. 거리/키워드에 따라 가변 개수."""
    # 중복 제거 (같은 호차+정류장)
    seen = set()
    unique = []
    for r in results:
        key = f"{r['vehicle']['number']}_{r['stop']['stop']}"
        if key not in seen:
            seen.add(key)
            unique.append(r)

    if not unique:
        return None

    # 가변 후보 수 결정
    if unique[0].get("distance") is not None:
        # 거리 기반: 1km 이내 정류장 모두 + 최소 3개
        cutoff = max(3, sum(1 for r in unique if r["distance"] <= 1000))
        cutoff = min(cutoff, 10)
    else:
        # 키워드 기반: 점수 > 0인 것, 최대 7개
        cutoff = min(len(unique), 7)

    candidates = unique[:cutoff]

    print(f"\n--- 추천 정류장 ({len(candidates)}개) ---")
    for i, r in enumerate(candidates):
        v = r["vehicle"]
        s = r["stop"]
        day_type = "토" if r["schedule_type"] == "saturday" else "평일"
        sched = f" {r['schedule_key']}" if r["schedule_key"] != schedule_time else ""

        dist_str = ""
        if r.get("distance") is not None:
            d = r["distance"]
            dist_str = f"{d:.0f}m" if d < 1000 else f"{d/1000:.1f}km"
            dist_str = f" ({dist_str})"

        kw_str = ""
        if r.get("keyword_score", 0) > 0:
            kw_str = f" [이름매칭:{r['keyword_score']}점]"

        print(
            f"  [{i+1}] {v['number']}호차 - {s['stop']} ({s['time']})"
            f"{dist_str}{kw_str} [{day_type}{sched}]"
        )

    # 선택
    print()
    choice = input(f"정류장 선택 (1-{len(candidates)}, Enter=1): ").strip()
    idx = int(choice) - 1 if choice.isdigit() else 0
    idx = max(0, min(idx, len(candidates) - 1))

    selected = candidates[idx]
    selected["has_vehicle_info"] = bool(selected["stop"].get("time"))
    return selected


def output_and_copy(info, selected, label=""):
    """결과 출력 + 클립보드 복사"""
    parent_msg = generate_parent_message(info, selected)
    internal_notice = generate_internal_notice(info, selected)

    print(f"\n{'=' * 50}")
    print(f"  [1] 학부모 안내 문자{label}")
    print("=" * 50)
    print(parent_msg)

    print(f"\n{'=' * 50}")
    print(f"  [2] 내부 차량배정공지방 양식{label}")
    print("=" * 50)
    print(internal_notice)

    print("\n" + "-" * 50)
    input("Enter를 누르면 [학부모 안내 문자]를 클립보드에 복사합니다...")
    if copy_to_clipboard(parent_msg):
        print("  >> 학부모 안내 문자가 클립보드에 복사되었습니다!")
    else:
        print("  >> 클립보드 복사 실패. 위 텍스트를 수동으로 복사해주세요.")

    input("Enter를 누르면 [내부 공지 양식]을 클립보드에 복사합니다...")
    if copy_to_clipboard(internal_notice):
        print("  >> 내부 공지 양식이 클립보드에 복사되었습니다!")
    else:
        print("  >> 클립보드 복사 실패. 위 텍스트를 수동으로 복사해주세요.")

    print("\n완료!")


def main():
    data = load_data()
    info = interactive_input()

    schedule_time = info["class_time"]
    days = info["days_list"]
    address = info["address"]

    # 주소 지오코딩
    print(f"\n주소 검색 중: '{address}'...")
    student_lat, student_lng, resolved_name = geocode_address(address)
    if student_lat:
        print(f"  위치 확인: {resolved_name or address} ({student_lat:.4f}, {student_lng:.4f})")
    else:
        print("  [!] 주소 좌표를 찾지 못했습니다. 키워드 매칭으로 전환합니다.")

    student_coords = (student_lat, student_lng) if student_lat else None

    print(f"정류장 검색 중... (시간: {schedule_time}, 요일: {info['days']})")

    # 매칭 정류장 찾기
    results = find_matching_stops(data, schedule_time, days, address, student_coords)

    if not results:
        # 수동배정 fallback
        print(f"\n[!] {schedule_time} 코스표에 매칭 정류장이 없습니다.")
        # 모든 시간대에서 거리순 검색
        all_results = []
        for v in data["vehicles"]:
            if is_weekday_schedule(days):
                for key, stops in v["weekday"].items():
                    for s in stops:
                        entry = {"vehicle": v, "stop": s, "schedule_key": key, "schedule_type": "weekday"}
                        entry["keyword_score"] = fuzzy_match_score(address, s["stop"])
                        if student_coords and s.get("lat"):
                            entry["distance"] = haversine(student_coords[0], student_coords[1], s["lat"], s["lng"])
                        else:
                            entry["distance"] = None
                        all_results.append(entry)

        if student_coords:
            all_results = [r for r in all_results if r["distance"] is not None]
            all_results.sort(key=lambda x: x["distance"])
        else:
            all_results = [r for r in all_results if r["keyword_score"] > 0]
            all_results.sort(key=lambda x: x["keyword_score"], reverse=True)

        if all_results:
            print("    → 수동배정: 다른 시간대에서 가장 가까운 탑승 위치를 찾습니다.")
            print("    ※ 실제 탑승 시간/호차는 배정 선생님이 수동 결정합니다.")
            selected = show_candidates_and_select(all_results, schedule_time)
            if selected:
                selected["has_vehicle_info"] = False
                manual_stop = dict(selected["stop"])
                manual_stop["time"] = ""
                selected["stop"] = manual_stop
                output_and_copy(info, selected, " (수동배정)")
        else:
            print("    주소를 다시 확인하거나, 더 구체적인 키워드를 입력해주세요.")
        return

    # 후보 표시 + 선택
    selected = show_candidates_and_select(results, schedule_time)
    if selected:
        output_and_copy(info, selected)


if __name__ == "__main__":
    main()
