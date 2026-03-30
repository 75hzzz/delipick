# delipick
개인 취향 및 배달시간을 고려한 배달 음식점 추천 시스템

### 폴더 구조
- `data/`: 식당, 메뉴, 영업시간 정보가 담긴 JSON 파일들
- `scripts/`: DB 구축(`db_setup.py`) 및 데이터 수집(`crawl.py`) 스크립트
- `database/`: DB 스키마 덤프 파일 (`.sql`)

### 실행 방법
1. **환경 변수 설정**: `.env.example` 파일을 복사하여 `.env` 파일을 생성하고 본인의 DB 정보를 입력합니다.
2. **패키지 설치**: `pip install -r requirements.txt` (pymysql, python-dotenv 필수)
3. **DB 구축**: 
   ```bash
   cd delipick_server/scripts
   python db_setup.py

아니면

1. mysql에서 스키마 하나 생성하고 use 한다음(**중요**)
2. mysql - File - Open SQL Script에서 database/delivery.sql을 열고 한번에실행




