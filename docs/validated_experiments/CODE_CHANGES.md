# 딜리픽 추천 검색 구조 변경 보고서

작성일 2026년 10월 19일 · 대상 김민석 및 딜리픽 팀원

## 1 무엇이 달라졌나

기존에는 추천 대상 음식점들의 메뉴 임베딩과 리뷰 임베딩을 MySQL에서 넓게 읽어 Python에서 점수를 계산했다. 개선 후에는 자연어 조건을 먼저 분석하고 MySQL에서 조건에 맞는 메뉴를 좁힌다. 후보가 많을 때 Qdrant와 개인화 보완 채널로 계산 대상을 고른 후, 기존 Python 점수식을 적용한다.

따라서 정확한 설명은 **“추천 점수 계산을 전부 Qdrant로 교체했다”가 아니라 “비싼 벡터 데이터 읽기와 전체 후보 계산을 줄이는 검색 단계를 앞에 추가했다”**이다. Python은 여전히 최종 유사도와 개인화 점수를 계산한다. MySQL도 계속 원본 데이터를 보관한다.

메뉴 수가 적을 때는 Qdrant를 건너뛰고 조건을 통과한 메뉴를 모두 계산한다. 그러므로 모든 요청에서 Qdrant가 호출되는 것은 아니다.

현재 확인된 것은 고정된 입력과 데이터에서의 검색 속도 개선 및 기준 결과 재현이다. 실제 사용자의 만족도 향상, 전국 규모 성능 보장, 자연어 조건의 완벽한 이해가 입증된 것은 아니다.

## 2 비교 대상과 폴더

`performance_lab_20261018/before/delipick_server`는 이번 구조 개선 실험을 시작할 때 보관한 기준 코드다. 학기 초 코드나 기말 PPT 작성 당시 코드와 반드시 같은 것은 아니다. 기준 코드에도 이미 LLM 응답 캐시, 임베딩 배치 요청, 벡터 JSON 파싱 캐시 등이 있었다.

`performance_lab_20261018/after/delipick_server`가 최종 개선 코드이며, 팀원이 Docker로 실행하는 `delipick_team/backend`에 같은 핵심 모듈이 복사되어 있다. `delipick_team/baseline`에는 비교용 기준 모듈이 있다. 기존 프로젝트 원본을 직접 교체한 것이 아니라 실험용 복사본과 공유용 실행 환경을 만들었다.

중간 실험은 `after_semantic_only`, `after_multichannel_v2`에 별도로 남아 있다. 실패했던 중간 결과를 최종 버전 결과로 설명하지 않도록 구분한다.

| 핵심 파일 | 이번 실험의 변경 | 담당 역할 |
| --- | --- | --- |
| `main.py` | 수정 | 검색 순서, 후보 상세 조회, 재정렬, 요청별 상태, 계측 |
| `vector_search.py` | 신규 | MySQL 조건 조회, Qdrant 벡터 검색 |
| `candidate_recall.py` | 신규 | 가격·배달·맛·리뷰 등 개인화 후보 보완 |
| `recommendation_scoring.py` | 수정 | 순수 텍스트 계산 함수 네 곳에 LRU 캐시 추가 |
| `recommend_logic.py` | 변경 없음 | 기존 LLM 분석, 사용자 임베딩 생성, ETA 시뮬레이션 유지 |
| `recommendation_rules.py` | 변경 없음 | 기존 태그·키워드·추천 규칙 유지 |
| `update_delivery.py` | 변경 없음 | 기존 배달시간 갱신 작업 유지 |

위 구분은 두 폴더의 파일 내용 비교로 확인했다. 함수별 줄 번호와 전체 차이는 함께 제공되는 `code_change_inventory.json`, `recommendation_changes.diff`에서 확인할 수 있다. 줄 번호는 문서 작성 시점 기준이다.

## 3 기존 구조와 개선 구조

### 기존 구조

```text
요청
  → _fetch_base_candidates 음식점 조회
  → _rank_recommendations
      → LLM 조건 분석과 사용자 임베딩 준비
      → 음식점에 속한 넓은 메뉴 후보의 벡터 JSON 읽기
      → Python에서 메뉴별 유사도와 개인화 점수 계산
      → 음식점별 대표 메뉴 선택 및 최종 추천
```

태그 자체가 없었던 구조는 아니다. 기존에도 점수 계산과 정확 추천·유사 추천 구분, 제외 조건 판단에 태그를 사용했다. **차이는 태그를 처음 도입했는지가 아니라, 인식한 자연어 조건을 큰 벡터 데이터를 읽기 전 SQL 후보 조회에도 반영하는지**에 있다.

### 개선 구조

