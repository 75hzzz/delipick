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
        calculate_queueing_metrics,
        fetch_realtime_weather,
        get_llm_scores,
    )
    from .update_delivery import scheduler, start_delivery_worker
except ImportError:
    from recommend_logic import (
        calculate_queueing_metrics,
        fetch_realtime_weather,
        get_llm_scores,
    )
    from update_delivery import scheduler, start_delivery_worker

load_dotenv()

# 카테고리명 복구용 기본값
_CATEGORY_NAME_FALLBACK = {
    1: "한식",
    2: "중식",
    3: "일식",
    4: "아시안",
    5: "패스트푸드",
    6: "양식",
    7: "카페",
}

_SPICY_KEYWORDS = ("매운", "마라", "불", "핫", "spicy", "hot", "fire", "엽")
_MILD_FAVOR_CATEGORIES = {5, 6, 7}
_SPICY_FOCUS_CATEGORIES = {1, 2, 3, 4}
_SPICY_BRAND_HINTS = ("엽떡", "신전", "마라", "불닭", "짬뽕", "두찜", "떡볶이", "닭발")
_NONSPICY_BRAND_HINTS = (
    "본죽",
    "롯데리아",
    "노브랜드버거",
    "맥도날드",
    "버거킹",
    "맘스터치",
    "피자",
    "도미노",
    "파파존",
    "스타벅스",
    "카페",
)


class RecommendationRequest(BaseModel):
    # 필터 조건
    category_ids: list[int] = Field(default_factory=list)
    min_price: int = 2000
    max_price: int = 100000
    spicy_level: str = ""
    weather_filter: bool = False
    limit: int = 30

    @model_validator(mode="after")
    def validate_ranges(self) -> "RecommendationRequest":
        # 가격 범위 보정
        if self.min_price < 0:
            self.min_price = 0
        if self.max_price < self.min_price:
            self.max_price = self.min_price

        # 결과 개수 보정
        self.limit = max(1, min(self.limit, 100))
        return self


class CategoryResponse(BaseModel):
    category_id: int
    category_name: str


class RestaurantResponse(BaseModel):
    id: int
    name: str
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
    llm_score: int = 0
    final_score: float


class RecommendationResponse(BaseModel):
    weather_status: str
    weather_temp: float
    count: int
    items: list[RestaurantResponse]


def _parse_allowed_origins() -> list[str]:
    # CORS 오리진 목록 파싱
    raw = os.getenv("CORS_ALLOW_ORIGINS", "*")
    values = [origin.strip() for origin in raw.split(",") if origin.strip()]
    return values or ["*"]


def _parse_bool_env(name: str, default: bool) -> bool:
    # bool 환경변수 파싱
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_int_env(name: str, default: int) -> int:
    # int 환경변수 파싱
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _parse_float_env(name: str, default: float) -> float:
    # float 환경변수 파싱
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


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


app = FastAPI(title="Delipick API", version="1.0.0")
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
    # DB 연결 시도
    last_error: pymysql.MySQLError | None = None

    for db_name in _db_candidates():
        try:
            # 연결 성공 시 즉시 반환
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
            # DB 미존재 오류면 다음 후보 재시도
            if _is_unknown_database(error):
                continue
            raise

    if last_error is not None:
        raise last_error
    raise RuntimeError("Unable to connect database with known candidates.")


def _spicy_preference_boost(spicy_level: str, menu_name: str | None) -> float:
    # 맵기 선호 보정값
    if not spicy_level:
        return 0.0

    # 키워드 유무 감지
    normalized_level = spicy_level.lower().strip()
    menu = (menu_name or "").lower()
    hot_keywords = ["매운", "불", "마라", "핫", "spicy", "hot", "fire"]
    has_hot_menu = any(keyword in menu for keyword in hot_keywords)

    if normalized_level in {"매운맛", "hot", "spicy", "3"}:
        return 15.0 if has_hot_menu else -3.0
    if normalized_level in {"중간맛", "medium", "2"}:
        return 6.0 if has_hot_menu else 2.0
    if normalized_level in {"순한맛", "mild", "1"}:
        return -6.0 if has_hot_menu else 4.0
    return 0.0


def _normalize_category_name(category_id: int | None, raw_name: Any) -> str | None:
    # DB 문자열 품질 확인
    if isinstance(raw_name, str):
        stripped = raw_name.strip()
        if stripped and "?" not in stripped:
            return stripped
    if category_id is not None:
        return _CATEGORY_NAME_FALLBACK.get(category_id)
    return None


