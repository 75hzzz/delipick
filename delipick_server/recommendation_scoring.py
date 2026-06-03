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

    menu_name = str(row.get("menu_name") or "").lower()
    restaurant_name = str(row.get("restaurant_name") or "").lower()
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


def _weight_by_user_type(user_type: str) -> dict[str, float]:
    if user_type == "convenience":
        return {
            "delivery": 0.4,
            "price": 0.15,
            "review": 0.15,
            "preference": 0.3,
        }
    if user_type == "gourmet":
        return {
            "delivery": 0.1,
            "price": 0.1,
            "review": 0.15,
            "preference": 0.65,
        }
    if user_type == "budget":
        return {
            "delivery": 0.1,
            "price": 0.45,
            "review": 0.15,
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
    taste_weight = 0.45 - (0.05 * experience_intent)
    menu_weight = 0.35 - (0.05 * experience_intent)
    score_parts: list[tuple[float, float]] = [(taste_similarity, taste_weight)]

    manual_taste_score = _manual_taste_range_score(menu_taste, taste_levels)
    if manual_taste_score is not None:
        score_parts.append((manual_taste_score, _manual_taste_weight(taste_levels)))

    if user_embedding and menu_embedding:
        menu_embedding_similarity = _cosine_similarity_0_1(user_embedding, menu_embedding, default=0.5)
        score_parts.append((menu_embedding_similarity, menu_weight))

    review_embedding = _parse_embedding(row.get("review_embedding"))
    if user_embedding and review_embedding:
        review_embedding_similarity = _cosine_similarity_0_1(
            user_embedding,
            review_embedding,
            default=0.5,
        )
        base_review_weight = 0.20 + (0.10 * experience_intent)
        review_weight = base_review_weight * (1.0 - (direct_intent * 0.45))
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
