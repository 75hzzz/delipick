from fastapi import FastAPI, Query
from typing import List, Optional
import uvicorn



# 민석 님이 만든 파일들 임포트
from update_delivery import start_delivery_worker
from recommend_logic import get_recommendations

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # 실제 배포 시에는 특정 도메인만 허용
    allow_methods=["*"],
    allow_headers=["*"],
)

app = FastAPI(title="DeliPick API Server")

# 서버 시작 시 스케줄러(배달시간 갱신) 가동
@app.on_event("startup")
async def startup_event():
    print("🔔 서버 시작: 배달 시간 갱신 워커를 백그라운드에서 실행합니다.")
    start_delivery_worker()

@app.get("/")
def home():
    return {"status": "online", "message": "동아 딜리버리 서버가 작동 중입니다."}

# ✅ Flutter 앱에서 호출할 API 엔드포인트
@app.get("/api/recommend")
def recommend_api(
    spicy: str = Query("2"),
    min_price: int = Query(0),
    max_price: int = Query(15000),
    prefs: List[int] = Query([1, 4]) # 기본값 예시
):
    """
    사용자의 설정값을 받아 최종 추천 리스트를 반환합니다.
    """
    try:
        results = get_recommendations(prefs, spicy, min_price, max_price)
        return {
            "success": True,
            "count": len(results),
            "data": results
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    # 포트 8000번에서 서버 실행
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)