def _llm_cutoff_score(req: RecommendationRequest) -> int:
    base_cutoff = _parse_int_env("LLM_FILTER_MIN_SCORE", 60)
    spicy_cutoff = _parse_int_env("LLM_SPICY_MIN_SCORE", 68)
    mild_cutoff = _parse_int_env("LLM_MILD_MIN_SCORE", 52)
    level = req.spicy_level.strip().lower()
    if level in {"hot", "spicy", "매운맛", "3"}:
        return max(base_cutoff, spicy_cutoff)
    if level in {"mild", "순한맛", "1"}:
        return mild_cutoff
    return base_cutoff


def _target_result_count(limit: int) -> int:
    configured = _parse_int_env("LLM_MIN_RESULTS", 10)
    return max(1, min(limit, configured))


def _looks_like_default_llm_scores(scores: dict[str, int]) -> bool:
    if not scores:
        return True
    values = list(scores.values())
    return len(set(values)) == 1 and values[0] == 50


def _contains_spicy_keyword(text: str | None) -> bool:
    value = (text or "").lower()
    return any(keyword in value for keyword in _SPICY_KEYWORDS)


def _name_spicy_affinity(name: str | None) -> float:
    value = (name or "").lower()
    score = 0.0
    if any(keyword in value for keyword in _SPICY_BRAND_HINTS):
        score += 0.55
    if any(keyword in value for keyword in _NONSPICY_BRAND_HINTS):
        score -= 0.75
    return score


def _spicy_signature_strength(item: dict[str, Any]) -> float:
    ratio = float(item.get("spicy_ratio") or 0.0)
    menu_bonus = 0.35 if _contains_spicy_keyword(item.get("main_menu")) else 0.0
    spicy_menu_bonus = 0.45 if _contains_spicy_keyword(item.get("spicy_menu_hint")) else 0.0
    category_id = item.get("category_id")
    if category_id in _SPICY_FOCUS_CATEGORIES:
        cuisine_bonus = 0.15
    elif category_id in _MILD_FAVOR_CATEGORIES:
        cuisine_bonus = -0.20
    else:
        cuisine_bonus = 0.0
    return ratio + menu_bonus + spicy_menu_bonus + cuisine_bonus + _name_spicy_affinity(item.get("name"))


def _passes_hot_gate(item: dict[str, Any], min_strength: float) -> bool:
    strength = _spicy_signature_strength(item)
    category_id = item.get("category_id")
    if category_id in _MILD_FAVOR_CATEGORIES and strength < (min_strength + 0.35):
        return False
    return strength >= min_strength


