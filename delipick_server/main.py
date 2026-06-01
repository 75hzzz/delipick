import json
import math
import os
from datetime import datetime
from typing import Any

import pymysql
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator

try:
    from .recommend_logic import (
        build_taste_vector_from_text,
        build_text_embedding,
        calculate_queueing_metrics,
    )
    from .update_delivery import scheduler, start_delivery_worker
except ImportError:
    from recommend_logic import (
        build_taste_vector_from_text,
        build_text_embedding,
        calculate_queueing_metrics,
    )
    from update_delivery import scheduler, start_delivery_worker

load_dotenv()

_CATEGORY_NAME_FALLBACK = {
    1: "한식",
    2: "중식",
    3: "일식",
    4: "아시안",
    5: "패스트푸드",
    6: "양식",
    7: "카페",
}


class RecommendationRequest(BaseModel):
    category_ids: list[int] = Field(default_factory=list)
    min_price: int = 2000
    max_price: int = 100000
    user_type: str = ""
    preference_text: str = ""
    limit: int = 30

    @model_validator(mode="after")
    def validate_ranges(self) -> "RecommendationRequest":
        if self.min_price < 0:
            self.min_price = 0
        if self.max_price < self.min_price:
            self.max_price = self.min_price

        self.user_type = _normalize_user_type(self.user_type)
        self.preference_text = self.preference_text.strip()
        self.limit = max(1, min(self.limit, 100))
        return self


class CategoryResponse(BaseModel):
    category_id: int
    category_name: str


class RestaurantResponse(BaseModel):
    menu_id: int | None = None
    id: int
    name: str
    restaurant_name: str | None = None
    category_id: int | None = None
    category_name: str | None = None
    address: str | None = None
    rating: float = 0.0
    main_menu: str | None = None
    main_menu_price: int | None = None
    image_url: str | None = None
    prep_time: int | None = None
    delivery_time: int | None = None
    estimated_total_time: float
    queuing_wait: float
    is_peak_time: bool
    delivery_score: float
    price_score: float
    restaurant_review_score: float
    preference_score: float
    final_score: float
    recommendation_reason: str | None = None


class RecommendationResponse(BaseModel):
    mode: str
    user_type: str | None = None
    preference_text: str
    count: int
    items: list[RestaurantResponse]


class MenuResponse(BaseModel):
    id: int
    restaurant_id: int
    menu_name: str
    price: int | None = None
    image_url: str | None = None


def _parse_allowed_origins() -> list[str]:
    raw = os.getenv("CORS_ALLOW_ORIGINS", "*")
    values = [origin.strip() for origin in raw.split(",") if origin.strip()]
    return values or ["*"]


def _parse_bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _clip01(value: float) -> float:
    return max(0.0, min(1.0, value))


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
        return _CATEGORY_NAME_FALLBACK.get(category_id)
    return None


def _db_candidates() -> list[str]:
    requested = os.getenv("DB_NAME", "").strip()
    defaults = [requested] if requested else []
    for name in ("delipick", "qqq"):
        if name not in defaults:
            defaults.append(name)
    return defaults


def _is_unknown_database(error: pymysql.MySQLError) -> bool:
    return bool(error.args and error.args[0] == 1049)


app = FastAPI(title="Delipick API", version="2.0.0")
_allowed_origins = _parse_allowed_origins()
_allow_credentials = not (_allowed_origins == ["*"])
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
                autocommit=True,
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


