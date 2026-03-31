# OpenWeather API
기상청 API보다 간편하고 API 응답도 json으로 바로 줌, 기상청 API는 받아도 다시 json으로 처리해야함

지금은 날씨, 현재온도, 날씨 아이콘만 있는데 더 추가 가능
OpenWeather API 기준 강수량은 1시간마다 나머지는 10~30분 마다 업데이트 됨 

temp         현재 온도
feels_like   체감 온도
temp_min     최저
temp_max     최고
pressure     기압
humidity     습도

rain["1h"] → 1시간 강수량
snow["1h"] → 1시간 적설량

저장되는 형식
{
  "city": "Busan",
  "description": "튼구름",
  "status": "흐림",
  "temp": 12.9,
  "icon": "04n",
  "timestamp": "2026-03-31T19:31:05.915058"
}

프론트에서 아이콘 쓰고 싶으면 main.dart에 추가
String iconUrl = "https://openweathermap.org/img/wn/$icon@2x.png";
