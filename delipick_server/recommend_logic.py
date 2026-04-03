import pymysql
import os
import json
import random
import requests
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI

# 1. 환경 설정 및 API 키 로드
load_dotenv()
client = OpenAI(api_key='APIkey')
WEATHER_API_KEY = os.getenv('APIkey') # 발급받은 날씨 키
LAT, LON = 35.104, 128.974 # 하단동 좌표

def get_db_connection():
    return pymysql.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        user=os.getenv('DB_USER', 'root'),
        password='DBPW',
        db=os.getenv('DB_NAME', 'delipick'),
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )

# --- [기능 A: 실시간 날씨 수집] ---
def fetch_realtime_weather():
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={LAT}&lon={LON}&appid={WEATHER_API_KEY}&units=metric&lang=kr"
    try:
        res = requests.get(url)
        data = res.json()
        main_weather = data["weather"][0]["main"]
        temp = data["main"]["temp"]
        mapping = {"Clear": "맑음", "Clouds": "흐림", "Rain": "비", "Snow": "눈", "Drizzle": "이슬비"}
        return mapping.get(main_weather, "맑음"), temp
    except:
        return "맑음", 20.0

# --- [기능 B: LLM 분석 (취향/날씨)] ---
def get_llm_scores(candidates, user_spicy, weather_status, temp):
    if not candidates: return {}
    context = "".join([f"- {res['name']} (메뉴: {res['main_menu']})\n" for res in candidates])
    
    prompt = f"""
    당신은 맛집 추천 전문가입니다. 현재 날씨는 '{weather_status}({temp}도)'이며 고객은 매운맛 {user_spicy}단계를 원합니다.
    다음 식당들의 메뉴를 분석해 0~100점으로 점수를 매겨주세요.
    1. 날씨에 어울리는 메뉴(비오면 국물/매콤, 맑으면 시원/깔끔)에 가산점.
    2. 매운맛 단계 적합도 반영.
    형식: '식당명: 점수'
    {context}
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        scores = {}
        for line in response.choices[0].message.content.split('\n'):
            if ':' in line:
                name, score = line.split(':')
                scores[name.strip()] = int(''.join(filter(str.isdigit, score)))
        return scores
    except:
        return {res['name']: 50 for res in candidates}

# --- [메인 실행 로직] ---
def main():
    # 설정값 (앱에서 넘어오는 값)
    MY_PREFS = [1, 4] 
    MY_SPICY = "2" 
    MIN_P, MAX_P = 8000, 9000

    # 날씨 데이터 로드
    weather_status, current_temp = fetch_realtime_weather()
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 기본 데이터 필터링
            sql = "SELECT r.id, r.name, r.prep_time, r.delivery_time, r.category_id, MIN(m.price) as main_menu_price, MIN(m.menu_name) as main_menu FROM restaurants r LEFT JOIN menus m ON r.id = m.restaurant_id GROUP BY r.id HAVING main_menu_price BETWEEN %s AND %s"
            cursor.execute(sql, (MIN_P, MAX_P))
            base_data = cursor.fetchall()

            # ---------------------------------------------------------
            # [1단계] 단순 거리순 (배달 시간 기준)
            # ---------------------------------------------------------
            print(f"\n[{datetime.now().strftime('%H:%M')}] === [1] 단순 거리순(배달 시간) 목록 ===")
            dist_sorted = sorted(base_data, key=lambda x: x['delivery_time'])
            for i, r in enumerate(dist_sorted[:5], 1):
                print(f"{i}위. {r['name']} (배달 {r['delivery_time']}분)")

            # ---------------------------------------------------------
            # [2단계] 혼잡도(Queueing) 반영 순
            # ---------------------------------------------------------
            now_hour = datetime.now().hour
            lam_factor = random.uniform(0.7, 0.9) if 11 <= now_hour < 14 else random.uniform(0.4, 0.6)
            for r in base_data:
                mu = 1 / r['prep_time'] if r['prep_time'] > 0 else 0.1
                lam = mu * lam_factor
                r['queuing_wait'] = lam / (mu * (mu - lam)) if (mu - lam) > 0 else 5.0
                r['queue_score'] = -(r['queuing_wait'] * 2) - (r['delivery_time'] * 0.5)

            print(f"\n=== [2] 혼잡도(Queueing) 반영 목록 (현재 시간대 가중치 적용) ===")
            queue_sorted = sorted(base_data, key=lambda x: x['queue_score'], reverse=True)
            for i, r in enumerate(queue_sorted[:5], 1):
                print(f"{i}위. {r['name']} (대기지수: {r['queuing_wait']:.2f} / 배달: {r['delivery_time']}분)")

            # ---------------------------------------------------------
            # [3단계] LLM 취향 분석 반영 (사용자 취향 중심)
            # ---------------------------------------------------------
            llm_results = get_llm_scores(queue_sorted[:15], MY_SPICY, weather_status, current_temp)
            for r in base_data:
                llm_boost = llm_results.get(r['name'], 50)
                pref_boost = 30 if r['category_id'] in MY_PREFS else 0
                r['final_score'] = llm_boost + pref_boost + r.get('queue_score', 0)

            print(f"\n=== [3] LLM 취향 분석 반영 최종 추천 목록 (매운맛 {MY_SPICY}단계) ===")
            final_sorted = sorted(base_data, key=lambda x: x['final_score'], reverse=True)
            for i, r in enumerate(final_sorted[:8], 1):
                print(f"{i}위. {r['name']} | {r['main_menu']} | {r['main_menu_price']:,}원")
                print(f"   [총점: {r['final_score']:.2f}] (취향반영됨 / 예상배달: {r['delivery_time']}분)")

            # ---------------------------------------------------------
            # [4단계] 날씨 특화 추천 섹션 (실시간 날씨 기반)
            # ---------------------------------------------------------
            print(f"\n=== [4] 실시간 날씨 특화 추천 (현재: {weather_status}, {current_temp}°C) ===")
            # 날씨 점수가 특히 높은(LLM 점수 80점 이상) 식당만 따로 추출
            weather_specials = [r for r in final_sorted if llm_results.get(r['name'], 0) >= 80]
            
            if not weather_specials: # 만약 고득점이 없으면 상위 3개 출력
                weather_specials = final_sorted[:3]

            for i, r in enumerate(weather_specials[:3], 1):
                tag = " 비 오는 날 딱!" if weather_status == "비" else " 맑은 날 추천 메뉴"
                print(f" {tag}: {r['name']} ({r['main_menu']})")
                print(f"   -> 오늘 같은 {weather_status} 날씨에 고객님이 선호하는 맵기로 추천드려요!")

    finally:
        conn.close()

if __name__ == "__main__":
    main()