```text
요청
  → LLM 조건 분석과 사용자 임베딩 준비
  → MySQL에서 가격·카테고리·필수 태그·제외 조건으로 메타데이터 조회
  → 후보 200개 이하: 조건 통과 후보 전체 사용
  → 후보 200개 초과:
      Qdrant 메뉴 벡터 상위 후보 ∪ 리뷰 벡터 상위 후보
      ∪ 가격·배달·맛·리뷰·종합 점수 보완 후보
  → 선택한 메뉴의 큰 벡터 JSON만 MySQL에서 읽기
  → 기존 Python 개인화 점수식으로 1차 순위 계산
  → 상위 음식점의 누락 메뉴를 추가 확인하고 최종 순위 계산
```

`RETRIEVAL_ENGINE=sql`은 검증용 기준 경로다. 동일한 조건 필터를 통과한 모든 메뉴를 최종 점수식으로 계산한다. Qdrant 경로가 이 결과를 얼마나 재현하는지 확인한다. **이 기준은 개선 전 결과와 동일하다는 뜻이 아니다.** 개선 전에는 없던 선행 조건 필터와 가격 정규화 기준 수정이 있기 때문이다.

## 4 main.py에서 바꾼 부분

### 4.1 요청 진입점을 run_recommendation으로 통합

위치: `backend/main.py:899`의 GET 조회 경로, `:928`의 POST 추천 경로, `:938`의 `run_recommendation`.

기존에는 라우트에서 바로 `_fetch_base_candidates` 후 `_rank_recommendations`를 호출했다. 지금은 `run_recommendation(request, conn)`이 전체 과정을 조정한다.

```python
# 기존 흐름
rows = _fetch_base_candidates(conn, request)
return _rank_recommendations(request, rows, conn)

# 개선 흐름
return run_recommendation(request, conn)
```

이 함수 안에서 조건 분석, 가벼운 후보 조회, Qdrant 검색, 후보 보완, 기존 재정렬을 순서대로 수행한다. 자연어가 비어 있는 맛 슬라이더 전용 요청은 기존 경로를 유지한다.

### 4.2 자연어 분석을 후보 조회 앞으로 이동

위치: `backend/main.py:951` 부근.

`build_preference_tag_intent`가 `must_tags`, `prefer_tags`, `avoid_tags`, `avoid_terms`, 메뉴용·리뷰용 임베딩 문장을 만든다. 이를 기존 `build_taste_vector_from_text`, `build_text_embeddings`에 전달한다. 이 함수들의 LLM 프롬프트나 임베딩 모델을 이번 개선에서 새로 만든 것은 아니다.

```python
intent = build_preference_tag_intent(request.preference_text)
menu_text = intent.get("menu_embedding_text") or request.preference_text
review_text = intent.get("review_embedding_text") or menu_text
taste = build_taste_vector_from_text(menu_text)
vectors = build_text_embeddings([menu_text, review_text])
candidates = vector_search.filter_candidates(conn, request, intent)
```

사용자 입력은 반드시 원문 그대로만 임베딩하는 구조가 아니다. 기존 분석 결과의 메뉴용·리뷰용 문장이 있으면 그것을 사용하고, 없으면 원문 등으로 보완한다. 메뉴·리뷰의 저장 벡터는 검색할 때마다 새로 생성하지 않는다.

### 4.3 선택한 메뉴의 상세 벡터만 읽기

위치: `backend/main.py:349`의 `_fetch_menu_flavors`.

함수에 `menu_ids: list[int] | None = None`을 추가했다. 기존 음식점 ID·가격 조건에 메뉴 ID 조건을 추가할 수 있게 했다.

```python
if menu_ids is not None:
    if not menu_ids:
        return []
    sql += " AND m.id IN (" + ",".join(["%s"] * len(menu_ids)) + ")"
    params.extend(menu_ids)
```

`None`이면 기존처럼 음식점에 속한 메뉴를 넓게 조회하고, 빈 리스트면 조회 없이 빈 결과를 반환한다. 메뉴 ID가 지정되면 그 메뉴들의 임베딩 JSON만 읽는다. 큰 1536차원 벡터의 전송·JSON 파싱·Python 연산 부담을 줄이는 핵심이다.

### 4.4 요청 안에서 분석과 ETA를 재사용

위치: `backend/main.py:45`, `:429`, `:438`, `:476`, `:492`, `:1009`, `:1039` 부근.

`_retrieval_context`라는 `ContextVar`에 해당 요청의 분석 결과, 사용자 벡터, 선택 메뉴 ID, 가격 범위, 음식점별 ETA, 리뷰 점수, 이미 읽은 상세 메뉴를 보관한다. 음식점 보완 후 두 번째 재정렬을 하더라도 같은 값을 사용한다.

