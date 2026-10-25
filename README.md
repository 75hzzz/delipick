# Delipick

기존 `delipick_app`과 `delipick_server` 구조를 유지한 통합본입니다. 검증한 추천 검색 개선 코드, Docker 실행 설정, 설명 문서를 합쳤습니다. 기존 원본 프로젝트와 실험 폴더는 수정하지 않았습니다.

팀원 실사용 테스트는 `test/qdrant-docker` 브랜치를 사용합니다. [팀원 테스트 순서](docs/TEAM_TEST_GUIDE.md)와 [업로드 전 점검 기록](docs/release_audit/REPORT.md)을 먼저 확인하세요. `main`에 바로 병합하는 버전이 아닙니다.

## 폴더 구성

```text
delipick_integrated/
  delipick_app/                  기존 Flutter 구조와 화면 유지, 오류 보완
  delipick_server/
    main.py                     검증한 개선 코드
    recommend_logic.py
    recommendation_rules.py
    recommendation_scoring.py
    update_delivery.py
    vector_search.py            조건 조회와 Qdrant 검색
    candidate_recall.py         개인화 후보 보완
    database/database.sql       기존 덤프의 로컬 복사본, Git 제외
    scripts/                    기존 스크립트와 Docker SQL 가져오기
    deployment/                 초기화와 Docker 실행 어댑터
    tests/                      통합 테스트
    data/demo/                  별도 가상 샘플
  docs/                         원래 문서와 변경 설명 및 검증 기록
  compose.yaml
  Dockerfile
  .env.example
  start.ps1
```

`backend`라는 새 폴더로 서버를 옮기지 않았습니다. `before`·`after`·실험 DB 내보내기·실험 가상환경도 이 프로젝트에 넣지 않았습니다. 원래 README는 `docs/ORIGINAL_README.md`에 보관했습니다.

## 기존 SQL 덤프로 실행

