# Docker 실행 및 테스트

## 처음 실행

1. Docker Desktop 설치 후 실행
2. 별도로 받은 `database.sql`을 `delipick_server/database/database.sql`에 추가. `import_metadata.json`은 Git에 포함된 파일 그대로 사용
3. 프로젝트 루트에서 아래 명령 실행

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
```

4. http://localhost:18086/docs 와 http://localhost:18086/deployment/info 접속 확인
5. 자유로운 자연어 입력 테스트 시 루트 `.env`에서 아래 항목 설정 후 시작 스크립트 재실행

```dotenv
QUERY_MODE=live
OPENAI_API_KEY=본인_키
```

6. Android 에뮬레이터 실행 후 `delipick_app` 폴더에서 아래 명령 실행

```powershell
flutter pub get
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:18086
```

## 가상 데이터로 실행

SQL 파일이 없다면 아래 명령으로 가상 메뉴 224개 샘플 실행

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start.ps1 -Demo
```

- 샘플 API 포트: `18087` (앱 연결 주소도 `http://10.0.2.2:18087`로 변경)
- `replay`: 기록된 문장 네 개만 지원, 자유 입력 테스트용 아님
- `live`: 자연어 분석과 사용자 임베딩 API 호출. 메뉴 임베딩 전체를 매번 재생성하는 방식은 아님

## 비교 조건

- 같은 SQL 파일·사용자 유형·자연어·맛 슬라이더·가격·카테고리로 비교
- 비교 중 네이버 자동 갱신은 `ENABLE_DELIVERY_WORKER=false`로 설정. 기존 ETA 시뮬레이션의 난수로 편의형 순위가 달라질 수 있음
- 첫 요청과 같은 문장의 반복 요청은 구분해서 측정. 캐시 적용 여부에 따라 대기시간 차이 발생 가능
- PC 사양·네트워크·외부 LLM 응답시간이 다르므로 팀원별 측정값을 단순 합산하지 않음
- 기존 실험의 before 스냅샷과 `merge-test`는 버전 차이가 있을 수 있음. 팀원 비교는 앱 사용성 평가이며 Qdrant 단독 효과를 분리한 실험은 아님

장바구니의 주문 완료는 모의 화면이며 실제 주문·결제는 발생하지 않음