def _weight_by_user_type(user_type: str) -> dict[str, float]:
    if user_type == "convenience":
        return {
            "delivery": 0.5,
            "price": 0.2,
            "review": 0.2,
            "preference": 0.1,
        }
    if user_type == "gourmet":
        return {
            "delivery": 0.1,
            "price": 0.1,
            "review": 0.3,
            "preference": 0.5,
        }
    if user_type == "budget":
        return {
            "delivery": 0.15,
            "price": 0.5,
            "review": 0.15,
            "preference": 0.2,
        }
    return {
        "delivery": 0.25,
        "price": 0.25,
        "review": 0.25,
        "preference": 0.25,
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


def _fetch_base_candidates(conn: pymysql.connections.Connection, req: RecommendationRequest) -> list[dict[str, Any]]:
    with conn.cursor() as cursor:
        cursor.execute("SHOW COLUMNS FROM restaurants")
        restaurant_columns = {row["Field"] for row in cursor.fetchall()}

    rating_expr = "r.google_rating" if "google_rating" in restaurant_columns else "0"
    prep_expr = "r.prep_time" if "prep_time" in restaurant_columns else "NULL"
    delivery_expr = "r.delivery_time" if "delivery_time" in restaurant_columns else "NULL"
    image_expr = "r.image_url" if "image_url" in restaurant_columns else "NULL"

    sql = """
    SELECT
        r.id,
        r.name,
        MAX(r.category_id) AS category_id,
        MAX(c.category_name) AS category_name,
        MAX(r.address) AS address,
        MAX({rating_expr}) AS rating_value,
        MAX({image_expr}) AS restaurant_image_url,
        MAX({prep_expr}) AS prep_time,
        MAX({delivery_expr}) AS delivery_time,
        COALESCE(mp.min_price, 0) AS main_menu_price,
        MIN(m.menu_name) AS main_menu,
        MIN(NULLIF(m.image_url, '')) AS main_menu_image_url
    FROM restaurants r
    LEFT JOIN categories c ON c.category_id = r.category_id
    LEFT JOIN (
        SELECT restaurant_id, MIN(price) AS min_price
        FROM menus
        GROUP BY restaurant_id
    ) mp ON mp.restaurant_id = r.id
    LEFT JOIN menus m
        ON m.restaurant_id = r.id
       AND m.price = mp.min_price
    WHERE COALESCE(mp.min_price, 0) BETWEEN %s AND %s
    """.format(
        rating_expr=rating_expr,
        image_expr=image_expr,
        prep_expr=prep_expr,
        delivery_expr=delivery_expr,
    )
    params: list[Any] = [req.min_price, req.max_price]

    if req.category_ids:
        placeholders = ",".join(["%s"] * len(req.category_ids))
        sql += f" AND r.category_id IN ({placeholders})"
        params.extend(req.category_ids)

    sql += """
    GROUP BY
        r.id,
        r.name,
        mp.min_price
    ORDER BY r.id ASC
    """

    with conn.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchall()


def _fetch_review_scores(conn: pymysql.connections.Connection, restaurant_ids: list[int]) -> dict[int, float]:
    if not restaurant_ids:
        return {}

    placeholders = ",".join(["%s"] * len(restaurant_ids))
    sql = f"""
    SELECT restaurant_id, AVG(review_score) AS avg_review_score
    FROM reviews
    WHERE restaurant_id IN ({placeholders})
    GROUP BY restaurant_id
    """

    with conn.cursor() as cursor:
        cursor.execute(sql, restaurant_ids)
        rows = cursor.fetchall()

    scores: dict[int, float] = {}
    for row in rows:
        rest_id = int(row["restaurant_id"])
        avg_score = row.get("avg_review_score")
        scores[rest_id] = _clip01(float(avg_score)) if avg_score is not None else 0.5
    return scores


def _fetch_menu_flavors(
    conn: pymysql.connections.Connection,
    restaurant_ids: list[int],
    req: RecommendationRequest,
) -> list[dict[str, Any]]:
    if not restaurant_ids:
        return []

    placeholders = ",".join(["%s"] * len(restaurant_ids))
    sql = f"""
    SELECT
        m.restaurant_id,
        m.id AS menu_id,
        m.menu_name,
        m.price,
        m.image_url AS menu_image_url,
        mf.salty,
        mf.sweet,
        mf.sour,
        mf.umami,
        mf.spicy,
        mf.semantic_embedding,
        mf.review_salty,
        mf.review_sweet,
        mf.review_sour,
        mf.review_umami,
        mf.review_spicy,
        mf.review_embedding
    FROM menus m
    LEFT JOIN menu_flavors mf ON mf.menu_id = m.id
    WHERE m.restaurant_id IN ({placeholders})
      AND m.price BETWEEN %s AND %s
    """

    params: list[Any] = [*restaurant_ids, req.min_price, req.max_price]
    with conn.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchall()


def _calculate_menu_preference_score(
    row: dict[str, Any],
    user_taste_vector: list[float],
    user_embedding: list[float],
) -> float:
    menu_taste = _menu_taste_vector(row)
    taste_similarity = _cosine_similarity_0_1(user_taste_vector, menu_taste, default=0.5)

    menu_embedding = _parse_embedding(row.get("semantic_embedding"))
    menu_embedding_similarity = _cosine_similarity_0_1(user_embedding, menu_embedding, default=0.5)

    review_embedding_raw = _parse_embedding(row.get("review_embedding"))
    if not review_embedding_raw:
        review_embedding_similarity = 0.5
    else:
        review_embedding_similarity = _cosine_similarity_0_1(
            user_embedding,
            review_embedding_raw,
            default=0.5,
        )

    return _clip01(
        (taste_similarity * 0.4)
        + (menu_embedding_similarity * 0.3)
        + (review_embedding_similarity * 0.3)
    )


def _rank_recommendations(req: RecommendationRequest, rows: list[dict[str, Any]], conn: pymysql.connections.Connection) -> RecommendationResponse:
    if not rows:
        return RecommendationResponse(
            mode="default_delivery" if not req.preference_text else "personalized",
            user_type=req.user_type or None,
            preference_text=req.preference_text,
            count=0,
            items=[],
        )

    now_hour = datetime.now().hour
    restaurant_ids = [int(row["id"]) for row in rows]

    review_scores = _fetch_review_scores(conn, restaurant_ids)

    enriched: list[dict[str, Any]] = []
    etas: list[float] = []
    prices: list[float] = []

    for row in rows:
        metrics = calculate_queueing_metrics(row.get("prep_time"), row.get("delivery_time"), now_hour)
        eta = float(metrics["total_eta"])
        price = float(row.get("main_menu_price") or 0.0)

        etas.append(eta)
        prices.append(price)

        enriched.append(
            {
                **row,
                **metrics,
                "restaurant_review_score": review_scores.get(int(row["id"]), 0.5),
            }
        )

    min_eta = min(etas)
    max_eta = max(etas)
    min_price = min(prices)
    max_price = max(prices)

    personalized = bool(req.preference_text)
    weights = _weight_by_user_type(req.user_type)

    for item in enriched:
        eta = float(item["total_eta"])
        if max_eta == min_eta:
            delivery_score = 1.0
        else:
            delivery_score = _clip01(1.0 - ((eta - min_eta) / (max_eta - min_eta)))

        review_score = _clip01(float(item.get("restaurant_review_score") or 0.5))

        item["delivery_score"] = delivery_score
        item["restaurant_review_score"] = review_score

    if personalized:
        user_taste = build_taste_vector_from_text(req.preference_text)
        user_taste_vector = [
            float(user_taste.get("salty", 0.5)),
            float(user_taste.get("sweet", 0.5)),
            float(user_taste.get("sour", 0.5)),
            float(user_taste.get("umami", 0.5)),
            float(user_taste.get("spicy", 0.5)),
        ]
        user_embedding = build_text_embedding(req.preference_text)

        flavor_rows = _fetch_menu_flavors(conn, restaurant_ids, req)
        restaurants_by_id = {int(item["id"]): item for item in enriched}
        menu_candidates: list[dict[str, Any]] = []

        for row in flavor_rows:
            rest_id = int(row.get("restaurant_id") or 0)
            rest = restaurants_by_id.get(rest_id)
            if rest is None:
                continue

            menu_price = float(row.get("price") or 0.0)
            preference_score = _calculate_menu_preference_score(
                row=row,
                user_taste_vector=user_taste_vector,
                user_embedding=user_embedding,
            )
            menu_candidates.append(
                {
                    "menu_id": int(row["menu_id"]),
                    "menu_name": row.get("menu_name"),
                    "menu_price": menu_price,
                    "menu_image_url": row.get("menu_image_url"),
                    "restaurant_id": rest_id,
                    "restaurant": rest,
                    "delivery_score": float(rest["delivery_score"]),
                    "review_score": float(rest["restaurant_review_score"]),
                    "preference_score": preference_score,
                    "estimated_total_time": float(rest["total_eta"]),
                    "queuing_wait": float(rest["queuing_wait"]),
                    "is_peak_time": bool(rest["is_peak_time"]),
                }
            )

        if not menu_candidates:
            return RecommendationResponse(
                mode="personalized",
                user_type=req.user_type or None,
                preference_text=req.preference_text,
                count=0,
                items=[],
            )

        menu_prices = [float(item["menu_price"]) for item in menu_candidates]
        min_menu_price = min(menu_prices)
        max_menu_price = max(menu_prices)

        for item in menu_candidates:
            if max_menu_price == min_menu_price:
                price_score = 1.0
            else:
                price_score = _clip01(
                    1.0 - ((float(item["menu_price"]) - min_menu_price) / (max_menu_price - min_menu_price))
                )
            item["price_score"] = price_score
            item["final_score"] = (
                (float(item["delivery_score"]) * weights["delivery"])
                + (price_score * weights["price"])
                + (float(item["review_score"]) * weights["review"])
                + (float(item["preference_score"]) * weights["preference"])
            )
            item["recommendation_reason"] = _reason_text(
                float(item["delivery_score"]),
                price_score,
                float(item["review_score"]),
                float(item["preference_score"]),
                True,
            )

        sorted_items = sorted(
            menu_candidates,
            key=lambda item: (float(item["final_score"]), -float(item["estimated_total_time"])),
            reverse=True,
        )
        selected = sorted_items[: req.limit]
        response_items = [
            RestaurantResponse(
                menu_id=int(item["menu_id"]),
                id=int(item["restaurant_id"]),
                name=str(item.get("menu_name") or ""),
                restaurant_name=str(item["restaurant"].get("name") or ""),
                category_id=item["restaurant"].get("category_id"),
                category_name=_normalize_category_name(
                    item["restaurant"].get("category_id"),
                    item["restaurant"].get("category_name"),
                ),
                address=item["restaurant"].get("address"),
                rating=float(item["restaurant"].get("rating_value") or 0.0),
                main_menu=str(item.get("menu_name") or ""),
                main_menu_price=int(item["menu_price"]) if item.get("menu_price") is not None else None,
                image_url=(
                    item.get("menu_image_url")
                    or item["restaurant"].get("main_menu_image_url")
                    or item["restaurant"].get("restaurant_image_url")
                    or None
                ),
                prep_time=int(item["restaurant"]["prep_time"]) if item["restaurant"].get("prep_time") is not None else None,
                delivery_time=(
                    int(item["restaurant"]["delivery_time"])
                    if item["restaurant"].get("delivery_time") is not None
                    else None
                ),
                estimated_total_time=float(item["estimated_total_time"]),
                queuing_wait=float(item["queuing_wait"]),
                is_peak_time=bool(item["is_peak_time"]),
                delivery_score=float(item["delivery_score"]),
                price_score=float(item["price_score"]),
                restaurant_review_score=float(item["review_score"]),
                preference_score=float(item["preference_score"]),
                final_score=float(item["final_score"]),
                recommendation_reason=str(item["recommendation_reason"]),
            )
            for item in selected
        ]
        mode = "personalized"
    else:
        for item in enriched:
            price = float(item.get("main_menu_price") or 0.0)
            if max_price == min_price:
                price_score = 1.0
            else:
                price_score = _clip01(1.0 - ((price - min_price) / (max_price - min_price)))
            item["price_score"] = price_score
            item["preference_score"] = 0.5
            item["final_score"] = float(item["delivery_score"])
            item["recommendation_reason"] = _reason_text(
                float(item["delivery_score"]),
                price_score,
                float(item["restaurant_review_score"]),
                0.5,
                False,
            )

        sorted_items = sorted(enriched, key=lambda item: float(item["total_eta"]))
        selected = sorted_items[: req.limit]
        response_items = [
            RestaurantResponse(
                menu_id=None,
                id=item["id"],
                name=item["name"],
                restaurant_name=item.get("name"),
                category_id=item.get("category_id"),
                category_name=_normalize_category_name(item.get("category_id"), item.get("category_name")),
                address=item.get("address"),
                rating=float(item.get("rating_value") or 0.0),
                main_menu=item.get("main_menu"),
                main_menu_price=int(item["main_menu_price"]) if item.get("main_menu_price") is not None else None,
                image_url=(item.get("main_menu_image_url") or item.get("restaurant_image_url") or None),
                prep_time=int(item["prep_time"]) if item.get("prep_time") is not None else None,
                delivery_time=int(item["delivery_time"]) if item.get("delivery_time") is not None else None,
                estimated_total_time=float(item["total_eta"]),
                queuing_wait=float(item["queuing_wait"]),
                is_peak_time=bool(item["is_peak_time"]),
                delivery_score=float(item.get("delivery_score") or 0.0),
                price_score=float(item.get("price_score") or 0.0),
                restaurant_review_score=float(item.get("restaurant_review_score") or 0.5),
                preference_score=float(item.get("preference_score") or 0.5),
                final_score=float(item.get("final_score") or 0.0),
                recommendation_reason=item.get("recommendation_reason"),
            )
            for item in selected
        ]
        mode = "default_delivery"

    return RecommendationResponse(
        mode=mode,
        user_type=req.user_type or None,
        preference_text=req.preference_text,
        count=len(response_items),
        items=response_items,
    )


def _build_request_from_query(
    category_ids: str | None,
    min_price: int,
    max_price: int,
    user_type: str,
    preference_text: str,
    limit: int,
) -> RecommendationRequest:
    parsed_categories: list[int] = []
    if category_ids:
        parsed_categories = [
            int(value.strip())
            for value in category_ids.split(",")
            if value.strip().isdigit()
        ]

    return RecommendationRequest(
        category_ids=parsed_categories,
        min_price=min_price,
        max_price=max_price,
        user_type=user_type,
        preference_text=preference_text,
        limit=limit,
    )


@app.on_event("startup")
def on_startup() -> None:
    should_start_worker = os.getenv("ENABLE_DELIVERY_WORKER", "false").lower() in {
        "1",
        "true",
        "yes",
    }
    if should_start_worker:
        start_delivery_worker()


@app.on_event("shutdown")
def on_shutdown() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)


