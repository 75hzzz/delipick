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


class RecommendationRequest(BaseModel):
    # 필터 조건
    category_ids: list[int] = Field(default_factory=list)
    min_price: int = 2000
    max_price: int = 100000
    spicy_level: str = ""
    weather_filter: bool = False
    sort: str = "delivery"
    limit: int = 30

    @model_validator(mode="after")
    def validate_ranges(self) -> "RecommendationRequest":
        # 가격 범위 보정
        if self.min_price < 0:
            self.min_price = 0
        if self.max_price < self.min_price:
            self.max_price = self.min_price

        # 정렬 모드 보정
        normalized_sort = self.sort.strip().lower()
        self.sort = normalized_sort if normalized_sort in {"delivery", "recommend"} else "delivery"

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
    # 날씨 조회 조건
    weather_status, weather_temp = ("맑음", 20.0)
    use_weather = req.weather_filter or req.sort == "recommend"
    if use_weather:
        weather_status, weather_temp = fetch_realtime_weather()

    now_hour = datetime.now().hour
    enriched: list[dict[str, Any]] = []

    for row in rows:
        # ETA 계산
        metrics = calculate_queueing_metrics(row.get("prep_time"), row.get("delivery_time"), now_hour)

        # 맵기 보정
        spicy_boost = _spicy_preference_boost(req.spicy_level, row.get("main_menu"))
        queue_score = float(metrics["queue_score"])

        enriched.append(
            {
                **row,
                **metrics,
                "spicy_boost": spicy_boost,
                "base_score": queue_score + spicy_boost,
            }
        )

    # LLM 점수 사용 조건
    use_llm = req.weather_filter or req.sort == "recommend"
    llm_scores: dict[str, int] = {}
    if use_llm and enriched:
        # LLM 입력 구성
        llm_input = [
            {"name": item["name"], "main_menu": item.get("main_menu", "")}
            for item in enriched
        ]
        llm_scores = get_llm_scores(llm_input, req.spicy_level, weather_status, weather_temp)

    for item in enriched:
        # 식당별 LLM 점수
        llm_score = llm_scores.get(item["name"], 0)
        item["llm_score"] = llm_score

        # 정렬 모드별 점수 계산
        if req.sort == "recommend":
            # 추천순
            item["final_score"] = (
                float(llm_score) * 1.0
                + float(item["spicy_boost"]) * 0.35
                - float(item["total_eta"]) * 0.02
            )
        else:
            # 배달순
            item["final_score"] = -float(item["total_eta"])

    # 최종 정렬
    sorted_items = sorted(enriched, key=lambda item: item["final_score"], reverse=True)
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
    sort: str,
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
        sort=sort,
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
    sort: str = Query(default="delivery"),
    limit: int = Query(default=30, ge=1, le=100),
) -> RecommendationResponse:
    # 리스트 조회 엔드포인트
    request = _build_request_from_query(
        category_ids=category_ids,
        min_price=min_price,
        max_price=max_price,
        spicy_level=spicy_level,
        weather_filter=weather_filter,
        sort=sort,
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
