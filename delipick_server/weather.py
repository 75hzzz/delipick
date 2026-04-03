import requests
import json
from datetime import datetime

# 하단동 좌표
API_KEY = "여기에 API KEY"
LAT = 35.104
LON = 128.974

weather_data = {}

# 날씨 상태 매핑
def get_weather_status(main):
    mapping = {
        "Clear": "맑음",
        "Clouds": "흐림",
        "Rain": "비",
        "Drizzle": "이슬비",
        "Thunderstorm": "천둥번개",
        "Snow": "눈",
        "Mist": "안개",
        "Fog": "안개",
        "Haze": "안개",
        "Smoke": "안개",
        "Dust": "안개",
        "Sand": "안개",
        "Ash": "안개",
    }
    return mapping.get(main, "기타")


# API 호출 + 데이터 처리
def fetch_weather():
    global weather_data

    url = (
        f"https://api.openweathermap.org/data/2.5/weather"
        f"?lat={LAT}&lon={LON}&appid={API_KEY}&units=metric&lang=kr"
    )

    try:
        res = requests.get(url)
        data = res.json()

        city = data["name"]
        main = data["weather"][0]["main"]
        desc = data["weather"][0]["description"]
        temp = data["main"]["temp"]
        icon = data["weather"][0]["icon"]

        weather_data = {
            "city": city,
            "description": desc,
            "status": get_weather_status(main),
            "temp": temp,
            "icon": icon,
            "timestamp": datetime.now().isoformat()
        }

        print("✅ 날씨 업데이트 완료")
        print(json.dumps(weather_data, indent=2, ensure_ascii=False))

        save_to_file(weather_data)

        return weather_data

    except Exception as e:
        print("❌ 에러 발생:", e)
        return None


# JSON 파일 저장
def save_to_file(data):
    with open("weather.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("💾 파일 저장 완료: weather.json")


# 직접 실행 테스트용
if __name__ == "__main__":
    print("🚀 Weather script started")

    fetch_weather()