@app.get("/")
def root() -> dict[str, Any]:
    return {
        "service": "delipick-api",
        "status": "ok",
        "docs": "/docs",
    }


@app.get("/health")
def health_check() -> dict[str, Any]:
    return {"status": "ok", "service": "delipick-api"}


@app.get("/categories", response_model=list[CategoryResponse])
def get_categories() -> list[CategoryResponse]:
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT category_id, category_name FROM categories ORDER BY category_id ASC"
            )
            rows = cursor.fetchall()
            return [
                CategoryResponse(
                    category_id=row["category_id"],
                    category_name=_normalize_category_name(
                        row.get("category_id"),
                        row.get("category_name"),
                    )
                    or "",
                )
                for row in rows
            ]
    except pymysql.MySQLError as error:
        raise HTTPException(status_code=500, detail=f"DB error: {error}") from error
    finally:
        conn.close()


@app.get("/restaurants/{restaurant_id}/menus", response_model=list[MenuResponse])
def get_restaurant_menus(restaurant_id: int) -> list[MenuResponse]:
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, restaurant_id, menu_name, price, image_url"
                " FROM menus WHERE restaurant_id=%s ORDER BY id ASC",
                (restaurant_id,),
            )
            rows = cursor.fetchall()
            return [
                MenuResponse(
                    id=row["id"],
                    restaurant_id=row["restaurant_id"],
                    menu_name=row["menu_name"] or "",
                    price=row.get("price"),
                    image_url=row.get("image_url"),
                )
                for row in rows
            ]
    except pymysql.MySQLError as error:
        raise HTTPException(status_code=500, detail=f"DB error: {error}") from error
    finally:
        conn.close()


