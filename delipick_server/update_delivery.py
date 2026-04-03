import os
import time
import requests
import pymysql
from datetime import datetime
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler

# 1. 환경 변수 로드 (.env 파일에 NAVER_CLIENT_ID, NAVER_CLIENT_SECRET, DB 정보 필수)
load_dotenv()

# 동아대 승학캠퍼스 정문 (위도, 경도)
USER_LAT = 35.113732
USER_LON = 128.965903

# 네이버 API 헤더 및 엔드포인트
NAVER_HEADERS = {
    'X-NCP-APIGW-API-KEY-ID': os.getenv('NAVER_CLIENT_ID'),
    'X-NCP-APIGW-API-KEY': os.getenv('NAVER_CLIENT_SECRET')
}
NAVER_URL = 'https://maps.apigw.ntruss.com/map-direction/v1/driving'

def get_db_connection():
    return pymysql.connect(
        host=os.getenv('DB_HOST'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        db=os.getenv('DB_NAME'),
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )

# 파라미터
def get_naver_duration(goal_lat, goal_lon):
    params = {
        'start': f'{USER_LON},{USER_LAT}', 
        'goal': f'{goal_lon},{goal_lat}',
        'option': 'trafast'
    }
    
    try:
        response = requests.get(NAVER_URL, params=params, headers=NAVER_HEADERS)
        if response.status_code == 200:
            data = response.json()
            duration_ms = data['route']['trafast'][0]['summary']['duration']
            # ms -> 분 변환
            return int(duration_ms / 1000 / 60)
        else:
            print(f"네이버 API 오류 ({response.status_code}): {response.text}")
            return 20
    except Exception as e:
        print(f"API 호출 중 예외 발생: {e}")
        return 20

def update_delivery_times():
    now_str = datetime.now().strftime('%H:%M:%S')
    print(f"⏰ [{now_str}] 동아대 정문 기준 실시간 배달 시간 최신화 시작...")
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 1. 좌표 데이터 조회
            cursor.execute("SELECT id, name, latitude, longitude FROM restaurants")
            restaurants = cursor.fetchall()

            for r in restaurants:
                if r['latitude'] and r['longitude']:
                    new_time = get_naver_duration(r['latitude'], r['longitude'])
                    
                    # 2. delivery_time 컬럼 업데이트
                    cursor.execute(
                        "UPDATE restaurants SET delivery_time = %s, last_delivery_update = NOW() WHERE id = %s", 
                        (new_time, r['id'])
                    )
            
            conn.commit()
            print(f"총 {len(restaurants)}개 식당 업데이트 완료!")
    except Exception as e:
        print(f"DB 작업 중 오류 발생: {e}")
    finally:
        conn.close()

# --- [스케줄러 실행부] ---
scheduler = BackgroundScheduler()

def start_delivery_worker():
    # 실행 시점 즉시 1회 갱신 (서버 켤 때)
    update_delivery_times()
    
    # 이후 1시간(60분) 간격으로 자동 실행
    scheduler.add_job(update_delivery_times, 'interval', minutes=60)
    scheduler.start()
    print("배달 시간 갱신 워커 가동 중... (동아대 승학캠퍼스 정문 기준)")

if __name__ == "__main__":
    # 단독 테스트용 실행 로직
    start_delivery_worker()
    try:
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        print("스케줄러가 종료되었습니다.")