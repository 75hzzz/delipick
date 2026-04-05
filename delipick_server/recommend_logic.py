import os
import random
from typing import Any

import pymysql
import requests
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY", "").strip()
LAT = float(os.getenv("WEATHER_LAT", "35.104"))
LON = float(os.getenv("WEATHER_LON", "128.974"))

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


def _normalize_spicy_text(user_spicy: str) -> str:
    # 매운맛 입력 정규화
    normalized = (user_spicy or "").strip().lower()
    if normalized in {"mild", "1", "순한맛"}:
        return "순한맛"
    if normalized in {"medium", "2", "중간맛"}:
        return "중간맛"
    if normalized in {"hot", "spicy", "3", "매운맛"}:
        return "매운맛"
    return user_spicy or "미선택"


def _db_candidates() -> list[str]:
    # DB 후보 목록
    requested = os.getenv("DB_NAME", "").strip()
    defaults = [requested] if requested else []
    for name in ("delipick", "qqq"):
        if name not in defaults:
            defaults.append(name)
    return defaults


def _is_unknown_database(error: pymysql.MySQLError) -> bool:
    return bool(error.args and error.args[0] == 1049)


def get_db_connection() -> pymysql.connections.Connection:
    # DB 연결 시도
    last_error: pymysql.MySQLError | None = None
    for db_name in _db_candidates():
        try:
            return pymysql.connect(
                host=os.getenv("DB_HOST", "127.0.0.1"),
                user=os.getenv("DB_USER", "root"),
                password=os.getenv("DB_PASSWORD", ""),
                db=db_name,
                charset="utf8mb4",
                cursorclass=pymysql.cursors.DictCursor,
                connect_timeout=5,
            )
        except pymysql.MySQLError as error:
            last_error = error
            if _is_unknown_database(error):
                continue
            raise

    if last_error is not None:
        raise last_error
    raise RuntimeError("Unable to connect database with known candidates.")


def fetch_realtime_weather() -> tuple[str, float]:
    # 날씨 조회
    if not WEATHER_API_KEY:
        return "맑음", 20.0

    url = (
        "https://api.openweathermap.org/data/2.5/weather"
        f"?lat={LAT}&lon={LON}&appid={WEATHER_API_KEY}&units=metric&lang=kr"
    )
    try:
        res = requests.get(url, timeout=5)
        res.raise_for_status()
        data = res.json()
        main_weather = data["weather"][0]["main"]
        temp = float(data["main"]["temp"])
        mapping = {
            "Clear": "맑음",
            "Clouds": "흐림",
            "Rain": "비",
            "Snow": "눈",
            "Drizzle": "이슬비",
            "Thunderstorm": "천둥번개",
        }
        return mapping.get(main_weather, "맑음"), temp
    except Exception:
        # 조회 실패 fallback
        return "맑음", 20.0


def calculate_queueing_metrics(prep_time: Any, delivery_time: Any, now_hour: int) -> dict[str, Any]:
    """
    입력값:
    - 조리시간(prep_time)
    - 배달시간(delivery_time)
    - 현재 시각(now_hour)

    출력값:
    - 예측 조리시간
    - 대기시간
    - 총 ETA
    - 정렬용 queue_score
    """
    base_prep = float(prep_time) if prep_time and float(prep_time) > 0 else 15.0
    delivery = float(delivery_time) if delivery_time and float(delivery_time) > 0 else 15.0

    # 피크타임 판정
    is_peak = (11 <= now_hour < 14) or (17 <= now_hour < 20)
    if is_peak:
        # 피크타임 가중치
        lam_factor = random.uniform(0.58, 0.78)
        peak_boost = random.uniform(0.10, 0.30) * base_prep
        spike_chance = 0.12
    else:
        lam_factor = random.uniform(0.35, 0.52)
        peak_boost = random.uniform(0.02, 0.12) * base_prep
        spike_chance = 0.05

    prep_noise = random.uniform(0.03, 0.18) * base_prep

    # M/M/1 대기시간 근사
    mu = 1.0 / base_prep
    lam = mu * lam_factor
    mm1_wait_raw = lam / (mu * (mu - lam)) if (mu - lam) > 1e-6 else base_prep * 1.2
    mm1_wait_cap = base_prep * (0.9 if is_peak else 0.6)
    mm1_wait = min(mm1_wait_raw, mm1_wait_cap)

    spike_minutes = random.uniform(6, 14) if random.random() < spike_chance else 0.0

    simulated_prep = base_prep + prep_noise + peak_boost + mm1_wait + spike_minutes

    # ETA 상한 제어
    target_total_cap = 60.0 if is_peak else 52.0
    prep_upper_cap = min(45.0, max(base_prep + 4.0, target_total_cap - delivery))
    simulated_prep = max(base_prep, min(simulated_prep, prep_upper_cap))

    queuing_wait = simulated_prep - base_prep
    total_eta = simulated_prep + delivery
    queue_score = -total_eta

    return {
        "sim_prep_time": simulated_prep,
        "queuing_wait": queuing_wait,
        "total_eta": total_eta,
        "queue_score": queue_score,
        "is_peak_time": is_peak,
        "spike_minutes": spike_minutes,
    }


def get_llm_scores(
    candidates: list[dict[str, Any]],
    user_spicy: str,
    weather_status: str,
    temp: float,
) -> dict[str, int]:
    # LLM 점수 계산
    if not candidates:
        return {}

    # LLM 비활성 fallback
    if client is None:
        return {res["name"]: 50 for res in candidates if res.get("name")}

    context = "".join(
        [
            (
                f"- {res.get('name', '')} | 카테고리: {res.get('category_name', '')} "
                f"| 대표메뉴: {res.get('main_menu', '')} "
                f"| 매운메뉴힌트: {res.get('spicy_menu_hint', '')} "
                f"| 매운메뉴비율: {res.get('spicy_ratio', 0)}\n"
            )
            for res in candidates
        ]
    )

    spicy_text = _normalize_spicy_text(user_spicy)

    # 프롬프트 구성
    prompt = f"""
당신은 음식 취향 필터 전용 심사관입니다.
현재 날씨는 {weather_status}({temp:.1f}°C), 사용자의 매운맛 선호는 '{spicy_text}'입니다.

점수 규칙:
- 취향에 매우 잘 맞으면 80~100
- 애매하게 맞으면 50~79
- 취향과 명확히 다르면 0~49
- 사용자가 '매운맛'을 원하면 매운 메뉴 중심 식당만 높은 점수를 주세요.
- 매운맛 선호일 때 버거/피자/카페/디저트 중심 체인은 원칙적으로 0~25를 주세요.
- 매운메뉴힌트가 비어 있고 매운메뉴비율이 낮으면 낮은 점수를 주세요.
- 사용자가 '순한맛'을 원하면 자극적인 매운 메뉴 중심 식당은 0~35를 주세요.

출력 형식은 반드시 '식당명: 점수' 한 줄씩입니다.

{context}
""".strip()

    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        content = response.choices[0].message.content or ""
        # 모델 출력 파싱
        scores: dict[str, int] = {}
        for line in content.splitlines():
            if ":" not in line:
                continue
            name, raw_score = line.split(":", 1)
            digits = "".join(ch for ch in raw_score if ch.isdigit())
            if not digits:
                continue
            score = max(0, min(100, int(digits)))
            scores[name.strip()] = score

        if not scores:
            # 파싱 실패 fallback
            return {res["name"]: 50 for res in candidates if res.get("name")}
        return scores
    except Exception:
        # 호출 실패 fallback
        return {res["name"]: 50 for res in candidates if res.get("name")}