특히 ETA는 난수를 사용하는 시뮬레이션이므로 같은 요청의 두 번 계산에서 새로 뽑으면 후보 보완 효과와 ETA 변동이 섞인다. 음식점별로 한 번 계산한 값을 재사용한다. 요청 종료 시 `finally`에서 `reset(token)`으로 상태를 되돌린다. 전역 딕셔너리에 모든 사용자의 요청 상태를 섞어 저장하는 방식이 아니다.

### 4.5 가격 점수의 기준 범위를 고정

위치: `backend/candidate_recall.py:12`의 `price_bounds`, `backend/main.py:569`, `:979` 부근.

가격 점수는 후보 집합의 최소·최대 가격 영향을 받는다. 검색된 일부 메뉴에서만 최소·최대 가격을 다시 계산하면 **같은 메뉴라도 검색 방식에 따라 가격 점수가 달라져** 순위가 바뀔 수 있다.

개선 후에는 조건을 통과한 전체 메타데이터 후보에서 가격 범위를 구하고, 일부 후보만 재정렬하더라도 그 범위를 사용한다. 검증용 전체 계산과 Qdrant 계산이 같은 가격 기준을 사용한다. 기존 before 결과와 완전히 같은 점수를 보장하는 수정은 아니다.

### 4.6 부정 문장에 대한 단순 카테고리 추론 중복 적용 방지

위치: `backend/main.py:416` 부근.

기존의 원문 키워드 카테고리 추론은 “마라탕 말고”에도 “마라”를 찾아 아시안으로 제한할 수 있다. 새로운 검색 경로에서는 이미 분석된 조건으로 후보를 정했으므로 `_retrieval_context`가 있으면 이 원문 기반 카테고리 추론을 다시 적용하지 않는다. 사용자가 UI에서 직접 고른 카테고리 조건을 없애는 것은 아니다.

### 4.7 최종 일반 반환 경로에도 제외 조건 확인

위치: `backend/main.py:649` 부근.

정확 추천·유사 추천 섹션을 나누지 않는 일반 반환 분기에도 `_has_avoid_match(tag_intent, item)` 검사를 추가했다. 이 변경은 `recommendation_scoring.py`가 아니라 **main.py**에 있다.

인식한 제외 조건을 최종 반환에서도 확인하는 보완이다. LLM이 제외 조건 자체를 놓치거나 데이터 태그가 틀리면 이 검사만으로 실제 음식의 조건을 보장할 수는 없다.

### 4.8 검색 실패를 정상 추천처럼 숨기지 않기

위치: `backend/main.py:988` 부근.

사용자 메뉴 임베딩이 비어 있으면 HTTP 502, Qdrant 검색 예외는 HTTP 503으로 알린다. Qdrant 장애를 가짜 유사도나 의미 없는 정상 추천으로 조용히 대체하지 않는다. 다만 후보가 적어 Qdrant를 호출하지 않는 요청은 Qdrant 장애와 무관하게 처리될 수 있다.

### 4.9 단계별 시간과 후보 수 기록

위치: `backend/main.py:203`의 `performance_log`, 기존 `_record_timing` 호출 확장.

응답 헤더에 `X-Response-Time-Ms`를 넣고, 로그에는 LLM·임베딩·메타데이터 조회·벡터 검색·후보 보완·상세 조회·재정렬 시간과 후보 수를 남긴다. 이 숫자는 병목을 구분하기 위한 값이다. 일부 시간 항목은 다른 항목을 포함하므로 항목을 모두 합산하면 중복 계산이 될 수 있다.

## 5 vector_search.py에서 새로 만든 부분

### 5.1 어떤 조건을 SQL 필터로 쓰는가

위치: `backend/vector_search.py:8`, `:21`의 `conditions`.

| 분석 결과 | SQL 반영 기준 |
| --- | --- |
| `must_tags` | 국물·면·밥·죽·음료·따뜻함·차가움의 허용 목록에 있는 태그만 필수 적용 |
| `avoid_tags` | 혼밥·아이동반·속편함 등 경험성 태그를 제외한 태그를 제외 조건으로 적용 |
| `avoid_terms` | 메뉴명에서 해당 표현이 발견되면 제외 |
| `prefer_tags` | 이 모듈에서는 SQL 필수 조건으로 사용하지 않음 |

필수 태그는 `must_tags ∩ SAFE_REQUIRED`, 제외 태그는 `avoid_tags − EXPERIENCE`로 만든다. 아이동반이나 속편함처럼 메뉴명만으로 확정하기 어려운 속성을 무조건 SQL 필터로 적용하지 않도록 한 것이다.

