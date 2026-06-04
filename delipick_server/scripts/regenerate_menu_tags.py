import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import pymysql
from dotenv import load_dotenv
from openai import OpenAI

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import recommendation_rules as rules  # noqa: E402

load_dotenv(ROOT_DIR / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def get_db_connection() -> pymysql.connections.Connection:
    requested = os.getenv("DB_NAME", "").strip()
    candidates = [requested] if requested else []
    for db_name in ("delipick", "qqq"):
        if db_name not in candidates:
            candidates.append(db_name)

    last_error: Exception | None = None
    for db_name in candidates:
        try:
            return pymysql.connect(
                host=os.getenv("DB_HOST", "127.0.0.1"),
                user=os.getenv("DB_USER", "root"),
                password=os.getenv("DB_PASSWORD", ""),
                db=db_name,
                charset="utf8mb4",
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=True,
            )
        except pymysql.MySQLError as error:
            last_error = error
            if error.args and error.args[0] == 1049:
                continue
            raise

    if last_error is not None:
        raise last_error
    raise RuntimeError("Unable to connect database.")


def ensure_menu_tags_column(conn: pymysql.connections.Connection) -> None:
    with conn.cursor() as cursor:
        cursor.execute("SHOW COLUMNS FROM menu_flavors LIKE 'menu_tags'")
        exists = cursor.fetchone()
        if exists:
            return

        cursor.execute(
            """
            ALTER TABLE menu_flavors
            ADD COLUMN menu_tags LONGTEXT NULL AFTER review_embedding
            """
        )


def normalize_tag_values(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []

    normalized: list[str] = []
    for value in values:
        tag = str(value).strip()
        if tag in rules._ALL_TAGS and tag not in normalized:
            normalized.append(tag)
    return normalized[:5]


def normalize_menu_tags(payload: dict[str, Any]) -> dict[str, list[str]]:
    return {
        field: normalize_tag_values(payload.get(field))
        for field in rules._TAG_OUTPUT_FIELDS
    }


def heuristic_menu_tags(menu_name: str, category_name: str | None) -> dict[str, list[str]]:
    text = f"{menu_name} {category_name or ''}".replace(" ", "").lower()
    tags = {field: [] for field in rules._TAG_OUTPUT_FIELDS}

    def add(field: str, *values: str) -> None:
        for value in values:
            if value in rules._TAG_SCHEMA[field] and value not in tags[field]:
                tags[field].append(value)

    if any(keyword in text for keyword in ("면", "국수", "우동", "라멘", "쌀국수", "칼국수", "냉면", "파스타", "짜장", "짬뽕")):
        add("food_type", "면")
    if "죽" in text:
        add("food_type", "죽", "밥")
        add("context", "속편함", "든든함")
        add("temperature", "따뜻함")
        add("taste", "담백")
    if any(keyword in text for keyword in ("국물", "탕", "찌개", "국밥", "우동", "라멘", "쌀국수", "칼국수", "짬뽕")):
        add("food_type", "국물")
        add("temperature", "따뜻함")
    if any(keyword in text for keyword in ("밥", "덮밥", "비빔밥", "볶음밥", "국밥", "백반")):
        add("food_type", "밥")
    if any(keyword in text for keyword in ("버거",)):
        add("food_type", "버거")
    if any(keyword in text for keyword in ("닭발",)):
        add("food_type", "닭발")
    if any(keyword in text for keyword in ("치킨", "닭강정")):
        add("food_type", "치킨")
    if any(keyword in text for keyword in ("커피", "아메리카노", "라떼", "에이드", "스무디", "주스", "음료", "티")):
        add("food_type", "음료")
    if any(keyword in text for keyword in ("케이크", "쿠키", "도넛", "디저트", "빙수", "초코")):
        add("food_type", "디저트")
    if any(keyword in text for keyword in ("사리", "추가")):
        add("flags", "추가사리", "옵션메뉴")
    if any(keyword in text for keyword in ("비조리", "직접")):
        add("flags", "비조리")
    if any(keyword in text for keyword in ("토핑",)):
        add("flags", "토핑")
    if any(keyword in text for keyword in ("세트", "set")):
        add("flags", "세트메뉴")
    if any(keyword in text for keyword in ("마라", "매운", "매콤", "불", "핫", "청양")):
        add("taste", "매콤")
    if "마라" in text:
        add("taste", "얼얼")
    if any(keyword in text for keyword in ("고소", "버터", "치즈", "참깨")):
        add("taste", "고소")
    if any(keyword in text for keyword in ("담백", "맑은", "샤브", "쌀국수")):
        add("taste", "담백")
        add("context", "속편함")
    if any(keyword in text for keyword in ("해장", "국밥", "짬뽕")):
        add("context", "해장")

    return tags


def build_prompt() -> str:
    tag_schema = json.dumps(rules._TAG_SCHEMA, ensure_ascii=False)
    return (
        "배달앱 메뉴명을 고정 태그 사전 기반으로 분석하세요.\n"
        "태그는 반드시 tag_schema 안의 값만 사용하세요.\n"
        f"tag_schema={tag_schema}\n\n"
        "출력 JSON 형식:\n"
        "{\n"
        '  "food_type": [],\n'
        '  "taste": [],\n'
        '  "context": [],\n'
        '  "temperature": [],\n'
        '  "flags": []\n'
        "}\n\n"
        "규칙:\n"
        "- 메뉴 하나당 전체 태그는 3~7개 정도만 선택하세요.\n"
        "- 우동, 라멘, 쌀국수, 칼국수, 짬뽕, 파스타, 냉면은 food_type에 면을 넣으세요.\n"
        "- 국물/탕/찌개/국밥/우동/라멘/쌀국수/짬뽕은 food_type에 국물을 넣으세요.\n"
        "- 전복죽, 야채죽, 소고기죽 등 죽 메뉴는 food_type에 죽과 밥을 넣고, 국물이나 면으로 분류하지 마세요.\n"
        "- 죽 메뉴는 context에 속편함, temperature에 따뜻함을 넣는 것이 적절합니다.\n"
        "- 사리, 추가, 토핑, 비조리처럼 단독 식사보다 옵션에 가까운 메뉴는 flags에 표시하세요.\n"
        "- 메뉴명만으로 확실한 태그만 넣고, 과도하게 추측하지 마세요.\n"
        "- JSON 객체만 반환하세요."
    )


def analyze_menu_tags(client: OpenAI, row: dict[str, Any]) -> dict[str, list[str]]:
    menu_name = str(row.get("menu_name") or "")
    category_name = row.get("category_name")
    fallback = heuristic_menu_tags(menu_name, category_name)

    content = {
        "menu_name": menu_name,
        "restaurant_name": row.get("restaurant_name"),
        "category_name": category_name,
        "flavor_reason": row.get("reason"),
        "review_reason": row.get("review_reason"),
    }

    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            response_format={"type": "json_object"},
            temperature=0,
            messages=[
                {"role": "system", "content": build_prompt()},
                {"role": "user", "content": json.dumps(content, ensure_ascii=False)},
            ],
        )
        payload = json.loads(response.choices[0].message.content or "{}")
        if not isinstance(payload, dict):
            return fallback
        normalized = normalize_menu_tags(payload)
        if not any(normalized.values()):
            return fallback
        return normalized
    except Exception as error:
        print(f"[WARN] LLM failed menu_id={row.get('menu_id')}: {error}")
        return fallback


def fetch_target_rows(conn: pymysql.connections.Connection, only_missing: bool) -> list[dict[str, Any]]:
    where_clause = "WHERE mf.menu_tags IS NULL OR mf.menu_tags = ''" if only_missing else ""
    with conn.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT
                mf.menu_id,
                COALESCE(mf.menu_name, m.menu_name) AS menu_name,
                mf.reason,
                mf.review_reason,
                mf.menu_tags,
                m.price,
                r.name AS restaurant_name,
                c.category_name
            FROM menu_flavors mf
            JOIN menus m ON m.id = mf.menu_id
            JOIN restaurants r ON r.id = m.restaurant_id
            LEFT JOIN categories c ON c.category_id = r.category_id
            {where_clause}
            ORDER BY mf.menu_id ASC
            """
        )
        return cursor.fetchall()


def update_menu_tags(conn: pymysql.connections.Connection, menu_id: int, tags: dict[str, list[str]]) -> None:
    payload = json.dumps(tags, ensure_ascii=False, separators=(",", ":"))
    with conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE menu_flavors
            SET menu_tags = %s
            WHERE menu_id = %s
            """,
            (payload, menu_id),
        )


def main() -> None:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is missing. Check delipick_server/.env")

    only_missing = "--all" not in sys.argv
    client = OpenAI(api_key=OPENAI_API_KEY)
    conn = get_db_connection()
    try:
        ensure_menu_tags_column(conn)
        rows = fetch_target_rows(conn, only_missing=only_missing)
        total = len(rows)
        print(f"Target rows: {total} (only_missing={only_missing})")

        for index, row in enumerate(rows, start=1):
            tags = analyze_menu_tags(client, row)
            update_menu_tags(conn, int(row["menu_id"]), tags)
            print(f"[{index}/{total}] menu_id={row['menu_id']} {row['menu_name']} -> {tags}")
            time.sleep(0.05)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