Docker Desktop을 켜고 이 README가 있는 폴더에서 실행합니다.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
```

이번 로컬 통합본에는 원래 프로젝트의 `delipick_server/database/database.sql`을 복사해 두었습니다. 팀원이 GitHub에서 내려받을 때는 이 파일이 제외되므로 기존 방식대로 덤프를 따로 전달받아 같은 위치에 넣어야 합니다. **스키마만 있는 SQL이 아니라 메뉴와 기존 임베딩 데이터도 필요합니다.**

이번 기준 덤프의 모델·차원·SHA-256·행 수는 `database/import_metadata.json`에 있습니다. 팀원에게는 같은 SQL 파일을 압축해 별도로 전달하세요. 다른 덤프를 임의로 넣고 메타데이터만 바꾸면 호환성을 검증한 것이 아닙니다. 새 덤프를 쓸 때는 데이터 생성자가 모델 정보와 행 수를 확인해 새 메타데이터를 함께 제공해야 합니다.

처음 실행하면 이 프로젝트 전용 MySQL에 SQL을 넣고, 태그 조회 테이블과 인덱스를 구성한 후 기존 임베딩을 Qdrant에 등록합니다. 임베딩을 새로 생성하거나 API 비용을 쓰는 초기화가 아닙니다. 다음 실행에서는 비어 있지 않은 DB에 SQL을 다시 덮어쓰지 않습니다.

SQL 가져오기는 완료 표식을 남깁니다. 중간 실패한 DB나 출처를 모르는 비어 있지 않은 DB는 정상 상태로 간주하지 않습니다. 완료된 DB는 원본 SQL 파일 없이도 다시 시작할 수 있습니다. 기존 통합본 볼륨은 기준 행 수를 확인하고, 예전 Qdrant 컬렉션은 모든 ID·벡터가 SQL과 같을 때만 소유권을 등록해 이어 씁니다. 모르는 컬렉션은 덮어쓰지 않습니다.

신뢰할 수 있는 단일 DB 덤프만 사용하세요. `CREATE DATABASE`, `DROP DATABASE`, `USE` 없이 내보낸 형태를 사용합니다. 제한된 DB 계정으로 가져오며, 여러 DB나 시스템 계정을 포함하는 전체 서버 덤프는 지원하지 않습니다. 기존 `scripts/db_setup.py`는 테이블을 삭제하는 초기화 스크립트이므로 Docker 실행에 자동 사용하지 않습니다.

- API 문서: http://localhost:18086/docs
- 실행 정보와 재생 예시: http://localhost:18086/deployment/info
- Qdrant: http://localhost:16339/dashboard
- MySQL Workbench: `127.0.0.1:13307`, DB `delipick`, 사용자 `delipick`, 비밀번호는 새 루트 `.env`의 `MYSQL_PASSWORD`

이는 기존 호스트 MySQL이나 `delipick-team`의 DB가 아니라 별도 named volume입니다. 루트 `.env`는 첫 실행 때 샘플에서 만들고 로컬 비밀번호를 생성합니다. `.env`와 비밀번호는 Git에 올리지 않습니다.

## 자유 입력과 재생 모드

기본 `QUERY_MODE=replay`는 API 키 없이 기록된 네 자연어 예시를 실행합니다. MySQL·Qdrant·점수 계산은 실제로 수행하지만 LLM 분석과 질의 임베딩 응답만 재사용합니다. 임의의 다른 문장은 HTTP 422로 알립니다.

원래처럼 자유로운 자연어 입력을 쓰려면 루트 `.env`에서 다음을 설정하고 `start.ps1`을 다시 실행합니다.

```dotenv
QUERY_MODE=live
OPENAI_API_KEY=본인_API_키
```

이 경우 API 사용료가 발생할 수 있습니다. 저장된 벡터와 질의 벡터는 같은 임베딩 모델이어야 합니다. 현재 기본값은 `text-embedding-3-small`, 1536차원입니다. 차원이 같다는 이유만으로 다른 모델의 벡터가 호환되지는 않습니다. 기존 벡터의 모델을 바꾸려면 새 벡터 생성·재등록이 필요합니다.

## 네이버 경로 시간 갱신

Docker 설정은 이 README 옆 루트 `.env`에서 읽습니다. 네이버 경로 API를 사용하려면 아래 항목을 채우고 `start.ps1`을 다시 실행하세요. 서버 폴더의 `.env`가 아니라 루트 `.env`입니다.

```dotenv
ENABLE_DELIVERY_WORKER=true
NAVER_CLIENT_ID=본인_네이버_클라이언트_ID
NAVER_CLIENT_SECRET=본인_네이버_클라이언트_시크릿
```

기존 워커는 API 서버 시작 시 한 번 실행한 뒤 60분마다 좌표가 있는 음식점의 경로 소요시간을 조회해 Docker MySQL의 `restaurants.delivery_time`과 `last_delivery_update`를 갱신합니다. 이 값에 별도의 조리·혼잡도 시뮬레이션을 더해 추천용 ETA를 계산하는 구조입니다. 네이버가 실제 주문의 배달 완료시간 전체를 예측하는 것은 아닙니다.

현재 출발점은 `update_delivery.py`의 고정 기준 좌표이며 앱 사용자의 GPS에 따라 바뀌지 않습니다. 키 누락·요청 오류 시 기존 배달시간과 갱신 시각을 보존합니다. 인증·권한·할당량 오류는 해당 배치의 나머지 요청을 중단합니다. 활성화하면 시작할 때와 매시간 여러 음식점에 대한 호출이 발생합니다. API 사용 권한과 호출 한도·요금도 확인하세요.

기본값은 `false`이며 가상 샘플용 `start.ps1 -Demo`에서도 강제로 끕니다. 첫 갱신은 백그라운드에서 즉시 시작하므로 경로 조회가 API 서버 준비를 막지 않습니다. 스케줄러는 API 프로세스 안에서 실행되므로 API가 꺼져 있으면 갱신하지 않습니다. 서버 재시작은 새 즉시 갱신을 유발하며 다중 API 프로세스로 확장할 때는 별도 단일 워커로 분리해야 중복 호출을 피할 수 있습니다.

```powershell
docker compose logs --tail 80 api
```

로그에서 `Delivery time refresh completed`와 `Delivery worker started (every 60 minutes)`를 확인할 수 있습니다. 이번 설정 복구 검증에서는 실제 네이버 API 호출이나 배달시간 값 변경을 실행하지 않았습니다.

## 가상 데이터로만 실행

실제 SQL을 받지 않은 팀원도 아래 명령으로 별도 샘플 환경을 실행할 수 있습니다.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start.ps1 -Demo
```

샘플은 실제 DB와 다른 `delipick-integrated-demo` 프로젝트와 볼륨을 사용합니다. 가상 음식점 28개·메뉴 224개이며 API는 http://localhost:18087/docs, Qdrant는 http://localhost:16340/dashboard, MySQL은 로컬 13308 포트입니다. 실제 데이터 환경에 가상 샘플을 덮어쓰지 않습니다.

## Flutter 앱 연결