@app.get("/restaurants", response_model=RecommendationResponse)
def get_restaurants(
    category_ids: str | None = Query(default=None, description="Comma-separated ids. Example: 1,2"),
    min_price: int = Query(default=2000, ge=0),
    max_price: int = Query(default=100000, ge=0),
    user_type: str = Query(default=""),
    preference_text: str = Query(default=""),
    limit: int = Query(default=30, ge=1, le=100),
) -> RecommendationResponse:
    request = _build_request_from_query(
        category_ids=category_ids,
        min_price=min_price,
        max_price=max_price,
        user_type=user_type,
        preference_text=preference_text,
        limit=limit,
    )

    conn = get_db_connection()
    try:
        rows = _fetch_base_candidates(conn, request)
        return _rank_recommendations(request, rows, conn)
    except pymysql.MySQLError as error:
        raise HTTPException(status_code=500, detail=f"DB error: {error}") from error
    finally:
        conn.close()


@app.post("/recommendations", response_model=RecommendationResponse)
def get_recommendations(request: RecommendationRequest) -> RecommendationResponse:
    conn = get_db_connection()
    try:
        rows = _fetch_base_candidates(conn, request)
        return _rank_recommendations(request, rows, conn)
    except pymysql.MySQLError as error:
        raise HTTPException(status_code=500, detail=f"DB error: {error}") from error
    finally:
        conn.close()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=os.getenv("APP_HOST", "0.0.0.0"),
        port=_parse_int_env("APP_PORT", 8000),
        reload=_parse_bool_env("APP_RELOAD", True),
    )
