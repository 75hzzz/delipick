import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd
import pymysql
from dotenv import load_dotenv
from openai import OpenAI


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

load_dotenv(ROOT_DIR / ".env")

FOOD_DB_URL = "https://various.foodsafetykorea.go.kr/nutrient/general/down/historyList.do"
DEFAULT_FOOD_DB_SHEET = "국가표준식품성분 Database 10.3"
DEFAULT_FLAVOR_MODEL = os.getenv("MENU_FLAVOR_MODEL") or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
DEFAULT_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

TASTE_KEYS = ("salty", "sweet", "sour", "umami", "spicy")
NUTRIENT_COLUMNS = [
    "식품명",
    "당류",
    "나트륨",
    "칼륨",
    "단백질",
    "지방",
    "비타민 C",
    "아스파르트산",
    "글루탐산",
]

SEARCH_KEYWORDS = [
    "김치",
    "볶음밥",
    "밥",
    "계란",
    "달걀",
    "마라",
    "로제",
    "떡볶이",
    "떡",
    "고추",
    "고춧가루",
    "치킨",
    "닭",
    "돼지",
    "소고기",
    "쇠고기",
    "불고기",
    "제육",
    "새우",
    "오징어",
    "낙지",
    "해물",
    "참치",
    "연어",
    "돈까스",
    "카츠",
    "파스타",
    "크림",
    "치즈",
    "토마토",
    "짜장",
    "짬뽕",
    "면",
    "우동",
    "라면",
    "국수",
    "국밥",
    "찌개",
    "된장",
    "고추장",
    "간장",
    "버섯",
    "야채",
    "샐러드",
    "피자",
    "햄버거",
    "버거",
    "카레",
    "냉면",
    "비빔",
    "만두",
    "죽",
    "국물",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="국가표준식품성분표를 참고해 메뉴별 5가지 맛 벡터와 메뉴 임베딩을 생성합니다."
    )
    parser.add_argument(
        "--food-db-path",
        default=os.getenv("FOOD_DB_PATH", ""),
        help="식품성분표 xlsx 경로. 미지정 시 FOOD_DB_PATH 환경변수 사용",
    )
    parser.add_argument(
        "--sheet",
        default=os.getenv("FOOD_DB_SHEET", DEFAULT_FOOD_DB_SHEET),
        help="식품성분표 시트명",
    )
    parser.add_argument("--limit", type=int, default=0, help="테스트용 처리 개수. 0이면 전체 처리")
    parser.add_argument("--start-id", type=int, default=0, help="해당 menu_id 이상부터 처리")
    parser.add_argument("--only-missing", action="store_true", help="menu_flavors에 아직 없는 메뉴만 처리")
    parser.add_argument("--sleep", type=float, default=0.3, help="메뉴 1개 처리 후 대기 시간")
    return parser.parse_args()


