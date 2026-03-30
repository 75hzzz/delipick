import json
import pymysql
import os
from dotenv import load_dotenv

# --- [0. .env 파일 로드] ---
load_dotenv()

# --- [1. DB 접속 설정] ---
# os.getenv를 통해 .env의 값을 가져옴
DB_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'db': os.getenv('DB_NAME'),
    'charset': 'utf8mb4'
}

def setup_database():
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()

    try:
        # [2. 테이블 생성 로직] - 기존 테이블이 있다면 삭제 후 새로 생성 (초기화)
        print("DB 테이블 생성 시작...")
        
        # 외래키 체크 해제 (삭제 순서 상관없게 함)
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
        
        # 테이블 생성 쿼리 (스키마 정의)
        sql_statements = [
            "DROP TABLE IF EXISTS `menus`;",
            "DROP TABLE IF EXISTS `operating_hours`;",
            "DROP TABLE IF EXISTS `restaurants`;",
            "DROP TABLE IF EXISTS `categories`;",
            
            # 카테고리 테이블
            """
            CREATE TABLE `categories` (
                `category_id` INT PRIMARY KEY,
                `category_name` VARCHAR(50) NOT NULL
            );
            """,
            
            # 식당 테이블
            """
            CREATE TABLE `restaurants` (
                `id` INT PRIMARY KEY AUTO_INCREMENT,
                `name` VARCHAR(100) NOT NULL,
                `category_id` INT,
                `address` VARCHAR(255),
                `latitude` DOUBLE,
                `longitude` DOUBLE,
                `dong_name` VARCHAR(50),
                `image_url` TEXT,
                `prep_time` INT DEFAULT 20,
                `delivery_time` INT DEFAULT 15,
                `last_delivery_update` DATETIME,
                FOREIGN KEY (`category_id`) REFERENCES `categories`(`category_id`)
            );
            """,
            
            # 운영시간 테이블
            """
            CREATE TABLE `operating_hours` (
                `id` INT PRIMARY KEY AUTO_INCREMENT,
                `restaurant_id` INT,
                `day_of_week` ENUM('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'),
                `open_time` TIME,
                `close_time` TIME,
                FOREIGN KEY (`restaurant_id`) REFERENCES `restaurants`(`id`) ON DELETE CASCADE
            );
            """,
            
            # 메뉴 테이블
            """
            CREATE TABLE `menus` (
                `id` INT PRIMARY KEY AUTO_INCREMENT,
                `restaurant_id` INT,
                `menu_name` VARCHAR(100) NOT NULL,
                `price` INT,
                `image_url` TEXT,
                FOREIGN KEY (`restaurant_id`) REFERENCES `restaurants`(`id`) ON DELETE CASCADE
            );
            """
        ]

        for sql in sql_statements:
            cursor.execute(sql)
        
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
        print("테이블 구조 생성 완료!")

        # [3. 초기 데이터 삽입 로직]
        # JSON 파일들 로드
        with open('../data/restaurants.json', 'r', encoding='utf-8') as f:
            basic_info = json.load(f)
        with open('../data/op_img.json', 'r', encoding='utf-8') as f:
            extra_info = json.load(f)
        with open('../data/menus.json', 'r', encoding='utf-8') as f:
            menu_info = json.load(f)

        # 카테고리 기본 데이터 삽입
        categories = [
            (1, "한식"), (2, "중식"), (3, "일식"), (4, "아시안"), 
            (5, "패스트푸드"), (6, "양식"), (7, "카페")
        ]
        cursor.executemany("INSERT INTO categories (category_id, category_name) VALUES (%s, %s)", categories)

        # 식당 및 운영시간 삽입
        print("식당 및 운영시간 데이터 삽입 중...")
        for i, basic in enumerate(basic_info, 1):
            # 1. 카테고리 ID 및 기본 조리 시간(prep_time) 설정
            # 양식은 느림(25), 한식은 보통(20), 일식/중식은 빠름(15), 패스트푸드는 아주 빠름(10), 카페는 광속(5)
            if i <= 17:    # 한식 (1~17)
                cat_id, p_time = 1, 20
            elif i <= 24:  # 중식 (18~24)
                cat_id, p_time = 2, 15
            elif i <= 32:  # 일식 (25~32)
                cat_id, p_time = 3, 15
            elif i <= 38:  # 아시안 (33~38)
                cat_id, p_time = 4, 20
            elif i <= 49:  # 패스트푸드 (39~49)
                cat_id, p_time = 5, 10
            elif i <= 56:  # 양식 (50~56)
                cat_id, p_time = 6, 25
            else:          # 카페 (57~58)
                cat_id, p_time = 7, 5

            extra = next((x for x in extra_info if x['name'] == basic['name']), None)
            img_url = extra['image_url'] if extra and extra.get('image_url') else ''
            
            # 2. Restaurants INSERT
            cursor.execute(
                """INSERT INTO restaurants 
                   (id, name, category_id, address, latitude, longitude, dong_name, image_url, prep_time) 
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (i, basic['name'], cat_id, basic['address'], basic['latitude'], basic['longitude'], basic['dong_name'], img_url, p_time)
            )

            # Operating Hours INSERT
            if extra and 'operating_time' in extra:
                for day, times in extra['operating_time'].items():
                    cursor.execute(
                        "INSERT INTO operating_hours (restaurant_id, day_of_week, open_time, close_time) VALUES (%s, %s, %s, %s)",
                        (i, day, times['open'], times['close'])
                    )

        # 메뉴 데이터 삽입
        print("메뉴 데이터 삽입 중...")
        for m_data in menu_info:
            res_id = next((idx for idx, b in enumerate(basic_info, 1) if b['name'] == m_data['restaurant']), None)
            if res_id:
                for menu in m_data['menus']:
                    price = int(menu['price'].replace('원', '').replace(',', '').strip() or 0)
                    cursor.execute(
                        "INSERT INTO menus (restaurant_id, menu_name, price, image_url) VALUES (%s, %s, %s, %s)",
                        (res_id, menu['menu'], price, menu['image'])
                    )

        conn.commit()
        print("모든 데이터 구축이 완료되었습니다!")

    except Exception as e:
        print(f"에러 발생: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    setup_database()