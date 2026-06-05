import json
import math
import re
from typing import Any

try:
    from . import recommendation_rules as rules
except ImportError:
    import recommendation_rules as rules


def _normalize_taste_levels(raw: dict[str, Any] | None) -> dict[str, int]:
    normalized: dict[str, int] = {}
    for key, value in (raw or {}).items():
        taste_key = str(key)
        if taste_key not in rules._TASTE_KEYS:
            continue
        try:
            level = int(value)
        except Exception:
            continue
        if level in rules._TASTE_LEVEL_RANGES:
            normalized[taste_key] = level
    return normalized


def _clip01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _compact_text(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").lower())


def _tokenize_preference_text(text: str) -> list[str]:
    tokens = re.findall(r"[0-9A-Za-z가-힣]+", (text or "").lower())
    return [
        token
        for token in tokens
        if len(token) >= 2 and token not in rules._TEXT_MATCH_STOPWORDS
    ]


def _keyword_hit_count(haystack: str, keywords: tuple[str, ...]) -> int:
    compact_haystack = _compact_text(haystack)
    return sum(1 for keyword in keywords if _compact_text(keyword) in compact_haystack)


def _experience_intent_score(text: str) -> float:
    compact = _compact_text(text)
    hits = sum(1 for trigger in rules._EXPERIENCE_INTENT_TRIGGERS if _compact_text(trigger) in compact)
    if hits <= 0:
        return 0.0

    direct_intent = _preference_query_direct_intent(text)
    raw_score = 0.35 + (hits * 0.20)
    return _clip01(raw_score * (1.0 - (direct_intent * 0.55)))


def _condition_adjustment_score(text: str, item: dict[str, Any]) -> float:
    compact = _compact_text(text)
    profiles = [
        profile
        for profile in rules._CONTEXT_ADJUSTMENT_PROFILES
        if any(_compact_text(trigger) in compact for trigger in profile["triggers"])
    ]
    if not profiles:
        return 0.0

    restaurant = item.get("restaurant") or {}
    category_name = _normalize_category_name(
        restaurant.get("category_id"),
        restaurant.get("category_name"),
    )
    positive_haystack = " ".join(
        str(value or "")
        for value in (
            item.get("menu_name"),
            category_name,
        )
        if value
    )
    negative_haystack = " ".join(
        str(value or "")
        for value in (
            item.get("menu_name"),
            restaurant.get("name"),
            category_name,
        )
        if value
    )
    if not positive_haystack.strip() and not negative_haystack.strip():
        return 0.0

    adjustment = 0.0
    for profile in profiles:
        pos_hits = _keyword_hit_count(positive_haystack, profile["positive"])
        neg_hits = _keyword_hit_count(negative_haystack, profile["negative"])
        positive_score = min(0.20, pos_hits * float(profile["positive_weight"]))
        negative_score = min(0.40, neg_hits * float(profile["negative_weight"]))
        adjustment += positive_score - negative_score

    return max(-0.42, min(0.24, adjustment))


def _preference_query_direct_intent(text: str) -> float:
    compact = _compact_text(text)
    tokens = _tokenize_preference_text(text)
    if not tokens:
        return 0.0

    has_analogy = any(marker in compact for marker in rules._ANALOGY_MARKERS)
    has_request = any(marker in compact for marker in rules._REQUEST_MARKERS)
    has_craving = any(marker in compact for marker in rules._CRAVING_MARKERS)
    has_attribute = any(term in compact for term in rules._ATTRIBUTE_TERMS)
    has_food_anchor = any(anchor in compact for anchor in rules._FOOD_ANCHORS)

    if has_analogy:
        return 0.25
    if has_request and has_attribute and not has_food_anchor:
        return 0.0
    if len(tokens) <= 2 and not has_request:
        return 1.0
    if len(tokens) <= 3 and has_craving and not has_request:
        return 0.85
    if len(tokens) <= 2 and has_request:
        return 0.75
    return 0.35


def _preference_text_match_score(text: str, row: dict[str, Any]) -> float:
    tokens = _tokenize_preference_text(text)
    if not tokens:
        return 0.0

    haystack = " ".join(
        str(value or "").lower()
        for value in (
            row.get("menu_name"),
            row.get("restaurant_name"),
        )
    )
    haystack = haystack.replace("동죽", "")
    if not haystack.strip():
        return 0.0

    score = 0.0
    for token in tokens:
        if token in haystack:
            score += 0.45
        for key, values in rules._TEXT_MATCH_EXPANSIONS.items():
            if key not in token and token not in key:
                continue
            for expanded in values:
                if expanded and expanded in haystack:
                    score += 0.35 if key in token else 0.18

    return _clip01(score)


def _direct_menu_name_match_scores(text: str, row: dict[str, Any]) -> tuple[float, float]:
    tokens = _tokenize_preference_text(text)
    if not tokens:
        return 0.0, 0.0

    menu_name = str(row.get("menu_name") or "").lower().replace("동죽", "")
    restaurant_name = str(row.get("restaurant_name") or "").lower().replace("동죽", "")
    if not menu_name and not restaurant_name:
        return 0.0, 0.0

    exact_score = 0.0
    related_score = 0.0
    for token in tokens:
        if token in menu_name:
            exact_score = max(exact_score, 1.0)
        elif token in restaurant_name:
            exact_score = max(exact_score, 0.65)
        for key, values in rules._TEXT_MATCH_EXPANSIONS.items():
            if key not in token and token not in key:
                continue
            if key in menu_name:
                related_score = max(related_score, 0.70)
            elif key in restaurant_name:
                related_score = max(related_score, 0.45)
            for expanded in values:
                if expanded in menu_name:
                    related_score = max(related_score, 0.55)
                elif expanded in restaurant_name:
                    related_score = max(related_score, 0.35)

    return _clip01(exact_score), _clip01(related_score)


def _normalize_user_type(raw: str) -> str:
    normalized = (raw or "").strip().lower()
    mapping = {
        "편의형": "convenience",
        "convenience": "convenience",
        "편의": "convenience",
        "미식형": "gourmet",
        "gourmet": "gourmet",
        "foodie": "gourmet",
        "미식": "gourmet",
        "경제형": "budget",
        "budget": "budget",
        "경제": "budget",
    }
    return mapping.get(normalized, "")


def _normalize_category_name(category_id: int | None, raw_name: Any) -> str | None:
    if isinstance(raw_name, str):
        stripped = raw_name.strip()
        if stripped and "?" not in stripped:
            return stripped
    if category_id is not None:
        return rules._CATEGORY_NAME_FALLBACK.get(category_id)
    return None


def _cosine_similarity_0_1(vec1: list[float], vec2: list[float], default: float = 0.5) -> float:
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return default

    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    if norm1 == 0 or norm2 == 0:
        return default

    cosine = dot / (norm1 * norm2)
    return _clip01((cosine + 1.0) / 2.0)


def _euclidean_similarity_0_1(vec1: list[float], vec2: list[float], default: float = 0.5) -> float:
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return default

    max_distance = math.sqrt(float(len(vec1)))
    if max_distance == 0:
        return default

    distance = math.sqrt(sum((a - b) ** 2 for a, b in zip(vec1, vec2)))
    return _clip01(1.0 - (distance / max_distance))


def _parse_embedding(raw: Any) -> list[float]:
    if raw is None:
        return []

    if isinstance(raw, list):
        return [float(v) for v in raw]

    if not isinstance(raw, str):
        return []

    text = raw.strip()
    if not text:
        return []

    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [float(v) for v in parsed]
    except Exception:
        pass

    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return []

    try:
        parsed = json.loads(text[start : end + 1])
        if isinstance(parsed, list):
            return [float(v) for v in parsed]
    except Exception:
        return []
    return []


def _parse_tag_profile(raw: Any) -> set[str]:
    if raw is None:
        return set()

    if isinstance(raw, dict):
        payload = raw
    elif isinstance(raw, str):
        text = raw.strip()
        if not text:
            return set()
        try:
            parsed = json.loads(text)
        except Exception:
            return set()
        if not isinstance(parsed, dict):
            return set()
        payload = parsed
    else:
        return set()

    tags: set[str] = set()
    for field in rules._TAG_OUTPUT_FIELDS:
        values = payload.get(field)
        if not isinstance(values, list):
            continue
        for value in values:
            tag = str(value).strip()
            if tag in rules._ALL_TAGS:
                tags.add(tag)
    return tags


def _infer_tags_from_menu_text(row: dict[str, Any]) -> set[str]:
    restaurant = row.get("restaurant") if isinstance(row.get("restaurant"), dict) else {}
    text = _compact_text(
        " ".join(
            str(value or "")
            for value in (
                row.get("menu_name"),
                row.get("restaurant_name"),
                restaurant.get("name"),
            )
        )
    )
    tags: set[str] = set()

    def add(*values: str) -> None:
        for value in values:
            if value in rules._ALL_TAGS:
                tags.add(value)

    if any(keyword in text for keyword in ("치킨", "닭강정")):
        add("치킨", "기름짐")
    if any(keyword in text for keyword in ("버거", "롯데리아", "버거킹", "노브랜드버거")):
        add("버거", "기름짐")
    if any(keyword in text for keyword in ("후라이드", "튀김", "콰삭", "바사삭", "스노윙")):
        add("튀김", "기름짐")
    if any(keyword in text for keyword in ("치즈", "크림", "버터", "마요")):
        add("느끼함", "기름짐")
    if any(keyword in text for keyword in ("아이스크림", "배스킨", "파인트", "쿼터", "도넛", "케이크", "초코")):
        add("디저트", "달콤")
    if any(keyword in text for keyword in ("스무디", "에이드", "아이스티", "음료")):
        add("음료", "차가움")
    soup_keywords = (
        "국물",
        "국밥",
        "우동",
        "국수",
        "쌀국수",
        "짬뽕",
        "해장국",
        "설렁탕",
        "육수",
        "찌개",
        "전골",
        "오뎅탕",
        "어묵탕",
        "갈비탕",
        "감자탕",
        "곰탕",
        "계란탕",
        "도리탕",
        "떡만두국",
    )
    if any(keyword in text for keyword in soup_keywords):
        add("국물")
    if any(keyword in text for keyword in ("면", "국수", "우동", "라멘", "쌀국수", "칼국수", "냉면", "파스타")):
        add("면")
    if any(keyword in text for keyword in ("밥", "덮밥", "볶음밥", "비빔밥", "국밥", "백반")):
        add("밥")
    if "죽" in text.replace("동죽", ""):
        add("죽", "밥", "속편함", "따뜻함")
    if any(keyword in text for keyword in ("마라", "매운", "매콤", "불닭", "핫")):
        add("매콤", "얼얼")
    if any(keyword in text for keyword in ("닭발",)):
        add("닭발", "야식")

    return tags


def _menu_tags_for_row(row: dict[str, Any]) -> set[str]:
    return _parse_tag_profile(row.get("menu_tags")) | _infer_tags_from_menu_text(row)


def _tag_intent_values(tag_intent: dict[str, Any] | None, key: str) -> set[str]:
    values = (tag_intent or {}).get(key)
    if not isinstance(values, list):
        return set()
    return {str(value).strip() for value in values if str(value).strip() in rules._ALL_TAGS}


def _tag_intent_terms(tag_intent: dict[str, Any] | None, key: str) -> set[str]:
    values = (tag_intent or {}).get(key)
    if not isinstance(values, list):
        return set()
    terms: set[str] = set()
    for value in values:
        term = _compact_text(str(value).strip())
        if len(term) >= 2:
            terms.add(term)
    return terms


def _tag_intent_type(tag_intent: dict[str, Any] | None) -> str:
    intent_type = str((tag_intent or {}).get("intent_type") or "general").strip()
    return intent_type if intent_type in rules._TAG_INTENT_TYPES else "general"


def _menu_tag_match_score(tag_intent: dict[str, Any] | None, row: dict[str, Any]) -> float | None:
    menu_tags = _menu_tags_for_row(row)
    must_tags = _tag_intent_values(tag_intent, "must_tags")
    prefer_tags = _tag_intent_values(tag_intent, "prefer_tags")
    avoid_tags = _tag_intent_values(tag_intent, "avoid_tags")
    avoid_terms = _tag_intent_terms(tag_intent, "avoid_terms")

    if not (must_tags or prefer_tags or avoid_tags or avoid_terms):
        return None

    intent_type = _tag_intent_type(tag_intent)
    if not menu_tags:
        return 0.03 if intent_type in {"food_form", "context", "drink", "direct_menu"} else None

    menu_name = _compact_text(str(row.get("menu_name") or ""))
    if "국물" in must_tags and any(keyword in menu_name for keyword in ("비빔", "볶음", "마른", "드라이")):
        menu_tags = set(menu_tags)
        menu_tags.discard("국물")

    score = 0.45
    if must_tags:
        matched_must = len(must_tags & menu_tags)
        must_ratio = matched_must / len(must_tags)
        score = 0.08 + (0.70 * must_ratio)
        missing_must = len(must_tags) - matched_must
        score -= 0.34 * missing_must

    if prefer_tags:
        prefer_ratio = len(prefer_tags & menu_tags) / len(prefer_tags)
        score += 0.22 * prefer_ratio

    avoid_hits = len(avoid_tags & menu_tags)
    if avoid_hits:
        score -= min(0.75, 0.30 * avoid_hits)

    if avoid_terms:
        text_haystack = _compact_text(
            " ".join(
                str(value or "")
                for value in (
                    row.get("menu_name"),
                    row.get("restaurant_name"),
                )
            )
        )
        avoid_term_hits = sum(1 for term in avoid_terms if term in text_haystack)
        if avoid_term_hits:
            score -= min(0.85, 0.45 * avoid_term_hits)

    if rules._OPTION_TAGS & menu_tags:
        score -= 0.35

    return _clip01(score)


def _has_all_required_tags(tag_intent: dict[str, Any] | None, row: dict[str, Any]) -> bool:
    must_tags = _tag_intent_values(tag_intent, "must_tags")
    if not must_tags:
        return False
    menu_tags = _menu_tags_for_row(row)
    return bool(menu_tags) and must_tags.issubset(menu_tags)


def _has_avoid_match(tag_intent: dict[str, Any] | None, row: dict[str, Any]) -> bool:
    avoid_tags = _tag_intent_values(tag_intent, "avoid_tags")
    avoid_terms = _tag_intent_terms(tag_intent, "avoid_terms")
    if not (avoid_tags or avoid_terms):
        return False

    menu_tags = _menu_tags_for_row(row)
    if avoid_tags & menu_tags:
        return True

    restaurant = row.get("restaurant") if isinstance(row.get("restaurant"), dict) else {}
    text_haystack = _compact_text(
        " ".join(
            str(value or "")
            for value in (
                row.get("menu_name"),
                row.get("restaurant_name"),
                restaurant.get("name"),
            )
        )
    )
    return any(term in text_haystack for term in avoid_terms)


def _should_apply_required_tag_filter(tag_intent: dict[str, Any] | None) -> bool:
    intent_type = _tag_intent_type(tag_intent)
    must_tags = _tag_intent_values(tag_intent, "must_tags")
    return bool(must_tags) and intent_type in {"food_form", "direct_menu", "drink", "context"}


def _should_exclude_food_form_category(
    tag_intent: dict[str, Any] | None,
    row: dict[str, Any],
    preference_text: str = "",
) -> bool:
    intent_type = _tag_intent_type(tag_intent)
    must_tags = _tag_intent_values(tag_intent, "must_tags")
    prefer_tags = _tag_intent_values(tag_intent, "prefer_tags")
    compact_preference = _compact_text(preference_text)
    has_noodle_intent = (
        "면" in must_tags
        or "면" in prefer_tags
        or any(keyword in compact_preference for keyword in ("면", "국수", "우동", "라멘", "쌀국수", "칼국수", "냉면"))
    )
    if intent_type not in {"food_form", "direct_menu", "general"} or not has_noodle_intent:
        return False

    restaurant = row.get("restaurant") if isinstance(row.get("restaurant"), dict) else {}
    category_id = row.get("category_id") or restaurant.get("category_id")
    try:
        return int(category_id) == 5
    except Exception:
        return False


def _tag_weight_by_intent(tag_intent: dict[str, Any] | None) -> float:
    intent_type = _tag_intent_type(tag_intent)
    if intent_type in {"food_form", "direct_menu", "drink"}:
        return 0.62
    if intent_type == "context":
        return 0.52
    if intent_type == "taste":
        if _tag_intent_values(tag_intent, "avoid_tags"):
            return 0.50
        return 0.36
    return 0.25


def _value_or_zero(raw: Any) -> float:
    try:
        if raw is None:
            return 0.0
        return float(raw)
    except Exception:
        return 0.0


def _menu_taste_vector(row: dict[str, Any]) -> list[float]:
    review_values = [
        _value_or_zero(row.get("review_salty")),
        _value_or_zero(row.get("review_sweet")),
        _value_or_zero(row.get("review_sour")),
        _value_or_zero(row.get("review_umami")),
        _value_or_zero(row.get("review_spicy")),
    ]
    base_values = [
        _value_or_zero(row.get("salty")),
        _value_or_zero(row.get("sweet")),
        _value_or_zero(row.get("sour")),
        _value_or_zero(row.get("umami")),
        _value_or_zero(row.get("spicy")),
    ]

    use_review = any(value > 0 for value in review_values)
    selected = review_values if use_review else base_values
    return [_clip01(value) for value in selected]


def _apply_manual_taste_targets(user_taste_vector: list[float], taste_levels: dict[str, int]) -> list[float]:
    adjusted = list(user_taste_vector)
    for key, level in taste_levels.items():
        index = rules._TASTE_KEY_TO_INDEX.get(key)
        target = rules._TASTE_LEVEL_TARGETS.get(level)
        if index is None or target is None or index >= len(adjusted):
            continue
        adjusted[index] = target
    return adjusted


def _manual_taste_range_score(menu_taste: list[float], taste_levels: dict[str, int]) -> float | None:
    scores: list[float] = []
    for key, level in taste_levels.items():
        index = rules._TASTE_KEY_TO_INDEX.get(key)
        taste_range = rules._TASTE_LEVEL_RANGES.get(level)
        if index is None or taste_range is None or index >= len(menu_taste):
            continue

        value = _clip01(float(menu_taste[index]))
        low, high = taste_range
        if low <= value <= high:
            scores.append(1.0)
            continue

        distance = (low - value) if value < low else (value - high)
        scores.append(_clip01(1.0 - (distance / 0.35)))

    if not scores:
        return None
    return _clip01(sum(scores) / len(scores))


def _manual_taste_weight(taste_levels: dict[str, int]) -> float:
    if not taste_levels:
        return 0.0
    return min(0.30, 0.16 + (0.04 * len(taste_levels)))


def _weight_by_user_type(user_type: str, tag_intent: dict[str, Any] | None = None) -> dict[str, float]:
    intent_type = _tag_intent_type(tag_intent)
    must_tags = _tag_intent_values(tag_intent, "must_tags")
    prefer_tags = _tag_intent_values(tag_intent, "prefer_tags")

    if intent_type == "context" and {"속편함", "죽", "따뜻함"} & (must_tags | prefer_tags):
        return {
            "delivery": 0.08,
            "price": 0.08,
            "review": 0.10,
            "preference": 0.74,
        }
    if user_type == "convenience" and intent_type in {"food_form", "drink", "direct_menu"}:
        return {
            "delivery": 0.40,
            "price": 0.10,
            "review": 0.20,
            "preference": 0.30,
        }
    if user_type == "gourmet" and intent_type in {"food_form", "drink", "direct_menu"}:
        return {
            "delivery": 0.10,
            "price": 0.10,
            "review": 0.20,
            "preference": 0.60,
        }
    if user_type == "budget" and intent_type in {"food_form", "drink", "direct_menu"}:
        return {
            "delivery": 0.10,
            "price": 0.50,
            "review": 0.10,
            "preference": 0.30,
        }
    if intent_type in {"food_form", "drink", "direct_menu"}:
        return {
            "delivery": 0.10,
            "price": 0.10,
            "review": 0.10,
            "preference": 0.70,
        }

    if user_type == "convenience":
        return {
            "delivery": 0.40,
            "price": 0.10,
            "review": 0.20,
            "preference": 0.30,
        }
    if user_type == "gourmet":
        return {
            "delivery": 0.1,
            "price": 0.1,
            "review": 0.2,
            "preference": 0.6,
        }
    if user_type == "budget":
        return {
            "delivery": 0.1,
            "price": 0.5,
            "review": 0.1,
            "preference": 0.3,
        }
    return {
        "delivery": 0.15,
        "price": 0.15,
        "review": 0.15,
        "preference": 0.55,
    }


def _reason_text(delivery: float, price: float, review: float, preference: float, personalized: bool) -> str:
    if not personalized:
        return "예상 배달 시간이 빠른 순으로 정렬했어요"

    candidates = [
        ("취향 유사도가 높아요", preference),
        ("리뷰 평점이 좋아요", review),
        ("예상 배달 시간이 빨라요", delivery),
        ("가격 부담이 낮아요", price),
    ]
    ranked = sorted(candidates, key=lambda x: x[1], reverse=True)

    strong = [message for message, score in ranked if score >= 0.65]
    if strong:
        return " · ".join(strong[:2])

    return ranked[0][0]


def _calculate_menu_preference_score(
    row: dict[str, Any],
    user_taste_vector: list[float],
    user_embedding: list[float],
    preference_text: str,
    taste_levels: dict[str, int],
    tag_intent: dict[str, Any] | None = None,
    review_user_embedding: list[float] | None = None,
) -> float:
    user_taste_vector = _apply_manual_taste_targets(user_taste_vector, taste_levels)
    menu_taste = _menu_taste_vector(row)
    taste_similarity = _clip01(
        (_euclidean_similarity_0_1(user_taste_vector, menu_taste, default=0.5) * 0.65)
        + (_cosine_similarity_0_1(user_taste_vector, menu_taste, default=0.5) * 0.35)
    )

    menu_embedding = _parse_embedding(row.get("semantic_embedding"))
    direct_intent = _preference_query_direct_intent(preference_text)
    experience_intent = _experience_intent_score(preference_text)
    tag_score = _menu_tag_match_score(tag_intent, row)
    tag_weight = _tag_weight_by_intent(tag_intent) if tag_score is not None else 0.0

    remaining_weight = 1.0 - tag_weight
    if tag_score is not None:
        taste_weight = remaining_weight * (0.36 - (0.04 * experience_intent))
        menu_weight = remaining_weight * (0.32 - (0.04 * experience_intent))
        review_base_weight = remaining_weight * (0.32 + (0.08 * experience_intent))
    else:
        taste_weight = 0.45 - (0.05 * experience_intent)
        menu_weight = 0.35 - (0.05 * experience_intent)
        review_base_weight = 0.20 + (0.10 * experience_intent)

    score_parts: list[tuple[float, float]] = [(taste_similarity, taste_weight)]
    if tag_score is not None:
        score_parts.append((tag_score, tag_weight))

    manual_taste_score = _manual_taste_range_score(menu_taste, taste_levels)
    if manual_taste_score is not None:
        score_parts.append((manual_taste_score, _manual_taste_weight(taste_levels)))

    if user_embedding and menu_embedding:
        menu_embedding_similarity = _cosine_similarity_0_1(user_embedding, menu_embedding, default=0.5)
        score_parts.append((menu_embedding_similarity, menu_weight))

    review_query_embedding = review_user_embedding if review_user_embedding is not None else user_embedding
    review_embedding = _parse_embedding(row.get("review_embedding"))
    if review_query_embedding and review_embedding:
        review_embedding_similarity = _cosine_similarity_0_1(
            review_query_embedding,
            review_embedding,
            default=0.5,
        )
        review_weight = review_base_weight * (1.0 - (direct_intent * 0.45))
        score_parts.append((review_embedding_similarity, review_weight))
    elif not user_embedding:
        exact_match_score, related_match_score = _direct_menu_name_match_scores(preference_text, row)
        text_match_score = _preference_text_match_score(preference_text, row)
        text_weight = 0.15 + (0.20 * (1.0 - direct_intent))
        related_weight = 0.20 * (1.0 - (direct_intent * 0.5))
        exact_weight = 0.50 * direct_intent

        if text_match_score > 0:
            score_parts.append((text_match_score, text_weight))
        if related_match_score > 0:
            score_parts.append((related_match_score, related_weight))
        if exact_match_score > 0:
            score_parts.append((exact_match_score, exact_weight))

    total_weight = sum(weight for _, weight in score_parts)
    if total_weight <= 0:
        return taste_similarity

    return _clip01(sum(score * weight for score, weight in score_parts) / total_weight)