“따뜻함”이 분석 결과에서 선호 태그에만 들어가면 현재 SQL은 그것을 필수 조건으로 강제하지 않는다. 따뜻함이 언제나 보장된다고 발표하면 실제 코드보다 강한 설명이다.

### 5.2 SQL에서 큰 벡터 대신 메타데이터만 읽기

위치: `backend/vector_search.py:28`의 `metadata_sql`, `:55`의 `filter_candidates`.

가격과 UI 카테고리, 필수·제외 태그로 조회한다. `menu_flavors`를 조인하더라도 첫 조회에서는 태그와 작은 맛 수치만 가져오고, 메뉴·리뷰 임베딩 JSON 필드는 가져오지 않는다.

```sql
-- 개념을 설명하기 위한 축약 예시
WHERE m.price BETWEEN %s AND %s
  AND EXISTS (
    SELECT 1 FROM menu_tag_map t
    WHERE t.menu_id = m.id AND t.tag_value = %s
  )
  AND NOT EXISTS (
    SELECT 1 FROM menu_tag_map t
    WHERE t.menu_id = m.id AND t.tag_value IN (...)
  )
```

제외 단어는 `LOCATE(%s, REPLACE(m.menu_name, ' ', ''))=0`으로 검사한다. `%`, `_`를 LIKE 와일드카드로 해석하지 않는 문자 포함 검사다. 메뉴명과 제외 단어의 일반 공백을 제거해 비교한다. 완전한 한국어 의미 분석이나 모든 종류의 공백 정규화는 아니다.

카페 카테고리를 제외한 메뉴는 4천 원 이상이라는 기존 사업 규칙도 적용한다. **영업시간 필터는 이 SQL에 구현되어 있지 않다.** PPT에 영업시간을 적었더라도 구현 완료 항목으로 설명하면 안 된다. 맛 수치도 초기 메타데이터 조회에 포함하지만, 현재 SQL에서 매운맛 수치의 임계값으로 직접 걸러내는 코드는 없다.

### 5.3 Qdrant에서 두 벡터 후보를 합치기

위치: `backend/vector_search.py:62`의 `search`.

```python
query_filter = models.Filter(
    must=[models.HasIdCondition(has_id=candidate_ids)]
)
for name, vector in (("menu", menu_vector), ("review", review_vector)):
    result = client().query_points(
        collection_name=collection(), using=name, query=vector,
        query_filter=query_filter, limit=k,
        with_payload=False, with_vectors=False,
        search_params=models.SearchParams(hnsw_ef=512),
    )
```

MySQL에서 조건을 통과한 메뉴 ID만 검색할 수 있도록 제한한다. 기본값은 메뉴 벡터 상위 100개와 리뷰 벡터 상위 100개의 합집합이다. 중복이 있으므로 실제 후보가 200개라는 뜻은 아니다. 서버는 Qdrant에서 벡터 원문을 받지 않고 후보 ID를 받는다.

이 코드는 dense 메뉴·리뷰 벡터 검색이다. **sparse lexical vector와 dense vector를 결합하는 하이브리드 검색을 구현한 것은 아니다.** 현재 프로젝트의 메뉴·리뷰 두 검색을 합치는 방식과 dense+sparse 하이브리드는 구분해야 한다.

## 6 candidate_recall.py에서 품질을 보완한 이유

### 6.1 의미가 비슷한 후보만 남기면 생기는 문제

기존 최종 추천은 의미 유사도만으로 정하지 않는다. 가격, ETA, 맛, 리뷰, 사용자 유형별 가중치도 반영한다. 의미 유사도 상위 후보만 먼저 잘라 버리면 저렴하거나 빠르기 때문에 최종 점수가 높았을 메뉴가 사라질 수 있다.

실제로 초기 semantic-only 버전은 336개 시나리오 중 기준 결과가 있는 327개에서 1위 메뉴 후보를 74번 놓쳤다. 음식점 구성 평균 일치율 약 85.5%, 메뉴 구성 평균 일치율 약 74.4%였다. 단순히 속도가 빨라졌다는 이유만으로 이 버전을 최종 성공으로 판단하지 않았다.

### 6.2 개인화 신호별 후보를 합집합으로 확보

위치: `backend/candidate_recall.py:36`의 `select`.

메타데이터의 작은 수치와 기존 점수 도우미를 이용해 후보 보완 채널을 만든다. 여기서는 큰 임베딩 JSON을 읽지 않는다.

