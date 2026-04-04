import os
import time
from datetime import datetime

import pymysql
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

load_dotenv()

# 동아대 승학캠퍼스 정문 좌표
USER_LAT = 35.113732
USER_LON = 128.965903

NAVER_URL = "https://maps.apigw.ntruss.com/map-direction/v1/driving"


def _db_candidates() -> list[str]:
    requested = os.getenv("DB_NAME", "").strip()
    defaults = [requested] if requested else []
    for name in ("delipick", "qqq"):
        if name not in defaults:
            defaults.append(name)
    return defaults


def _is_unknown_database(error: pymysql.MySQLError) -> bool:
    return bool(error.args and error.args[0] == 1049)


def get_db_connection() -> pymysql.connections.Connection:
    last_error: pymysql.MySQLError | None = None
    for db_name in _db_candidates():
        try:
            return pymysql.connect(
                host=os.getenv("DB_HOST", "127.0.0.1"),
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
    client_id = os.getenv("NAVER_CLIENT_ID", "").strip()
    client_secret = os.getenv("NAVER_CLIENT_SECRET", "").strip()
    return {
        "X-NCP-APIGW-API-KEY-ID": client_id,
        "X-NCP-APIGW-API-KEY": client_secret,
    }


def _has_naver_keys() -> bool:
    headers = _naver_headers()
    return bool(headers["X-NCP-APIGW-API-KEY-ID"] and headers["X-NCP-APIGW-API-KEY"])


def get_naver_duration(goal_lat: float, goal_lon: float) -> int:
    if not _has_naver_keys():
        return 20

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
        if response.status_code == 200:
            data = response.json()
            duration_ms = data["route"]["trafast"][0]["summary"]["duration"]
            return int(duration_ms / 1000 / 60)

        print(f"Naver API error ({response.status_code}): {response.text}")
        return 20
    except Exception as error:
        print(f"Naver API request failed: {error}")
        return 20


def update_delivery_times() -> None:
    now_str = datetime.now().strftime("%H:%M:%S")
    print(f"[{now_str}] Delivery time refresh started.")

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, latitude, longitude FROM restaurants")
            restaurants = cursor.fetchall()

            updated = 0
            for restaurant in restaurants:
                lat = restaurant.get("latitude")
                lon = restaurant.get("longitude")
                if lat is None or lon is None:
                    continue

                new_time = get_naver_duration(float(lat), float(lon))
                cursor.execute(
                    "UPDATE restaurants SET delivery_time = %s, last_delivery_update = NOW() WHERE id = %s",
                    (new_time, restaurant["id"]),
                )
                updated += 1

            conn.commit()
            print(f"Delivery time refresh completed: {updated} rows updated")
    except Exception as error:
        print(f"Delivery update failed: {error}")
    finally:
        conn.close()


scheduler = BackgroundScheduler()


def start_delivery_worker() -> None:
    if scheduler.running:
        return

    update_delivery_times()
    scheduler.add_job(update_delivery_times, "interval", minutes=60)
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
