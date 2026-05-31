import json
import os
import random
import re
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


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


def _clip01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _extract_json_object(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {}

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return {}

    try:
        parsed = json.loads(match.group(0))
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        return {}
    return {}


def _heuristic_taste_vector(text: str) -> dict[str, float]:
    lower = (text or "").lower()
    vector = {
        "salty": 0.5,
        "sweet": 0.5,
        "sour": 0.5,
        "umami": 0.5,
        "spicy": 0.5,
    }
    boosts = {
        "salty": ("짭", "짠", "간장", "소금"),
        "sweet": ("달", "디저트", "초코", "케이크", "아이스크림"),
        "sour": ("새콤", "상큼", "신맛", "레몬", "식초"),
        "umami": ("감칠", "진한", "고기", "국물", "육수"),
        "spicy": ("매운", "마라", "불", "핫", "spicy", "hot"),
    }
    for key, keywords in boosts.items():
        hits = sum(1 for word in keywords if word in lower)
        vector[key] = _clip01(vector[key] + (0.15 * hits))
    return vector


def build_taste_vector_from_text(text: str) -> dict[str, float]:
    # 자연어 -> 5차원 맛 벡터 생성
    if not text.strip():
        return {
            "salty": 0.5,
            "sweet": 0.5,
            "sour": 0.5,
            "umami": 0.5,
            "spicy": 0.5,
        }

    if client is None:
        return _heuristic_taste_vector(text)

    prompt = (
        "사용자 음식 취향 문장을 분석해 salty, sweet, sour, umami, spicy 값을 "
        "각각 0.0~1.0 실수로 반환하세요. 반드시 JSON 객체만 반환하세요."
    )

    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            response_format={"type": "json_object"},
            temperature=0,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": text},
            ],
        )
        payload = _extract_json_object(response.choices[0].message.content or "")
        return {
            "salty": _clip01(float(payload.get("salty", 0.5))),
            "sweet": _clip01(float(payload.get("sweet", 0.5))),
            "sour": _clip01(float(payload.get("sour", 0.5))),
            "umami": _clip01(float(payload.get("umami", 0.5))),
            "spicy": _clip01(float(payload.get("spicy", 0.5))),
        }
    except Exception:
        return _heuristic_taste_vector(text)


def build_text_embedding(text: str) -> list[float]:
    # 자연어 -> 임베딩 벡터 생성
    if not text.strip() or client is None:
        return []

    try:
        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text,
        )
        embedding = response.data[0].embedding if response.data else []
        return [float(value) for value in embedding]
    except Exception:
        return []