| 보완 채널 | 기본 확보 개수 | 음식점별 제한 |
| --- | --- | --- |
| 가격 | 40 | 2개 메뉴 |
| 배달 | 40 | 2개 메뉴 |
| 맛 | 40 | 2개 메뉴 |
| 리뷰 | 40 | 2개 메뉴 |
| 가벼운 종합 점수 | 120 | 3개 메뉴 |
| 필수 태그 충족 후보 | 최대 40 | 이 채널에는 별도 음식점 제한 없음 |

종합 점수는 기존 가중치와 점수 함수를 활용하되 벡터 필드가 없는 행을 사용하므로 의미 점수는 빠진 근사 점수다. 코드의 `[1.0]`은 최종 사용자 임베딩을 대체하는 가짜 벡터가 아니라 **의미 항이 없는 저비용 후보 선별 함수 호출에만 쓰이는 값**이다. 최종 재정렬에는 실제 사용자·메뉴·리뷰 벡터가 들어간다.

후보는 모두 기존 조건을 통과한 집합 안에서만 추가한다. 제외 조건을 풀어서 억지로 개수를 채우는 방식이 아니다. 각 채널 결과를 합집합으로 합치므로 확보 개수를 단순 합산해 실제 상세 조회 개수라고 설명하면 안 된다.

이 과정도 후보 메타데이터를 순회하므로 연산이 완전히 상수 시간이 된 것은 아니다. 대규모에서 메타데이터 조회와 ID 목록 전송도 추가 최적화가 필요할 수 있다.

### 6.3 음식점별 대표 메뉴 누락 보완

위치: `backend/main.py:1014` 부근.

메뉴를 일부만 뽑으면 음식점은 맞게 찾았어도 그 음식점 안에서 최종 대표 메뉴를 잘못 고를 수 있다. 이를 보완하려고 1차 순위에서 기본 상위 10개 음식점을 고르고, 그 음식점에 속한 **조건 통과 메뉴 중 아직 읽지 않은 메뉴**를 추가로 읽어 다시 계산한다.

처음 읽은 상세 메뉴는 요청 상태에서 재사용하므로 같은 벡터를 전부 다시 조회하지 않는다. SQL 전체 계산 경로와 후보 200개 이하 경로에는 이 보완을 적용하지 않는다. 이 방법은 검사한 데이터에서 누락을 해결했지만, 어떤 새로운 데이터에서도 전체 계산과 반드시 같다는 수학적 보장은 아니다.

## 7 recommendation_scoring.py에서 바꾼 부분

이번 차이는 아래 함수 네 곳에 `@lru_cache`를 추가한 것이다. 최종 가중치나 유사도 공식을 새 모델로 교체한 것은 아니다.

| 함수 | 현재 시작 줄 | 캐시 크기 |
| --- | --- | --- |
| `_compact_text` | 34 | 8192 |
| `_tokenize_preference_text` | 46 | 256 |
| `_experience_intent_score` | 61 | 256 |
| `_preference_query_direct_intent` | 119 | 256 |

같은 문장·키워드를 메뉴마다 반복 정규화하거나 분석하던 비용을 줄인다. 메모리 캐시이므로 프로세스를 재시작하면 사라진다. Redis를 추가한 것은 아니다. 캐시가 있는 벡터 파싱 함수 `_parse_embedding_text`는 이번 개선 이전에도 있었다.

## 8 DB와 Qdrant 데이터 준비

### 8.1 MySQL에 보완한 구조

실험 스크립트 `performance_lab_20261018/experiment.py`의 `migrate`에서 다음 인덱스와 태그 테이블을 실험용 DB에 만든다. 공유 Docker 데이터 초기화는 `deployment/schema.py`, `deployment/seed.py`가 담당한다.

```sql
CREATE INDEX idx_lab_price_rest ON menus(price, restaurant_id, id);
CREATE INDEX idx_lab_rest_price ON menus(restaurant_id, price, id);
CREATE INDEX idx_lab_category_id ON restaurants(category_id, id);
CREATE INDEX idx_lab_review_score ON reviews(restaurant_id, review_score);

CREATE TABLE menu_tag_map (
  menu_id INT NOT NULL,
  tag_type VARCHAR(32) NOT NULL,
  tag_value VARCHAR(64) NOT NULL,
  PRIMARY KEY(menu_id, tag_type, tag_value),
  INDEX idx_tag_lookup(tag_value, menu_id)
);
```

태그는 기존 `_menu_tags_for_row`의 정규화와 메뉴명 추론을 사용해 만든다. 사람이 모두 검수한 독립적인 정답 태그가 아니다. 현재 검색은 `tag_value`를 사용하며 태그 종류별 차이를 추가로 구분하지 않는다. 인덱스가 있다고 모든 질의가 항상 그것을 최적으로 사용하는 것은 아니므로 EXPLAIN과 실제 시간으로 확인해야 한다.

