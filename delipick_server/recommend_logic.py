import pymysql
import os
import random
import requests
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY')) # 환경변수 사용 권장
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY')
LAT, LON = 35.104, 128.974 

def get_db_connection():
    return pymysql.connect(
        host=os.getenv('DB_HOST'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'), # 실제 비번은 .env에!
        db=os.getenv('DB_NAME'),
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )

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

def get_llm_scores(candidates, user_spicy, weather_status, temp):
    if not candidates: return {}
    context = "".join([f"- {res['name']} (메뉴: {res['main_menu']})\n" for res in candidates])
    
    prompt = f"""
    당신은 맛집 추천 전문가입니다. 현재 날씨는 '{weather_status}({temp}도)'이며 고객은 매운맛 {user_spicy}단계를 원합니다.
    다음 식당들의 메뉴를 분석해 0~100점으로 점수를 매겨주세요.
    1. 날씨에 어울리는 메뉴에 가산점.
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

# ✅ 메인 API용 함수 (데이터 리턴)
def get_recommendations(my_prefs, my_spicy, min_p, max_p):
    weather_status, current_temp = fetch_realtime_weather()
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = """
                SELECT r.id, r.name, r.prep_time, r.delivery_time, r.category_id, 
                       MIN(m.price) as main_menu_price, MIN(m.menu_name) as main_menu 
                FROM restaurants r 
                LEFT JOIN menus m ON r.id = m.restaurant_id 
                GROUP BY r.id 
                HAVING main_menu_price BETWEEN %s AND %s
            """
            cursor.execute(sql, (min_p, max_p))
            base_data = cursor.fetchall()

            # [큐잉 로직]
            now_hour = datetime.now().hour
            lam_factor = random.uniform(0.7, 0.9) if 11 <= now_hour < 14 else random.uniform(0.4, 0.6)
            for r in base_data:
                mu = 1 / r['prep_time'] if r['prep_time'] > 0 else 0.1
                lam = mu * lam_factor
                r['queuing_wait'] = lam / (mu * (mu - lam)) if (mu - lam) > 0 else 5.0
                r['queue_score'] = -(r['queuing_wait'] * 2) - (r['delivery_time'] * 0.5)

            # [LLM 취향 분석]
            queue_sorted = sorted(base_data, key=lambda x: x['queue_score'], reverse=True)
            llm_results = get_llm_scores(queue_sorted[:15], my_spicy, weather_status, current_temp)
            
            for r in base_data:
                llm_boost = llm_results.get(r['name'], 50)
                pref_boost = 30 if r['category_id'] in my_prefs else 0
                r['final_score'] = round(float(llm_boost + pref_boost + r.get('queue_score', 0)), 2)

            final_sorted = sorted(base_data, key=lambda x: x['final_score'], reverse=True)
            return final_sorted[:10] # 상위 10개 반환
    finally:
        conn.close()