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
    normalized = (user_spicy or "").strip().lower()
    if normalized in {"mild", "1", "순한맛"}:
        return "순한맛"
    if normalized in {"medium", "2", "중간맛"}:
        return "중간맛"
    if normalized in {"hot", "spicy", "3", "매운맛"}:
        return "매운맛"
    return user_spicy or "미선택"


def _db_candidates() -> list[str]:
    requested = os.getenv("DB_NAME", "").strip()
    defaults = [requested] if requested else []
    for name in ("delipick", "qqq"):
        if name not in defaults:
            defaults.append(name)
    return defaults


def _is_unknown_database(error: pymysql.MySQLError) -> bool:
    return bool(error.args and error.args[0] == 1049)


def get_db_connection() -> pymysql.connections.Connection:
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
        return "맑음", 20.0


def calculate_queueing_metrics(prep_time: Any, delivery_time: Any, now_hour: int) -> dict[str, Any]:
    """
    주어진 조리시간/배달시간을 기반으로 피크타임 가중치를 반영해
    예측 조리시간, 대기시간, 총 ETA를 계산한다.
    """
    base_prep = float(prep_time) if prep_time and float(prep_time) > 0 else 15.0
    delivery = float(delivery_time) if delivery_time and float(delivery_time) > 0 else 15.0

    is_peak = (11 <= now_hour < 14) or (17 <= now_hour < 20)
    if is_peak:
        # 피크타임 과증폭을 줄여 ETA가 60~70분으로 고정되지 않도록 완화
        lam_factor = random.uniform(0.58, 0.78)
        peak_boost = random.uniform(0.10, 0.30) * base_prep
        spike_chance = 0.12
    else:
        lam_factor = random.uniform(0.35, 0.52)
        peak_boost = random.uniform(0.02, 0.12) * base_prep
        spike_chance = 0.05

    prep_noise = random.uniform(0.03, 0.18) * base_prep

    mu = 1.0 / base_prep
    lam = mu * lam_factor
    mm1_wait_raw = lam / (mu * (mu - lam)) if (mu - lam) > 1e-6 else base_prep * 1.2
    mm1_wait_cap = base_prep * (0.9 if is_peak else 0.6)
    mm1_wait = min(mm1_wait_raw, mm1_wait_cap)

    spike_minutes = random.uniform(6, 14) if random.random() < spike_chance else 0.0

    simulated_prep = base_prep + prep_noise + peak_boost + mm1_wait + spike_minutes

    # 총 ETA가 과도하게 커지지 않게 prep 상한을 배달시간과 연동
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
    if not candidates:
        return {}

    if client is None:
        return {res["name"]: 50 for res in candidates if res.get("name")}

    context = "".join(
        [f"- {res.get('name', '')} (메뉴: {res.get('main_menu', '')})\n" for res in candidates]
    )

    spicy_text = _normalize_spicy_text(user_spicy)

    prompt = f"""
당신은 맛집 추천 전문가입니다.
현재 날씨는 {weather_status}({temp:.1f}°C), 사용자의 매운맛 선호는 '{spicy_text}'입니다.
아래 식당 메뉴를 보고 0~100 사이 점수를 매겨 주세요.
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
            return {res["name"]: 50 for res in candidates if res.get("name")}
        return scores
    except Exception:
        return {res["name"]: 50 for res in candidates if res.get("name")}
