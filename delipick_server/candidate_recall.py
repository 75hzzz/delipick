"""Recall inexpensive personalization signals before loading large vectors."""
import os

try:
    from . import recommendation_scoring as scoring
except ImportError:
    import recommendation_scoring as scoring

TASTE_KEYS = ("salty", "sweet", "sour", "umami", "spicy")


def price_bounds(rows):
    values = [float(row["price"]) for row in rows]
    return (min(values), max(values)) if values else (0.0, 0.0)


def price_score(price, bounds):
    low, high = bounds
    return 1.0 if high == low else scoring._clip01(1.0 - (float(price) - low) / (high - low))


def diversified(rows, scores, quota, per_restaurant=2):
    counts = {}
    result = []
    for i in sorted(range(len(rows)), key=lambda i: (-scores[i], int(rows[i]["menu_id"]))):
        restaurant_id = int(rows[i]["restaurant_id"])
        if counts.get(restaurant_id, 0) >= per_restaurant:
            continue
        counts[restaurant_id] = counts.get(restaurant_id, 0) + 1
        result.append(int(rows[i]["menu_id"]))
        if len(result) >= quota:
            break
    return result


def select(rows, req, intent, taste, restaurant_state, bounds):
    """Use only scalar features here; full semantic scoring is still downstream."""
    weights = scoring._weight_by_user_type(req.user_type, intent)
    target = [float(taste.get(k, 0.5)) for k in TASTE_KEYS]
    manual_target = scoring._apply_manual_taste_targets(target, req.taste_levels)
    etas = [state["eta"] for state in restaurant_state.values()]
    low_eta, high_eta = min(etas), max(etas)
    channels = {k: [] for k in ("price", "delivery", "taste", "review", "coarse", "required")}
    # Repeated franchise menus share features, but have different IDs/locations.
    features_cache = {}
    for row in rows:
        state = restaurant_state[int(row["restaurant_id"])]
        key = tuple(row.get(k) for k in ("menu_name", "restaurant_name", "category_id", "menu_tags",
                                         *TASTE_KEYS, *("review_" + k for k in TASTE_KEYS)))
        features = features_cache.get(key)
        if features is None:
            menu_taste = scoring._menu_taste_vector(row)
            taste_score = (scoring._euclidean_similarity_0_1(manual_target, menu_taste) * 0.65
                           + scoring._cosine_similarity_0_1(manual_target, menu_taste) * 0.35)
            manual = scoring._manual_taste_range_score(menu_taste, req.taste_levels)
            if manual is not None:
                taste_score = 0.5 * taste_score + 0.5 * manual
            # Missing vector fields intentionally omit semantic terms in this proxy.
            coarse_preference = scoring._calculate_menu_preference_score(
                row, target, [1.0], req.preference_text, req.taste_levels, intent, [1.0])
            exact, related = scoring._direct_menu_name_match_scores(req.preference_text, row)
            direct = scoring._preference_query_direct_intent(req.preference_text)
            bonus = exact * direct * 0.22 + related * (direct * 0.06 + (1.0 - direct) * 0.10)
            adjustment = scoring._condition_adjustment_score(req.preference_text, {
                "menu_name": row["menu_name"], "restaurant": state["row"]})
            features = (taste_score, coarse_preference, bonus, scoring._has_all_required_tags(intent, row), adjustment)
            features_cache[key] = features
        taste_score, coarse_preference, bonus, required, adjustment = features
        delivery = 1.0 if high_eta == low_eta else 1.0 - (state["eta"] - low_eta) / (high_eta - low_eta)
        price = price_score(row["price"], bounds)
        coarse = (weights["delivery"] * delivery + weights["price"] * price
                  + weights["review"] * state["review"] + weights["preference"] * coarse_preference
                  + bonus + adjustment)
        channels["price"].append(price)
        channels["delivery"].append(delivery)
        channels["taste"].append(taste_score)
        channels["review"].append(state["review"])
        channels["coarse"].append(coarse)
        channels["required"].append(coarse if required else -10.0)
    quota = int(os.getenv("RECALL_CHANNEL_K", "40"))
    mixed_quota = int(os.getenv("RECALL_MIXED_K", "120"))
    picks = {name: diversified(rows, scores, mixed_quota if name == "coarse" else quota,
                               per_restaurant=3 if name == "coarse" else 2)
             for name, scores in channels.items() if name != "required"}
    required_rows = [i for i, score in enumerate(channels["required"]) if score > -10.0]
    if required_rows:
        ordered = sorted(required_rows, key=lambda i: (-channels["required"][i], int(rows[i]["menu_id"])))
        picks["required"] = [int(rows[i]["menu_id"]) for i in ordered[:quota]]
    return sorted({menu_id for ids in picks.values() for menu_id in ids}), {name: len(ids) for name, ids in picks.items()}
