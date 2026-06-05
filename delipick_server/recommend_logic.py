import json
import os
import random
import re
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

try:
    from . import recommendation_rules as rules
except ImportError:
    import recommendation_rules as rules

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
ENABLE_TASTE_LLM = os.getenv("ENABLE_TASTE_LLM", "false").lower() in {"1", "true", "yes"}

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


def _compact_text(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").lower())


def _normalize_tag_values(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []

    normalized: list[str] = []
    for value in values:
        tag = str(value).strip()
        if tag in rules._ALL_TAGS and tag not in normalized:
            normalized.append(tag)
    return normalized


def _normalize_avoid_terms(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []

    normalized: list[str] = []
    for value in values:
        term = str(value).strip()
        if 2 <= len(term) <= 20 and term not in normalized:
            normalized.append(term)
    return normalized


def _normalize_embedding_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text[:180]


def _fallback_embedding_texts(intent: dict[str, Any], original_text: str) -> tuple[str, str]:
    must_tags = intent.get("must_tags") if isinstance(intent.get("must_tags"), list) else []
    prefer_tags = intent.get("prefer_tags") if isinstance(intent.get("prefer_tags"), list) else []
    avoid_tags = intent.get("avoid_tags") if isinstance(intent.get("avoid_tags"), list) else []

    menu_parts: list[str] = []
    review_parts: list[str] = []

    for tag in [*must_tags, *prefer_tags]:
        if tag in rules._TAG_SCHEMA["food_type"] or tag in rules._TAG_SCHEMA["taste"] or tag in rules._TAG_SCHEMA["temperature"]:
            menu_parts.append(str(tag))
        if tag in rules._TAG_SCHEMA["context"] or tag in {"속편함", "든든함", "가벼움", "따뜻함"}:
            review_parts.append(str(tag))

    if "매콤" in avoid_tags or "얼얼" in avoid_tags:
        menu_parts.append("안 매운")
    if "느끼함" in avoid_tags or "기름짐" in avoid_tags or "튀김" in avoid_tags:
        menu_parts.extend(["담백한", "가벼운"])
        review_parts.extend(["부담 없는", "가벼운"])
    if "디저트" in avoid_tags and "음료" in avoid_tags:
        menu_parts.append("식사")

    menu_text = " ".join(dict.fromkeys(menu_parts)).strip()
    review_text = " ".join(dict.fromkeys(review_parts)).strip()
    return menu_text or original_text, review_text or menu_text or original_text


def _normalize_tag_intent(payload: dict[str, Any]) -> dict[str, Any]:
    intent_type = str(payload.get("intent_type") or "general").strip()
    if intent_type not in rules._TAG_INTENT_TYPES:
        intent_type = "general"

    return {
        "intent_type": intent_type,
        "must_tags": _normalize_tag_values(payload.get("must_tags")),
        "prefer_tags": _normalize_tag_values(payload.get("prefer_tags")),
        "avoid_tags": _normalize_tag_values(payload.get("avoid_tags")),
        "avoid_terms": _normalize_avoid_terms(payload.get("avoid_terms")),
        "menu_embedding_text": _normalize_embedding_text(payload.get("menu_embedding_text")),
        "review_embedding_text": _normalize_embedding_text(payload.get("review_embedding_text")),
    }


def _has_negated_concept(compact: str, keywords: tuple[str, ...]) -> bool:
    after_markers = ("말고", "싫", "못먹", "빼고", "제외", "피하", "별로", "안먹")
    before_markers = ("안", "못")

    for keyword in keywords:
        target = _compact_text(keyword)
        index = compact.find(target)
        while index >= 0:
            before = compact[max(0, index - 3) : index]
            after = compact[index + len(target) : index + len(target) + 8]
            if any(marker in after for marker in after_markers):
                return True
            if any(before.endswith(marker) for marker in before_markers):
                return True
            index = compact.find(target, index + 1)

    return False


def _apply_negation_overrides(text: str, intent: dict[str, Any]) -> dict[str, Any]:
    compact = _compact_text(text)
    normalized = _normalize_tag_intent(intent)
    meal_request = any(keyword in compact for keyword in ("추천", "음식", "메뉴", "먹고", "먹을", "식사", "밥", "국물", "든든"))

    def add_unique(key: str, *values: str) -> None:
        target = normalized.setdefault(key, [])
        if not isinstance(target, list):
            target = []
            normalized[key] = target
        for value in values:
            if value and value not in target:
                target.append(value)

    def remove_tags(*tags: str) -> None:
        tag_set = set(tags)
        for key in ("must_tags", "prefer_tags"):
            values = normalized.get(key)
            if isinstance(values, list):
                normalized[key] = [value for value in values if value not in tag_set]

    def force_avoid(tags: tuple[str, ...], terms: tuple[str, ...] = (), prefer: tuple[str, ...] = ()) -> None:
        remove_tags(*tags)
        add_unique("avoid_tags", *tags)
        add_unique("avoid_terms", *terms)
        for tag in prefer:
            if tag not in normalized["avoid_tags"]:
                add_unique("prefer_tags", tag)
        if normalized["intent_type"] == "general":
            normalized["intent_type"] = "taste"

    if _has_negated_concept(compact, ("매운", "매콤", "마라", "마라탕", "얼얼", "불닭", "핫")):
        force_avoid(
            ("매콤", "얼얼"),
            ("마라", "마라탕", "매운", "매콤", "불닭"),
            ("담백",),
        )
        if meal_request:
            add_unique("prefer_tags", "속편함", "밥", "국물")
            add_unique("avoid_tags", "디저트", "음료")

    if _has_negated_concept(compact, ("느끼", "기름진", "기름", "튀긴", "튀김", "후라이드")):
        force_avoid(
            ("느끼함", "기름짐", "튀김"),
            ("느끼", "기름", "튀김", "튀긴", "후라이드", "치즈", "크림", "버터", "마요", "아이스크림"),
            ("담백", "가벼움"),
        )
        if meal_request or not normalized["must_tags"]:
            add_unique("prefer_tags", "속편함", "밥", "국물")
            add_unique("avoid_tags", "디저트", "음료")

    if _has_negated_concept(compact, ("달달", "달콤", "디저트", "초코", "케이크", "케익")):
        force_avoid(
            ("달콤", "디저트"),
            ("달달", "달콤", "디저트", "초코", "케이크", "케익"),
        )
        if any(keyword in compact for keyword in ("식사", "밥", "든든")):
            add_unique("prefer_tags", "밥", "든든함")

    if _has_negated_concept(compact, ("커피", "아메리카노", "라떼", "에스프레소")):
        add_unique("avoid_terms", "커피", "아메리카노", "라떼", "에스프레소")
        if any(keyword in compact for keyword in ("음료", "마실", "차가운", "시원")):
            normalized["intent_type"] = "drink"
            add_unique("must_tags", "음료")
            add_unique("prefer_tags", "차가움")

    if _has_negated_concept(compact, ("닭발",)):
        force_avoid(("닭발",), ("닭발",))
        if "야식" in compact:
            add_unique("prefer_tags", "야식")

    if any(keyword in compact for keyword in ("속안좋", "속아프", "배탈", "배아", "배아픔", "배아파", "복통", "설사", "체했", "소화", "부담")):
        add_unique("prefer_tags", "속편함", "담백", "따뜻함")
        add_unique("avoid_tags", "매콤", "얼얼", "기름짐", "느끼함", "디저트", "음료", "튀김", "버거", "치킨", "닭발")
        add_unique("avoid_terms", "마라", "매운", "불닭", "닭발", "버거", "치킨")

    if "국물" in normalized["must_tags"] and "닭발" not in compact:
        add_unique("avoid_tags", "닭발")
        add_unique("avoid_terms", "닭발")

    if not normalized.get("menu_embedding_text") or not normalized.get("review_embedding_text"):
        menu_text, review_text = _fallback_embedding_texts(normalized, text)
        normalized["menu_embedding_text"] = normalized.get("menu_embedding_text") or menu_text
        normalized["review_embedding_text"] = normalized.get("review_embedding_text") or review_text

    return _normalize_tag_intent(normalized)


def _heuristic_preference_tag_intent(text: str) -> dict[str, Any]:
    compact = _compact_text(text)
    must_tags: list[str] = []
    prefer_tags: list[str] = []
    avoid_tags: list[str] = []
    avoid_terms: list[str] = []
    intent_type = "general"

    def add(target: list[str], *tags: str) -> None:
        for tag in tags:
            if tag in rules._ALL_TAGS and tag not in target:
                target.append(tag)

    has_noodle = any(keyword in compact for keyword in ("면", "국수", "우동", "라멘", "쌀국수", "칼국수", "파스타", "냉면"))
    has_soup = any(keyword in compact for keyword in ("국물", "탕", "찌개", "뜨끈", "뜨근", "따뜻"))
    has_drink = any(keyword in compact for keyword in ("음료", "마실", "시원한거", "시원한것", "갈증", "에이드", "커피"))
    has_rice = any(keyword in compact for keyword in ("밥", "덮밥", "비빔밥", "볶음밥", "국밥", "백반"))
    has_porridge = "죽" in compact

    if has_noodle:
        intent_type = "food_form"
        add(must_tags, "면")
        add(avoid_tags, "버거", "닭발", "치킨", "디저트", "음료", "밥", "죽", "옵션메뉴", "추가사리", "비조리", "토핑")
    if has_soup:
        intent_type = "food_form"
        add(must_tags, "국물")
        add(prefer_tags, "따뜻함", "진한", "감칠맛")
        add(avoid_tags, "디저트", "음료")
    if has_drink:
        intent_type = "drink"
        add(must_tags, "음료")
        add(prefer_tags, "차가움")
        add(avoid_tags, "면", "밥", "국물", "탕", "찌개", "닭발", "버거", "치킨", "옵션메뉴", "추가사리")
    if has_rice and not has_noodle:
        intent_type = "food_form"
        add(must_tags, "밥")
        add(prefer_tags, "든든함")
        add(avoid_tags, "디저트", "음료", "옵션메뉴", "추가사리")
    if has_porridge and not has_noodle:
        intent_type = "food_form"
        add(must_tags, "죽")
        add(prefer_tags, "밥", "속편함", "따뜻함", "담백")
        add(avoid_tags, "면", "버거", "닭발", "치킨", "디저트", "음료", "옵션메뉴", "추가사리")

    if any(keyword in compact for keyword in ("안매운", "안매콤", "맵지", "순한", "자극적이지")):
        intent_type = "taste" if intent_type == "general" else intent_type
        add(prefer_tags, "담백")
        add(avoid_tags, "매콤", "얼얼")
    if any(keyword in compact for keyword in ("매운", "매콤", "마라", "얼얼")):
        intent_type = "taste" if intent_type == "general" else intent_type
        add(prefer_tags, "매콤", "얼얼")
    if any(keyword in compact for keyword in ("속안좋", "속아프", "배탈", "배아", "배아픔", "배아파", "복통", "설사", "체했", "소화", "부담")):
        intent_type = "context"
        add(prefer_tags, "속편함", "담백", "따뜻함")
        add(avoid_tags, "매콤", "얼얼", "기름짐", "느끼함", "디저트", "음료", "튀김")

    return {
        "intent_type": intent_type,
        "must_tags": must_tags,
        "prefer_tags": prefer_tags,
        "avoid_tags": avoid_tags,
        "avoid_terms": avoid_terms,
        "menu_embedding_text": "",
        "review_embedding_text": "",
    }


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

    if client is None or not ENABLE_TASTE_LLM:
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


def build_preference_tag_intent(text: str) -> dict[str, Any]:
    if not text.strip():
        return {
            "intent_type": "general",
            "must_tags": [],
            "prefer_tags": [],
            "avoid_tags": [],
            "avoid_terms": [],
            "menu_embedding_text": "",
            "review_embedding_text": "",
        }

    fallback = _apply_negation_overrides(text, _heuristic_preference_tag_intent(text))
    if client is None:
        return fallback

    tag_schema = json.dumps(rules._TAG_SCHEMA, ensure_ascii=False)
    prompt = (
        "사용자 음식 추천 문장을 고정 태그 사전 기반 JSON으로 분석하세요.\n"
        "태그는 반드시 아래 tag_schema에 있는 값만 사용하세요.\n"
        f"tag_schema={tag_schema}\n\n"
        "출력 JSON 형식:\n"
        "{\n"
        '  "intent_type": "direct_menu|food_form|taste|context|drink|general",\n'
        '  "must_tags": ["반드시 만족해야 하는 태그"],\n'
        '  "prefer_tags": ["만족하면 좋은 태그"],\n'
        '  "avoid_tags": ["피해야 하는 태그"],\n'
        '  "avoid_terms": ["메뉴명/가게명에서 피해야 하는 원문 단어"],\n'
        '  "menu_embedding_text": "메뉴 임베딩과 비교할 음식 형태/맛/온도 중심 검색 문장",\n'
        '  "review_embedding_text": "리뷰 임베딩과 비교할 상황/감정/경험 중심 검색 문장"\n'
        "}\n\n"
        "판단 규칙:\n"
        "- '국물 있는 면 요리'처럼 음식 형태가 명확하면 must_tags에 국물, 면을 넣으세요.\n"
        "- '면 요리' 요청에는 버거, 닭발, 치킨, 디저트, 음료, 밥, 죽, 옵션메뉴, 추가사리, 비조리, 토핑을 avoid_tags에 넣으세요.\n"
        "- '죽', '전복죽', '야채죽' 요청은 must_tags에 죽을 넣고, 국물이나 면으로 분류하지 마세요.\n"
        "- '음료' 요청에는 음료를 must_tags에 넣고, 면/밥/국물/닭발/버거/치킨/옵션메뉴/추가사리를 avoid_tags에 넣으세요.\n"
        "- '속이 안 좋다', '배탈', '배아픔', '복통', '설사', '체했다'는 context로 보고 속편함, 담백, 따뜻함을 prefer_tags에 넣으세요.\n"
        "- '말고', '싫어', '못먹어', '빼고', '제외', '피하고', '안 매운'처럼 부정 표현이 붙은 대상은 prefer_tags에 넣지 말고 avoid_tags와 avoid_terms에 넣으세요.\n"
        "- 예: '매운거 말고'는 매콤/얼얼을 avoid_tags에 넣고, '마라탕 말고'는 마라탕/마라를 avoid_terms에 넣으세요.\n"
        "- 예: '느끼한거 못먹어'는 느끼함/기름짐을 avoid_tags에 넣고 담백을 prefer_tags에 넣으세요.\n"
        "- menu_embedding_text에는 음식 형태, 맛, 온도 등 메뉴 자체 특징만 긍정 조건 중심으로 쓰세요.\n"
        "- review_embedding_text에는 속편함, 든든함, 해장, 야식, 가벼움 같은 상황/경험 중심으로 쓰세요.\n"
        "- 부정 대상 단어는 embedding_text 두 문장에 가능하면 넣지 말고 avoid_tags/avoid_terms에만 넣으세요.\n"
        "- 사용자가 원하지 않는 조건만 avoid_tags에 넣고, 확실하지 않은 태그는 prefer_tags로 낮춰 넣으세요.\n"
        "- JSON 객체만 반환하세요."
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
        normalized = _apply_negation_overrides(text, payload)
        if not (normalized["must_tags"] or normalized["prefer_tags"] or normalized["avoid_tags"]):
            return fallback
        return normalized
    except Exception:
        return fallback


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


def build_text_embeddings(texts: list[str]) -> list[list[float]]:
    normalized = [str(text or "").strip() for text in texts]
    if client is None or not any(normalized):
        return [[] for _ in normalized]

    unique_texts: list[str] = []
    unique_indexes: dict[str, int] = {}
    for text in normalized:
        if not text:
            continue
        if text not in unique_indexes:
            unique_indexes[text] = len(unique_texts)
            unique_texts.append(text)

    try:
        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=unique_texts,
        )
        unique_embeddings: list[list[float]] = [[] for _ in unique_texts]
        for item in response.data or []:
            unique_embeddings[int(item.index)] = [float(value) for value in item.embedding]

        return [
            unique_embeddings[unique_indexes[text]] if text and text in unique_indexes else []
            for text in normalized
        ]
    except Exception:
        return [build_text_embedding(text) for text in normalized]
