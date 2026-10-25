import os
import time
import logging
import math
from datetime import datetime

import pymysql
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


class NaverAccessError(RuntimeError):
    """Stop a batch after authentication, permission, or quota failure."""

# 기준 좌표
USER_LAT = 35.113732
USER_LON = 128.965903

NAVER_URL = "https://maps.apigw.ntruss.com/map-direction/v1/driving"


def _db_candidates() -> list[str]:
    # DB 후보 목록
    requested = os.getenv("DB_NAME", "").strip()
    if requested:
        return [requested]
    defaults = [requested] if requested else []
    for name in ("delipick", "qqq"):
        if name not in defaults:
            defaults.append(name)
    return defaults


def _is_unknown_database(error: pymysql.MySQLError) -> bool:
    return bool(error.args and error.args[0] == 1049)


def get_db_connection() -> pymysql.connections.Connection:
    # DB 연결 시도
    last_error: pymysql.MySQLError | None = None
    for db_name in _db_candidates():
        try:
            return pymysql.connect(
                host=os.getenv("DB_HOST", "127.0.0.1"),
                port=int(os.getenv("DB_PORT", "3306")),
                user=os.getenv("DB_USER", "root"),
                password=os.getenv("DB_PASSWORD", ""),
                db=db_name,
                charset="utf8mb4",
                cursorclass=pymysql.cursors.DictCursor,
                connect_timeout=5,
            )
        except pymysql.MySQLError as error:
            last_error = error
            if _is_unknown_database(error):
                continue
            raise

    if last_error is not None:
        raise last_error
    raise RuntimeError("Unable to connect database with known candidates.")


def _naver_headers() -> dict[str, str]:
    # 네이버 API 인증 헤더
    client_id = os.getenv("NAVER_CLIENT_ID", "").strip()
    client_secret = os.getenv("NAVER_CLIENT_SECRET", "").strip()
    return {
        "X-NCP-APIGW-API-KEY-ID": client_id,
        "X-NCP-APIGW-API-KEY": client_secret,
    }


def _has_naver_keys() -> bool:
    # 인증키 유무 확인
    headers = _naver_headers()
    return bool(headers["X-NCP-APIGW-API-KEY-ID"] and headers["X-NCP-APIGW-API-KEY"])


def get_naver_duration(goal_lat: float, goal_lon: float) -> int | None:
    # 네이버 경로 기반 소요시간 조회
    if not _has_naver_keys():
        return None

    params = {
        "start": f"{USER_LON},{USER_LAT}",
        "goal": f"{goal_lon},{goal_lat}",
        "option": "trafast",
    }

    try:
        response = requests.get(
            NAVER_URL,
            params=params,
            headers=_naver_headers(),
            timeout=8,
        )
        if response.status_code in {401, 403, 429}:
            raise NaverAccessError(f"Naver access or quota failure ({response.status_code})")
        if response.status_code == 200:
            data = response.json()
            duration_ms = float(data["route"]["trafast"][0]["summary"]["duration"])
            if not math.isfinite(duration_ms) or duration_ms <= 0:
                return None
            return max(1, int(duration_ms / 1000 / 60))

        logger.warning("Naver route request failed with HTTP %s; cached time retained", response.status_code)
        return None
    except NaverAccessError:
        raise
    except Exception as error:
        logger.warning("Naver route request failed (%s); cached time retained", type(error).__name__)
        return None


def update_delivery_times() -> None:
    if not _has_naver_keys():
        logger.warning("Delivery refresh skipped: both Naver credentials are required")
        return
    # 식당별 배달시간 갱신 배치
    now_str = datetime.now().strftime("%H:%M:%S")
    print(f"[{now_str}] Delivery time refresh started.")

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, latitude, longitude FROM restaurants")
            restaurants = cursor.fetchall()

            updated = 0
            for restaurant in restaurants:
                # 좌표 유효성 확인
                lat = restaurant.get("latitude")
                lon = restaurant.get("longitude")
                if lat is None or lon is None:
                    continue

                try:
                    lat, lon = float(lat), float(lon)
                    if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
                        continue
                    new_time = get_naver_duration(lat, lon)
                except (ValueError, TypeError):
                    continue
                except NaverAccessError as error:
                    logger.warning("%s; remaining restaurants keep cached delivery times", error)
                    break
                if new_time is None:
                    continue
                cursor.execute(
                    "UPDATE restaurants SET delivery_time = %s, last_delivery_update = NOW() WHERE id = %s",
                    (new_time, restaurant["id"]),
                )
                updated += 1

            conn.commit()
            print(f"Delivery time refresh completed: {updated} rows updated")
    except Exception as error:
        if conn is not None:
            conn.rollback()
        logger.warning("Delivery refresh failed (%s); uncommitted updates rolled back", type(error).__name__)
    finally:
        if conn is not None:
            conn.close()


scheduler = BackgroundScheduler()


def start_delivery_worker() -> None:
    # 워커 시작 + 주기 스케줄 등록
    if scheduler.running:
        return
    if not _has_naver_keys():
        logger.warning("Delivery worker not started: both Naver credentials are required")
        return

    # The first run is immediate but must not block API startup on remote calls.
    scheduler.add_job(update_delivery_times, "interval", minutes=60,
                      id="delivery_refresh", replace_existing=True, max_instances=1,
                      coalesce=True, next_run_time=datetime.now())
    scheduler.start()
    print("Delivery worker started (every 60 minutes).")


if __name__ == "__main__":
    start_delivery_worker()
    try:
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        if scheduler.running:
            scheduler.shutdown()
        print("Delivery worker stopped")