### 8.2 Qdrant에 저장하는 값

기존 `menu_flavors.semantic_embedding`, `review_embedding`을 읽어 메뉴 ID를 point ID로 사용한다. `menu`, `review` 두 named vector로 저장하며 각 벡터는 1536차원, 코사인 거리다. 기존 벡터를 복사하므로 전체 메뉴 임베딩을 새로 생성하지 않는다.

인덱스 기본 설정은 HNSW `m=16`, `ef_construct=100`, `full_scan_threshold=20000`, 최적화 `indexing_threshold=64`, `default_segment_number=1`이다. 조회 시 `hnsw_ef=512`를 사용한다. `full_scan_threshold`는 포인트 개수가 아니라 KB 기준 설정이다. 후보 집합이 작으면 Qdrant가 exact scan을 선택할 수 있으므로 모든 성능 향상을 HNSW만의 효과라고 설명하면 안 된다.

MySQL은 원본 DB이고 Qdrant는 별도 프로그램으로 실행되는 파생 검색 저장소다. MySQL에 설치하는 스토리지 엔진이나 플러그인이 아니다. 현재는 원본 벡터를 MySQL에도 남겨 두기 때문에 저장 공간을 절약하는 작업도 아니다.

이번 실제 데이터 Docker 점검에서 메뉴 벡터는 1104개 메뉴에 등록되어 있었고, 유효한 리뷰 벡터가 등록된 메뉴는 311개였다. 리뷰 행 1937개가 있다는 것과 모든 메뉴에 리뷰 벡터가 있다는 것은 다르다. 리뷰 벡터가 없는 메뉴도 메뉴 벡터와 기존의 맛·가격·음식점 리뷰 점수 등으로 후보가 될 수 있다. 이 결과를 모든 메뉴가 리뷰 의미 정보까지 충분히 반영한다고 설명하면 안 된다. 리뷰 벡터 커버리지 보완은 별도의 품질 개선 과제다.

### 8.3 아직 운영 수준으로 완성되지 않은 동기화

태그 마이그레이션은 `INSERT IGNORE` 중심이라 메뉴 변경 시 오래된 태그를 자동 삭제하지 않는다. 벡터 업데이트 스크립트는 upsert를 지원하지만 삭제·변경 이벤트의 지속적인 자동 동기화는 없다. SQL에서 사라진 메뉴 ID는 후보에서 빠지지만, 메뉴 내용만 바뀌면 Qdrant 벡터가 최신화되기 전까지 오래된 검색 결과가 나올 수 있다.

실제 서비스에서는 메뉴 변경 이벤트, 재생성 작업 큐, 실패 재시도, 버전 관리, 삭제 처리를 추가해야 한다.

## 9 자연어 상황 조건은 어디까지 구현했나

| PPT 또는 계획의 항목 | 현재 상태 |
| --- | --- |
| LLM 분석을 후보 조회 전 수행 | 구현 |
| 인식한 필수 음식 형태·일부 온도 태그 SQL 적용 | 구현 |
| 인식한 제외 태그와 제외 메뉴명 SQL 적용 | 구현 |
| 리뷰 벡터도 후보 검색과 기존 점수에 활용 | 구현 |
| 1인분·1인 세트·개별 메뉴를 검증된 별도 속성으로 필터 | 미구현 |
| 영업시간 조건 SQL 필터 | 미구현 |
| 매운맛 수치 임계값을 SQL 필수 필터로 적용 | 미구현 |
| 양·포장 편의·혼자 주문 경험을 리뷰에서 별도 추출하고 검증 | 미구현 |
| 아이동반·속편함 등을 메뉴명만으로 확정 | 보장하지 않음 |
| 알레르기나 안전 조건을 실제 음식 기준으로 보장 | 보장하지 않음 |

현재 매운맛 수치는 개인화 점수에도 쓰인다. 하지만 “안 매운” 요청의 SQL 제외는 주로 인식한 태그·단어에 의존한다. 숫자 임계값 하드 필터가 구현되었다는 뜻은 아니다.

따라서 발표에서는 **“검색 구조와 일부 태그 선행 필터를 구현했고, 상황 정보를 검증된 메뉴 속성으로 보강하는 작업은 별도 과제로 남아 있다”**라고 구분하는 것이 정확하다.

## 10 Docker 공유 환경에서 추가한 부분

`compose.yaml`은 MySQL, Qdrant, 초기 데이터 작업, FastAPI를 분리해 실행한다. MySQL과 Qdrant 데이터는 Docker named volume에 저장한다. Windows 폴더를 Qdrant 데이터 저장소로 직접 사용하는 구조가 아니다.