def get_db_connection() -> pymysql.connections.Connection:
    return pymysql.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        db=os.getenv("DB_NAME", "delipick"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def ensure_menu_flavors_table(conn: pymysql.connections.Connection) -> None:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS menu_flavors (
                menu_id INT PRIMARY KEY,
                menu_name VARCHAR(100) NOT NULL,
                salty DECIMAL(3,1) DEFAULT 0.0,
                sweet DECIMAL(3,1) DEFAULT 0.0,
                sour DECIMAL(3,1) DEFAULT 0.0,
                umami DECIMAL(3,1) DEFAULT 0.0,
                spicy DECIMAL(3,1) DEFAULT 0.0,
                reason TEXT,
                semantic_embedding LONGTEXT NULL,
                FOREIGN KEY (menu_id) REFERENCES menus(id) ON DELETE CASCADE
            )
            """
        )

        cursor.execute("SHOW COLUMNS FROM menu_flavors")
        existing = {row["Field"] for row in cursor.fetchall()}
        additions = {
            "reason": "ALTER TABLE menu_flavors ADD COLUMN reason TEXT NULL AFTER spicy",
            "semantic_embedding": "ALTER TABLE menu_flavors ADD COLUMN semantic_embedding LONGTEXT NULL AFTER reason",
        }
        for column, sql in additions.items():
            if column not in existing:
                cursor.execute(sql)


def normalize_text(value: Any) -> str:
    if pd.isna(value):
        return ""
    text = str(value).lower()
    text = re.sub(r"\[.*?\]|\(.*?\)|\{.*?\}", " ", text)
    text = re.sub(r"[^가-힣a-z0-9]", "", text)
    return text.strip()


def load_food_nutrient_db(path: str, sheet: str) -> pd.DataFrame:
    food_db_path = Path(path)
    if not food_db_path.exists():
        raise FileNotFoundError(
            f"식품성분표 파일을 찾을 수 없습니다: {food_db_path}\n"
            f"다운로드 페이지: {FOOD_DB_URL}\n"
            "실행 예: python scripts/generate_menu_flavors_from_nutrient_db.py "
            "--food-db-path C:\\path\\식품성분표(10개정판).xlsx"
        )

    df = pd.read_excel(food_db_path, sheet_name=sheet, header=1)
    df = df[df["식품명"].notna()].copy()
    df = df[df["식품명"] != "식품명"].copy()

    existing_cols = [column for column in NUTRIENT_COLUMNS if column in df.columns]
    df = df[existing_cols].copy()

    for column in existing_cols:
        if column != "식품명":
            df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0)

    df["식품명_정규화"] = df["식품명"].astype(str).apply(normalize_text)
    return df


def extract_search_keywords(menu_name: str) -> list[str]:
    normalized = normalize_text(menu_name)
    keywords = [keyword for keyword in SEARCH_KEYWORDS if keyword in normalized]
    if not keywords and normalized:
        keywords.append(normalized)
    return list(dict.fromkeys(keywords))


def find_related_nutrients(menu_name: str, nutrient_df: pd.DataFrame, max_rows: int = 12) -> list[dict[str, Any]]:
    matched_rows: list[pd.DataFrame] = []
    for keyword in extract_search_keywords(menu_name):
        keyword_norm = normalize_text(keyword)
        if not keyword_norm:
            continue

        matched = nutrient_df[nutrient_df["식품명_정규화"].str.contains(keyword_norm, na=False)].copy()
        if not matched.empty:
            matched["매칭키워드"] = keyword
            matched_rows.append(matched)

    if not matched_rows:
        return []

    result_df = pd.concat(matched_rows, ignore_index=True)
    result_df = result_df.drop_duplicates(subset=["식품명"]).head(max_rows)

    records: list[dict[str, Any]] = []
    for _, row in result_df.iterrows():
        records.append(
            {
                "matched_keyword": row.get("매칭키워드", ""),
                "food_name": row.get("식품명", ""),
                "sugar_g": float(row.get("당류", 0)),
                "sodium_mg": float(row.get("나트륨", 0)),
                "potassium_mg": float(row.get("칼륨", 0)),
                "protein_g": float(row.get("단백질", 0)),
                "fat_g": float(row.get("지방", 0)),
                "vitamin_c_mg": float(row.get("비타민 C", 0)),
                "aspartic_acid_mg": float(row.get("아스파르트산", 0)),
                "glutamic_acid_mg": float(row.get("글루탐산", 0)),
            }
        )
    return records


def build_flavor_prompt(menu_name: str, related_nutrients: list[dict[str, Any]]) -> str:
    nutrient_json = json.dumps(related_nutrients, ensure_ascii=False, indent=2)
    return f"""
너는 음식 추천 시스템을 위한 메뉴 초기 맛 벡터 생성기다.

목표:
메뉴명과 국가표준식품성분표 참고 데이터를 기반으로 아래 5가지 맛 점수를 0.0~1.0 사이로 추정한다.

맛 점수:
- salty: 짠맛
- sweet: 단맛
- sour: 신맛
- umami: 감칠맛
- spicy: 매운맛

중요한 전제:
- 이 수치는 절대적인 맛 측정값이 아니다.
- 메뉴 간 상대 비교를 위한 초기 맛 벡터다.
- 이후 리뷰 분석으로 음식점별 맛 차이를 보정할 수 있다.
- 식품성분표에 없는 정보는 메뉴명과 일반적인 재료 특성을 기반으로 추정한다.
- 확신하기 어려우면 0.2~0.5 사이의 중립값을 사용한다.

성분과 맛의 연결 기준:
- 당류가 높거나 단맛 소스가 예상되면 sweet 증가
- 나트륨, 간장, 된장, 고추장, 소금 양념이 예상되면 salty 증가
- 글루탐산, 아스파르트산, 단백질, 육류, 해산물, 버섯, 장류, 국물류는 umami 증가
- 비타민 C, 식초, 김치, 레몬, 피클, 발효 식재료는 sour 증가
- 고추, 고춧가루, 마라, 불닭, 매운, 짬뽕, 떡볶이 등은 spicy 증가

주의:
- 최종 출력은 JSON만 한다.
- 각 맛 점수는 소수점 한 자리로 출력한다.
- reason에는 핵심 근거를 한국어로 짧게 작성한다.

메뉴명:
{menu_name}

식품성분표 참고 데이터:
{nutrient_json}

출력 형식:
{{
  "salty": 0.0,
  "sweet": 0.0,
  "sour": 0.0,
  "umami": 0.0,
  "spicy": 0.0,
  "reason": "..."
}}
""".strip()


def parse_json_response(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            raise
        return json.loads(match.group(0))


def generate_flavor_vector(
    client: OpenAI,
    model: str,
    menu_name: str,
    related_nutrients: list[dict[str, Any]],
    retry: int = 3,
) -> dict[str, Any]:
    prompt = build_flavor_prompt(menu_name, related_nutrients)

    for attempt in range(retry):
        try:
            response = client.responses.create(
                model=model,
                input=prompt,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "menu_flavor_schema",
                        "schema": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "salty": {"type": "number"},
                                "sweet": {"type": "number"},
                                "sour": {"type": "number"},
                                "umami": {"type": "number"},
                                "spicy": {"type": "number"},
                                "reason": {"type": "string"},
                            },
                            "required": [*TASTE_KEYS, "reason"],
                        },
                    }
                },
            )
            data = parse_json_response(response.output_text)
            for key in TASTE_KEYS:
                value = max(0.0, min(1.0, float(data.get(key, 0.0))))
                data[key] = round(value, 1)
            data["reason"] = str(data.get("reason", ""))[:1000]
            return data
        except Exception as error:
            print(f"맛 벡터 생성 실패: {menu_name}, attempt={attempt + 1}, error={error}")
            time.sleep(2)

    return {
        "salty": 0.3,
        "sweet": 0.3,
        "sour": 0.1,
        "umami": 0.4,
        "spicy": 0.1,
        "reason": "LLM 분석 실패로 기본 중립값 사용",
    }


def build_embedding_text(menu_name: str, flavor: dict[str, Any]) -> str:
    return f"""
메뉴명: {menu_name}
짠맛: {flavor["salty"]}
단맛: {flavor["sweet"]}
신맛: {flavor["sour"]}
감칠맛: {flavor["umami"]}
매운맛: {flavor["spicy"]}
근거: {flavor["reason"]}
""".strip()


def generate_semantic_embedding(
    client: OpenAI,
    model: str,
    menu_name: str,
    flavor: dict[str, Any],
    retry: int = 3,
) -> list[float]:
    embedding_text = build_embedding_text(menu_name, flavor)

    for attempt in range(retry):
        try:
            response = client.embeddings.create(model=model, input=embedding_text)
            return [float(value) for value in response.data[0].embedding]
        except Exception as error:
            print(f"임베딩 생성 실패: {menu_name}, attempt={attempt + 1}, error={error}")
            time.sleep(2)

    return []


def fetch_menus(
    conn: pymysql.connections.Connection,
    start_id: int,
    limit: int,
    only_missing: bool,
) -> list[dict[str, Any]]:
    where = ["m.id >= %s"]
    params: list[Any] = [start_id]

    join = ""
    if only_missing:
        join = "LEFT JOIN menu_flavors mf ON mf.menu_id = m.id"
        where.append("mf.menu_id IS NULL")

    limit_sql = ""
    if limit > 0:
        limit_sql = "LIMIT %s"
        params.append(limit)

    sql = f"""
        SELECT m.id, m.menu_name
        FROM menus m
        {join}
        WHERE {" AND ".join(where)}
        ORDER BY m.id
        {limit_sql}
    """
    with conn.cursor() as cursor:
        cursor.execute(sql, params)
        return list(cursor.fetchall())


def upsert_menu_flavor(
    conn: pymysql.connections.Connection,
    menu_id: int,
    menu_name: str,
    flavor: dict[str, Any],
    embedding: list[float],
) -> None:
    sql = """
        INSERT INTO menu_flavors (
            menu_id,
            menu_name,
            salty,
            sweet,
            sour,
            umami,
            spicy,
            reason,
            semantic_embedding
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            menu_name = VALUES(menu_name),
            salty = VALUES(salty),
            sweet = VALUES(sweet),
            sour = VALUES(sour),
            umami = VALUES(umami),
            spicy = VALUES(spicy),
            reason = VALUES(reason),
            semantic_embedding = VALUES(semantic_embedding)
    """
    with conn.cursor() as cursor:
        cursor.execute(
            sql,
            (
                menu_id,
                menu_name,
                flavor["salty"],
                flavor["sweet"],
                flavor["sour"],
                flavor["umami"],
                flavor["spicy"],
                flavor["reason"],
                json.dumps(embedding),
            ),
        )


def main() -> None:
    args = parse_args()
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY가 필요합니다. delipick_server/.env에 값을 설정하세요.")
    if not args.food_db_path:
        raise RuntimeError("FOOD_DB_PATH 또는 --food-db-path가 필요합니다.")

    client = OpenAI(api_key=api_key)
    nutrient_df = load_food_nutrient_db(args.food_db_path, args.sheet)

    with get_db_connection() as conn:
        ensure_menu_flavors_table(conn)
        menus = fetch_menus(conn, args.start_id, args.limit, args.only_missing)

        print(f"식품성분표 로드 완료: {len(nutrient_df)}개")
        print(f"처리 대상 메뉴: {len(menus)}개")

        for index, row in enumerate(menus, start=1):
            menu_id = int(row["id"])
            menu_name = str(row["menu_name"])
            related_nutrients = find_related_nutrients(menu_name, nutrient_df)

            print(
                f"[{index}/{len(menus)}] "
                f"menu_id={menu_id}, menu_name={menu_name}, 참고식품={len(related_nutrients)}개"
            )

            flavor = generate_flavor_vector(client, DEFAULT_FLAVOR_MODEL, menu_name, related_nutrients)
            embedding = generate_semantic_embedding(client, DEFAULT_EMBEDDING_MODEL, menu_name, flavor)
            upsert_menu_flavor(conn, menu_id, menu_name, flavor, embedding)

            print(
                f"  -> salty={flavor['salty']}, sweet={flavor['sweet']}, "
                f"sour={flavor['sour']}, umami={flavor['umami']}, spicy={flavor['spicy']}, "
                f"embedding_dim={len(embedding)}"
            )
            time.sleep(args.sleep)

    print("완료")


if __name__ == "__main__":
    main()