def _fetch_base_candidates(conn: pymysql.connections.Connection, req: RecommendationRequest) -> list[dict[str, Any]]:
    # 스키마 유무 감지
    with conn.cursor() as cursor:
        cursor.execute("SHOW COLUMNS FROM restaurants")
        restaurant_columns = {row["Field"] for row in cursor.fetchall()}
        cursor.execute("SHOW TABLES LIKE 'restaurant_details'")
        has_restaurant_details = cursor.fetchone() is not None
        detail_columns: set[str] = set()
        if has_restaurant_details:
            cursor.execute("SHOW COLUMNS FROM restaurant_details")
            detail_columns = {row["Field"] for row in cursor.fetchall()}

    # 평점 컬럼 선택
    if "google_rating" in restaurant_columns:
        rating_expr = "r.google_rating"
    elif "rating" in restaurant_columns:
        rating_expr = "r.rating"
    elif has_restaurant_details and "google_rating" in detail_columns:
        rating_expr = "rd.google_rating"
    else:
        rating_expr = "0"
    prep_expr = "r.prep_time" if "prep_time" in restaurant_columns else "NULL"
    delivery_expr = "r.delivery_time" if "delivery_time" in restaurant_columns else "NULL"
    image_expr = "r.image_url" if "image_url" in restaurant_columns else "NULL"
    details_join = "LEFT JOIN restaurant_details rd ON rd.id = r.id" if has_restaurant_details else ""

    # 기본 후보 조회 쿼리
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
        MAX(COALESCE(ms.spicy_ratio, 0)) AS spicy_ratio,
        MAX(ms.spicy_menu_hint) AS spicy_menu_hint,
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
    LEFT JOIN (
        SELECT
            restaurant_id,
            AVG(
                CASE
                    WHEN LOWER(menu_name) REGEXP '매운|마라|불|핫|spicy|hot|fire|엽' THEN 1
                    ELSE 0
                END
            ) AS spicy_ratio,
            MIN(
                CASE
                    WHEN LOWER(menu_name) REGEXP '매운|마라|불|핫|spicy|hot|fire|엽'
                        THEN menu_name
                    ELSE NULL
                END
            ) AS spicy_menu_hint
        FROM menus
        GROUP BY restaurant_id
    ) ms ON ms.restaurant_id = r.id
    {details_join}
    WHERE COALESCE(mp.min_price, 0) BETWEEN %s AND %s
    """
    params: list[Any] = [req.min_price, req.max_price]

    # 카테고리 필터 조건
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
    sql = sql.format(
        rating_expr=rating_expr,
        image_expr=image_expr,
        prep_expr=prep_expr,
        delivery_expr=delivery_expr,
        details_join=details_join,
    )

    with conn.cursor() as cursor:
        # DB 조회 실행
        cursor.execute(sql, params)
        return cursor.fetchall()


def _rank_recommendations(req: RecommendationRequest, rows: list[dict[str, Any]]) -> RecommendationResponse:
    weather_status, weather_temp = ("맑음", 20.0)
    if req.weather_filter:
        weather_status, weather_temp = fetch_realtime_weather()

    now_hour = datetime.now().hour
    enriched: list[dict[str, Any]] = []

    for row in rows:
        metrics = calculate_queueing_metrics(row.get("prep_time"), row.get("delivery_time"), now_hour)
        spicy_boost = _spicy_preference_boost(req.spicy_level, row.get("main_menu"))

        enriched.append(
            {
                **row,
                **metrics,
                "spicy_boost": spicy_boost,
                "base_score": float(metrics["queue_score"]) + spicy_boost,
            }
        )

    target_count = _target_result_count(req.limit)
    spicy_level = req.spicy_level.strip().lower()
    if spicy_level in {"hot", "spicy", "매운맛", "3"}:
        strict_min = _parse_float_env("HOT_SIGNATURE_STRICT_MIN", 0.80)
        relaxed_min = _parse_float_env("HOT_SIGNATURE_RELAXED_MIN", 0.50)
        strict_candidates = [item for item in enriched if _passes_hot_gate(item, strict_min)]
        relaxed_candidates = [item for item in enriched if _passes_hot_gate(item, relaxed_min)]
        if len(strict_candidates) >= target_count:
            enriched = strict_candidates
        elif len(relaxed_candidates) >= target_count:
            enriched = relaxed_candidates
        elif relaxed_candidates:
            enriched = relaxed_candidates
    elif spicy_level in {"mild", "순한맛", "1"}:
        # 순한맛은 강한 매운 시그니처 매장을 대부분 제외한다.
        enriched = [
            item
            for item in enriched
            if _spicy_signature_strength(item) < 0.55
            or item.get("category_id") in _MILD_FAVOR_CATEGORIES
        ]

    use_llm_filter = req.weather_filter or bool(req.spicy_level.strip())
    llm_scores: dict[str, int] = {}
    if use_llm_filter and enriched:
        llm_input = [
            {
                "name": item["name"],
                "category_name": _normalize_category_name(item.get("category_id"), item.get("category_name")) or "",
                "main_menu": item.get("main_menu", ""),
                "spicy_menu_hint": item.get("spicy_menu_hint", ""),
                "spicy_ratio": round(float(item.get("spicy_ratio") or 0.0), 2),
            }
            for item in enriched
        ]
        llm_scores = get_llm_scores(llm_input, req.spicy_level, weather_status, weather_temp)
    llm_filter_available = use_llm_filter and not _looks_like_default_llm_scores(llm_scores)

    for item in enriched:
        llm_score = llm_scores.get(item["name"], 0)
        item["llm_score"] = llm_score
        item["final_score"] = float(llm_score) if use_llm_filter else -float(item["total_eta"])

    filtered_items = enriched
    if llm_filter_available:
        cutoff = _llm_cutoff_score(req)

        def _by_cutoff(current_cutoff: int) -> list[dict[str, Any]]:
            if spicy_level in {"hot", "spicy", "매운맛", "3"}:
                hot_min = _parse_float_env("HOT_SIGNATURE_RELAXED_MIN", 0.45)
                return [
                    item
                    for item in enriched
                    if int(item.get("llm_score") or 0) >= current_cutoff
                    and _passes_hot_gate(item, hot_min)
                ]
            return [
                item for item in enriched if int(item.get("llm_score") or 0) >= current_cutoff
            ]

        filtered_items = _by_cutoff(cutoff)
        while len(filtered_items) < target_count and cutoff > 40:
            cutoff -= 4
            filtered_items = _by_cutoff(cutoff)

        # 컷오프 완화 후에도 비어 있으면 LLM 상위 매장을 최소 개수만큼 노출
        if not filtered_items and enriched:
            if spicy_level in {"hot", "spicy", "매운맛", "3"}:
                emergency_hot = [
                    item for item in enriched if _passes_hot_gate(item, 0.35)
                ]
                source = emergency_hot if emergency_hot else enriched
            else:
                source = enriched
            filtered_items = sorted(source, key=lambda item: int(item.get("llm_score") or 0), reverse=True)[:target_count]

        # 매운맛 결과가 너무 적으면, 매운 시그니처가 있는 차선 후보를 보충한다.
        if spicy_level in {"hot", "spicy", "매운맛", "3"} and len(filtered_items) < target_count and enriched:
            fallback_min = _parse_float_env("HOT_SIGNATURE_FALLBACK_MIN", 0.30)
            supplement_source = [item for item in enriched if _passes_hot_gate(item, fallback_min)]
            if not supplement_source:
                supplement_source = enriched

            existing_ids = {int(item["id"]) for item in filtered_items if item.get("id") is not None}
            supplement_sorted = sorted(
                supplement_source,
                key=lambda item: (
                    int(item.get("llm_score") or 0),
                    _spicy_signature_strength(item),
                    -float(item.get("total_eta") or 9999),
                ),
                reverse=True,
            )

            for item in supplement_sorted:
                item_id = item.get("id")
                if item_id is None:
                    continue
                normalized_id = int(item_id)
                if normalized_id in existing_ids:
                    continue
                filtered_items.append(item)
                existing_ids.add(normalized_id)
                if len(filtered_items) >= target_count:
                    break

    # 기본 노출은 항상 배달 ETA 순
    sorted_items = sorted(filtered_items, key=lambda item: float(item["total_eta"]))
    selected = sorted_items[: req.limit]

    response_items = [
        RestaurantResponse(
            id=item["id"],
            name=item["name"],
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
            llm_score=int(item.get("llm_score") or 0),
            final_score=float(item["final_score"]),
        )
        for item in selected
    ]

    return RecommendationResponse(
        weather_status=weather_status,
        weather_temp=weather_temp,
        count=len(response_items),
        items=response_items,
    )


def _build_request_from_query(
    category_ids: str | None,
    min_price: int,
    max_price: int,
    spicy_level: str,
    weather_filter: bool,
    limit: int,
) -> RecommendationRequest:
    # 카테고리 문자열 파싱
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
        spicy_level=spicy_level,
        weather_filter=weather_filter,
        limit=limit,
    )


@app.on_event("startup")
def on_startup() -> None:
    # 배달시간 워커 시작 조건
    should_start_worker = os.getenv("ENABLE_DELIVERY_WORKER", "false").lower() in {
        "1",
        "true",
        "yes",
    }
    if should_start_worker:
        start_delivery_worker()


@app.on_event("shutdown")
def on_shutdown() -> None:
    # 스케줄러 종료 처리
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
    # 카테고리 목록 조회
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


@app.get("/restaurants", response_model=RecommendationResponse)
def get_restaurants(
    category_ids: str | None = Query(default=None, description="Comma-separated ids. Example: 1,2"),
    min_price: int = Query(default=2000, ge=0),
    max_price: int = Query(default=100000, ge=0),
    spicy_level: str = Query(default=""),
    weather_filter: bool = Query(default=False),
    limit: int = Query(default=30, ge=1, le=100),
) -> RecommendationResponse:
    # 리스트 조회 엔드포인트
    request = _build_request_from_query(
        category_ids=category_ids,
        min_price=min_price,
        max_price=max_price,
        spicy_level=spicy_level,
        weather_filter=weather_filter,
        limit=limit,
    )

    conn = get_db_connection()
    try:
        rows = _fetch_base_candidates(conn, request)
        return _rank_recommendations(request, rows)
    except pymysql.MySQLError as error:
        raise HTTPException(status_code=500, detail=f"DB error: {error}") from error
    finally:
        conn.close()


@app.post("/recommendations", response_model=RecommendationResponse)
def get_recommendations(request: RecommendationRequest) -> RecommendationResponse:
    # JSON body 기반 조회 엔드포인트
    conn = get_db_connection()
    try:
        rows = _fetch_base_candidates(conn, request)
        return _rank_recommendations(request, rows)
    except pymysql.MySQLError as error:
        raise HTTPException(status_code=500, detail=f"DB error: {error}") from error
    finally:
        conn.close()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.getenv("APP_HOST", "0.0.0.0"),
        port=_parse_int_env("APP_PORT", 8000),
        reload=_parse_bool_env("APP_RELOAD", True),
    )