| 파일 | 담당 역할 |
| --- | --- |
| `Dockerfile` | 동일한 Python 실행 환경과 고정 의존성 구성 |
| `compose.yaml` | MySQL·Qdrant·초기화·API 연결, 로컬 포트와 상태 검사 |
| `start.ps1` | Windows에서 환경 파일 준비 후 Docker 실행 |
| `deployment/schema.py` | 공유 데이터용 테이블·인덱스 생성 |
| `deployment/seed.py` | 데이터 체크섬 확인, 초기 적재, Qdrant 벡터 등록 |
| `deployment/replay.py` | 미리 기록한 실제 LLM·임베딩 응답 재사용 |
| `deployment/app.py` | 실행 모드 검증, 상태 조회, backend 연결 |
| `deployment/test_stack.py` | 실제 Docker MySQL·Qdrant 통합 테스트 |
| `deployment/benchmark.py` | before·after 검색 구간 시간 측정 |
| `tools/extended_validation.py` | 576개 비교 조합과 실제 HTTP 동시 요청 검사 |

공유 데이터는 가상 음식점 28개, 메뉴 224개, 가상 리뷰 28개다. 실제 수집 리뷰나 개인 API 키를 공개 저장소에 복사하지 않는다. 벡터 자체는 미리 생성한 실제 임베딩이다. 임의 숫자로 만든 가짜 벡터를 사용한 검색은 아니다.

기본 `QUERY_MODE=replay`는 기록된 자연어 예시 네 개를 재사용한다. 임의의 새로운 자연어 입력은 HTTP 422로 알린다. `live` 모드에서만 개인 OpenAI API 키로 새 요청을 분석한다. 따라서 replay 성능에는 외부 LLM·임베딩 API 대기시간이 포함되지 않는다. replay는 재현성과 설치 편의를 위한 모드이지 전체 자연어 기능을 검증한 결과가 아니다.

API는 `http://127.0.0.1:18080/docs`, Qdrant는 로컬 16335 포트다. MySQL은 팀 Compose 내부에서만 연결한다. DB 비밀번호와 API 키가 들어가는 `.env`는 Git에서 제외한다. Flutter 화면 소스는 이 공유용 저장소에 포함하지 않았다.

## 11 기존 실제 데이터 실험을 어떻게 해석하나

이 절은 앞서 실시한 Windows Python·로컬 MySQL·WSL Qdrant 실험이다. **아래 숫자는 이번 Docker 재측정 결과가 아니다.**

원본 복사본은 음식점 66개, 메뉴 1104개, 리뷰 1937개다. 10배·30배 데이터는 ID를 바꾸어 복제한 합성 확장 데이터다. 메뉴 수는 각각 11040개, 33120개다. 독립적으로 수집한 전국 데이터가 아니다.

검색 속도 측정은 국물·면·혼자 먹기 세 질의, 각 경로·규모마다 질의별 워밍업 1회와 측정 3회로 총 9개 표본을 사용했다. 기록된 LLM 분석·사용자 임베딩을 동일하게 재사용하고 ETA를 고정해 검색 변경의 영향을 분리했다.

| 규모 | 개선 전 평균 ms | 최종 개선 평균 ms | 조건 필터 후 전체 계산 ms | 개선 전 읽은 메뉴 행 | 개선 후 읽은 메뉴 행 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1배 | 711.93 | 25.16 | 23.58 | 953 | 34.33 |
| 10배 | 9118.86 | 348.36 | 243.86 | 9530 | 266.67 |
| 30배 | 28437.59 | 641.24 | 1031.78 | 28590 | 423.33 |

10배에서는 조건 필터 후 전체 계산이 Qdrant와 보완 단계를 거치는 경로보다 빨랐다. 1배의 세 질의는 후보가 적어 Qdrant를 우회하는 경로다. 따라서 이 결과는 **“Qdrant는 어떤 규모에서도 무조건 빠르다”가 아니라 “조건 필터와 선택적 상세 계산을 포함한 전체 구조가 개선 전보다 적은 작업으로 처리했다”**고 해석한다.

LLM API를 실제 호출한 소수 요청은 전체 응답이 약 3.3~4.7초였다. 검색 구간 25ms를 전체 사용자 응답 25ms라고 발표하면 안 된다.

### 기준 결과 재현 검사

36개 자연어 질의에 사용자 유형 3개·맛 프로필 3개를 조합한 324개와 UI 조건 12개, 총 336개 시나리오를 검사했다. 기준은 동일한 조건 필터를 적용한 후 모든 적합 후보를 계산하는 SQL 전체 경로다.