기본 Android 에뮬레이터 주소는 통합본 포트인 `http://10.0.2.2:18086`입니다. 다른 환경은 기존 `API_BASE_URL` 옵션으로 지정합니다. Flutter SDK와 앱 개발 환경은 별도로 필요합니다. Docker는 Flutter 앱을 실행하지 않습니다.

```powershell
cd delipick_app
flutter pub get
# Android 에뮬레이터에서 기존 SQL 환경에 연결
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:18086
# 가상 샘플은 18087 포트
```

Windows 데스크톱 또는 브라우저 개발 환경은 `http://localhost:18086`을 사용합니다. 실물 휴대폰에서 PC로 연결하려면 LAN 바인딩·방화벽을 별도로 검토해야 합니다. 현재 Docker 포트는 localhost 전용입니다.

## 테스트와 종료

```powershell
docker compose exec -T -e QUERY_MODE=replay -e ENABLE_DELIVERY_WORKER=false -e OPENAI_API_KEY= api python -m pytest delipick_server/tests -q -p no:cacheprovider
# 가상 샘플 환경을 검사할 때
docker compose -p delipick-integrated-demo exec -T -e QUERY_MODE=replay -e ENABLE_DELIVERY_WORKER=false -e OPENAI_API_KEY= api python -m pytest delipick_server/tests -q -p no:cacheprovider
# 상태와 실패 원인
docker compose ps -a
docker compose logs --tail 60 import init api
# 실제 데이터 환경을 중지하되 데이터 보존
docker compose stop
```

`docker compose down -v`는 DB·벡터 볼륨을 삭제하므로 평소에는 사용하지 마세요. 기존 볼륨의 비밀번호는 `.env`만 변경한다고 자동으로 바뀌지 않습니다. SQL 가져오기가 중간 실패하면 일부 테이블이 남을 수 있으므로 임의로 재초기화하지 말고 로그와 데이터 상태를 확인하세요.

테스트 자체도 재생 모드와 워커 비활성화를 강제합니다. 추가 데이터 변경 검사는 별도 검증 환경에서만 실행합니다. 앱의 장바구니 주문 완료 화면은 모의 기능이며 실제 주문·결제·배달 플랫폼 접수가 일어나지 않습니다. 이번 팀원 평가는 추천 결과와 반응속도가 대상입니다.

## 변경 문서와 GitHub 공유 범위

- [통합 내용](docs/INTEGRATION.md)
- [공유 전 최종 점검 결과와 수정 사항](docs/release_audit/REPORT.md)
- [팀원 PC 실행 및 비교 테스트 안내](docs/TEAM_TEST_GUIDE.md)
- [기존 검증 코드 상세](docs/validated_experiments/CODE_CHANGES.md)
- [기존 Docker 성능 검증](docs/validated_experiments/DOCKER_AUDIT_RESULTS.md)
- `docs/integration_provenance.json`: 최초 통합 당시 체크섬, `docs/release_audit/source_manifest.json`: 이번 수정 후 체크섬
- `docs/integration/`: 이 통합 경로에서 새로 실시한 실행 테스트 결과

기존 검증 보고서는 당시 경로와 측정값을 유지한 보관본입니다. 보고서의 `backend/`는 이 통합본의 `delipick_server/`에 해당합니다. 새 폴더로 합쳤다는 이유만으로 이전 속도 수치를 새 환경의 재측정값이라고 주장하지 않습니다.

로컬 통합 복사본에는 기존 SQL과 원본 수집 JSON이 남아 있지만 이 브랜치의 최신 공유 파일에서는 제외합니다. `.env`, 비밀키, 가상환경, 빌드 캐시도 제외합니다. 이전 브랜치에서 이미 추적하던 데이터는 과거 Git 이력에 남아 있을 수 있으며, 이번 작업은 이력을 강제로 다시 쓰지 않습니다. 데이터 공개 권한·개인정보는 별도로 확인하세요. 새 브랜치는 기존 `merge-test` 이력을 이어받고 `main`은 변경하지 않습니다.

이 구성은 로컬 개발용입니다. 기본 인증 없는 API·Qdrant나 DB 포트를 인터넷에 공개하지 마세요. 재초기화는 관리 대상 normalized 태그와 소유한 컬렉션의 벡터를 SQL에 맞게 정리하지만, 서비스 중 데이터 변경을 실시간으로 동기화하는 운영 파이프라인은 아직 없습니다. iOS 실기기·실제 결제·운영 배포 인증은 이번 검증 범위가 아닙니다.
