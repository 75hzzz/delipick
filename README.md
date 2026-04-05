# 1. main에 있는 코드와 동기화할 때

## * Android Studio OR vscode 터미널에서
```bash
# 1. 깃허브(원격)의 최신 정보를 내 컴퓨터로 동기화 (필수!)
git fetch origin

# 2. 현재, 내 브랜치인지 확인
git branch
# 2-1. (이미 내 브랜치라면 패스) 내 브랜치가 아니라면, 내 브랜치로 이동
git checkout [내-브랜치-이름]

# 3. 내 브랜치의 상태를 원격 main 상태로 덮어쓰기
  # (기존 로컬에 있는 코드 삭제 후, main 코드 덮어쓰기)
git reset --hard origin/main
```

# 2. 데이터 베이스 구축

### 폴더 구조
- `data/`: 식당, 메뉴, 영업시간 정보가 담긴 JSON 파일들
- `scripts/`: DB 구축(`db_setup.py`) 및 데이터 수집(`crawl.py`) 스크립트
- `database/`: DB 스키마 덤프 파일 (`.sql`)

## * 실행 방법
1. **환경 변수 설정**: `.env.example` 파일을 복사 ->  `.env` 파일을 생성 -> 본인의 DB 정보를 입력
2. **패키지 설치**: 터미널 창에 해당 명령어 입력 
   ```bash
   pip install -r requirements.txt 
   # (pymysql, python-dotenv 필수)
   ```
3-1. **터미널 창에서 DB 구축하는 방법**:
   ```bash
   cd delipick_server/scripts
   python db_setup.py
   ```


아니면

3-2. **MySQL Workbench에서 DB 구축하는 방법**:
1. mysql에서 `delipick` 스키마 하나 생성
2. (**중요**) `use delipick;` 한 다음
3. mysql - File - Open SQL Script -> database/delivery.sql을 열고 한번에 실행

# 3. OpenWeather API

기상청 API보다 간편하고 API 응답도 json으로 바로 줌, 기상청 API는 받아도 다시 json으로 처리해야함

---

지금은 날씨, 현재온도, 날씨 아이콘만 있는데 더 추가 가능<br>
OpenWeather API 기준 강수량은 1시간마다 나머지는 10~30분 마다 업데이트 됨<br>

| 필드 | 설명 |
|------|------|
| temp | 현재 온도 |
| feels_like | 체감 온도 |
| pressure | 기압 |
| humidity | 습도 |
| rain["1h"] | 1시간 강수량 |
| snow["1h"] | 1시간 적설량 |

---

## 저장 형식

```json
{
  "city": "Busan",
  "description": "튼구름",
  "status": "흐림",
  "temp": 12.9,
  "icon": "04n",
  "timestamp": "2026-03-31T19:31:05.915058"
}
```

---

프론트에서 날씨 아이콘 쓰고 싶으면 추가하면 됨

```dart
String iconUrl =
    "https://openweathermap.org/img/wn/$icon@2x.png";
```
