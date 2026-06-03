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

try:
    from . import recommendation_scoring as scoring
except ImportError:
    import recommendation_scoring as scoring

load_dotenv()


class RecommendationRequest(BaseModel):
    category_ids: list[int] = Field(default_factory=list)
    min_price: int = 2000
    max_price: int = 100000
    user_type: str = ""
    preference_text: str = ""
    taste_levels: dict[str, int] = Field(default_factory=dict)
    limit: int = 30

    @model_validator(mode="after")
    def validate_ranges(self) -> "RecommendationRequest":
        if self.min_price < 0:
            self.min_price = 0
        if self.max_price < self.min_price:
            self.max_price = self.min_price

        self.user_type = scoring._normalize_user_type(self.user_type)
        self.preference_text = self.preference_text.strip()
        self.taste_levels = scoring._normalize_taste_levels(self.taste_levels)
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
        WHERE price BETWEEN %s AND %s
        GROUP BY restaurant_id
    ) mp ON mp.restaurant_id = r.id
    LEFT JOIN menus m
        ON m.restaurant_id = r.id
       AND m.price = mp.min_price
    WHERE mp.min_price IS NOT NULL
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
        scores[rest_id] = scoring._clip01(float(avg_score)) if avg_score is not None else 0.5
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
        r.name AS restaurant_name,
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
    JOIN restaurants r ON r.id = m.restaurant_id
    LEFT JOIN menu_flavors mf ON mf.menu_id = m.id
    WHERE m.restaurant_id IN ({placeholders})
      AND m.price BETWEEN %s AND %s
    """

    params: list[Any] = [*restaurant_ids, req.min_price, req.max_price]
    with conn.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchall()


def _rank_recommendations(req: RecommendationRequest, rows: list[dict[str, Any]], conn: pymysql.connections.Connection) -> RecommendationResponse:
    if not rows:
        return RecommendationResponse(
            mode="personalized" if (req.preference_text or req.taste_levels) else "default_delivery",
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

    personalized = bool(req.preference_text or req.taste_levels)
    weights = scoring._weight_by_user_type(req.user_type)

    for item in enriched:
        eta = float(item["total_eta"])
        if max_eta == min_eta:
            delivery_score = 1.0
        else:
            delivery_score = scoring._clip01(1.0 - ((eta - min_eta) / (max_eta - min_eta)))

        review_score = scoring._clip01(float(item.get("restaurant_review_score") or 0.5))

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
            preference_score = scoring._calculate_menu_preference_score(
                row=row,
                user_taste_vector=user_taste_vector,
                user_embedding=user_embedding,
                preference_text=req.preference_text,
                taste_levels=req.taste_levels,
            )
            direct_intent = scoring._preference_query_direct_intent(req.preference_text)
            exact_match_score, related_match_score = scoring._direct_menu_name_match_scores(req.preference_text, row)
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
                    "direct_intent": direct_intent,
                    "exact_match_score": exact_match_score,
                    "related_match_score": related_match_score,
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
                price_score = scoring._clip01(
                    1.0 - ((float(item["menu_price"]) - min_menu_price) / (max_menu_price - min_menu_price))
                )
            item["price_score"] = price_score
            item["condition_adjustment"] = scoring._condition_adjustment_score(req.preference_text, item)
            item["final_score"] = scoring._clip01(
                (float(item["delivery_score"]) * weights["delivery"])
                + (price_score * weights["price"])
                + (float(item["review_score"]) * weights["review"])
                + (float(item["preference_score"]) * weights["preference"])
                + (float(item["exact_match_score"]) * float(item["direct_intent"]) * 0.22)
                + (
                    float(item["related_match_score"])
                    * ((float(item["direct_intent"]) * 0.06) + ((1.0 - float(item["direct_intent"])) * 0.10))
                )
                + float(item["condition_adjustment"])
            )
            item["recommendation_reason"] = scoring._reason_text(
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
                category_name=scoring._normalize_category_name(
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
                price_score = scoring._clip01(1.0 - ((price - min_price) / (max_price - min_price)))
            item["price_score"] = price_score
            item["preference_score"] = 0.5
            item["final_score"] = float(item["delivery_score"])
            item["recommendation_reason"] = scoring._reason_text(
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
                category_name=scoring._normalize_category_name(item.get("category_id"), item.get("category_name")),
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
    taste_levels: str,
    limit: int,
) -> RecommendationRequest:
    parsed_categories: list[int] = []
    if category_ids:
        parsed_categories = [
            int(value.strip())
            for value in category_ids.split(",")
            if value.strip().isdigit()
        ]

    parsed_taste_levels: dict[str, int] = {}
    for entry in (taste_levels or "").split(","):
        if ":" not in entry:
            continue
        key, value = entry.split(":", 1)
        key = key.strip()
        try:
            parsed_taste_levels[key] = int(value.strip())
        except Exception:
            continue

    return RecommendationRequest(
        category_ids=parsed_categories,
        min_price=min_price,
        max_price=max_price,
        user_type=user_type,
        preference_text=preference_text,
        taste_levels=parsed_taste_levels,
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
                    category_name=scoring._normalize_category_name(
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
    taste_levels: str = Query(default=""),
    limit: int = Query(default=30, ge=1, le=100),
) -> RecommendationResponse:
    request = _build_request_from_query(
        category_ids=category_ids,
        min_price=min_price,
        max_price=max_price,
        user_type=user_type,
        preference_text=preference_text,
        taste_levels=taste_levels,
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