최종 버전은 이 검사에서 음식점·메뉴 구성 평균 일치율 100%, 음식점 순위 일치 336/336, 기준 결과가 있는 경우 1위 메뉴 일치 327/327이었다. 같은 메뉴 점수 차이는 0, 새롭게 빈 결과가 된 경우는 없었다. 인식한 태그·제외 단어 기준 위반은 반환 1584개에서 0개였다.

이것은 **추천 정확도 100%가 아니다.** 사람의 정답 라벨이나 실제 이용 만족도와 비교하지 않았고, LLM이 조건을 누락한 경우는 이 필터 검사만으로 잡지 못한다. 336개 중 기준부터 빈 결과인 경우도 9개 있었다.

저장된 매운맛 수치를 추가 점검한 183개 반환에서는 0.4 초과가 없었지만, 이것도 저장 수치 기준 사후 검사다. 실제 음식의 매운맛을 사람이 검증한 결과나 숫자 SQL 필터 구현 증거는 아니다.

30배의 넓은 요청 추가 검사에서는 중간 버전에 18개 중 2개 차이가 있었고 최대 점수 차이는 약 0.00418이었다. 음식점 메뉴 보완 후 같은 18개에서 순위별 점수 차이가 0이 되었다. 이 데이터를 보고 보완했으므로 최종 독립 테스트라고 부르지 않고 회귀 검사로 구분한다.

## 12 이번 Docker 재검증 결과

최신 수치는 [DOCKER_AUDIT_RESULTS.md](DOCKER_AUDIT_RESULTS.md)에 별도로 생성한다. 실제 데이터 대규모 실험, 공유 가상 데이터 실험, 외부 API를 포함하는 요청은 서로 구분한다.

Docker에서는 Qdrant를 실제 서버로 띄우고 MySQL과 연결해 테스트할 수 있다. 데이터 크기별 검색 시간, 최종 결과 차이, 후보 수, 오류 응답, 실제 HTTP 동시 요청을 검사할 수 있다. 다만 유한한 테스트를 통과했다고 모든 운영 성능이나 추천 정확도가 보장되지는 않는다.

## 13 팀원이 다시 실행하는 방법

팀 공유 폴더에서 PowerShell로 실행한다. Docker Desktop이 켜져 있어야 한다.

```powershell
.\start.ps1
docker compose ps
docker compose exec -T api python -m pytest deployment/test_stack.py -q -p no:cacheprovider
docker compose exec -T api python -m deployment.benchmark --repeats 3
```

추가 576개 비교와 동시 요청 검사는 호스트 Python 3이 있다면 다음 명령으로 실행한다. 호스트에는 표준 라이브러리만 사용하며 실제 DB·Qdrant 비교는 컨테이너 안에서 실행한다. API 포트가 18080인 기본 구성을 기준으로 한다.

```powershell
python tools/extended_validation.py
```

결과는 `docs/docker_extended_quality.json`, `docs/docker_http_load.json`에 저장된다. 반환 개수 1·5·10·20, 사용자 유형 3개, 맛 프로필 3개, 가격·카테고리 조건 4개를 예시 질의 4개에 조합한다. Qdrant 경로를 확인하려고 이 검사는 작은 후보 집합 우회 기준을 일시적으로 0으로 설정한다. 운영 기본값을 변경하는 것은 아니다.

기존 실험 전체 차이와 줄 번호 목록은 별도 문서 생성 스크립트가 실제 파일에서 만든다. 코드 수정 후에는 다시 생성해야 한다. 다른 팀원 PC, Mac, 운영 클라우드의 실행은 이 PC에서의 검사와 별도로 확인해야 한다.

## 14 지금 말할 수 있는 결론

“MySQL에서 명확한 조건으로 후보를 줄이고, 후보가 많으면 Qdrant와 개인화 신호로 계산 대상을 선별하도록 구현했다. 기존 개인화 점수식을 유지하면서 벡터 읽기·계산량을 줄였고, 고정된 테스트에서는 전체 계산 기준의 추천 결과를 재현했다.”

이 정도가 구현과 측정에 맞는 설명이다. “모든 자연어 조건을 보장한다”, “전국 규모에서도 항상 일정한 응답속도다”, “추천 정확도 100%다”, “DB만 바꿔서 무조건 빨라졌다”는 설명은 현재 증거보다 강하다.

다음 과제는 독립적인 사람 평가 데이터, 더 다양한 실제 메뉴·리뷰와 질의, 지속 부하 시험, 데이터 변경 자동 동기화, 검증된 1인분·온도·매운맛 속성, 운영 모니터링이다. 새로운 태그나 더 나은 리뷰 표현으로 추천 자체의 적합도를 높이는 작업은 이번 검색 최적화와 별도로 평가하면 된다.
