"""Idempotently initialize only this deployment's isolated demo database/index."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import time

import pymysql
from qdrant_client import QdrantClient, models

from delipick_server import recommendation_scoring as scoring
from delipick_server.deployment.schema import STATEMENTS
from delipick_server.deployment.index_sync import reconcile

ROOT = Path(__file__).resolve().parents[1]


def main():
    packed = (ROOT/"data/demo/demo.json.gz").read_bytes()
    digest = hashlib.sha256(packed).hexdigest()
    manifest = json.loads((ROOT/"data/demo/manifest.json").read_text(encoding="utf-8"))
    if digest != manifest["sha256"]:
        raise RuntimeError("Bundled dataset checksum mismatch")
    data = json.loads(gzip.decompress(packed))
    assert data["fictional"] is True
    conn = pymysql.connect(host=os.environ["DB_HOST"],user=os.environ["DB_USER"],password=os.environ["DB_PASSWORD"],
                           database=os.environ["DB_NAME"],charset="utf8mb4",autocommit=False,
                           cursorclass=pymysql.cursors.DictCursor)
    try:
        with conn.cursor() as cur:
            for statement in STATEMENTS:
                cur.execute(statement)
            cur.execute("SELECT state_value FROM deployment_state WHERE state_key='dataset_sha256'")
            state = cur.fetchone()
            if state and state["state_value"] != digest:
                raise RuntimeError("Existing data belongs to a different seed; automatic replacement is forbidden")
            if not state:
                for table in ("categories", "restaurants", "menus", "menu_flavors", "reviews", "menu_tag_map"):
                    cur.execute(f"SELECT COUNT(*) n FROM {table}")
                    if cur.fetchone()["n"]:
                        raise RuntimeError("Nonempty unrecognized database; refusing to overwrite")
                cur.executemany("INSERT INTO categories VALUES (%s,%s)",[(r["category_id"],r["category_name"]) for r in data["categories"]])
                cur.executemany("INSERT INTO restaurants (id,name,category_id,address,google_rating,prep_time,delivery_time) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                                [(r["id"],r["name"],r["category_id"],r["address"],r["google_rating"],r["prep_time"],r["delivery_time"]) for r in data["restaurants"]])
                foods = {f["id"]:f for f in data["foods"]}
                flavors, tags = [], []
                for menu in data["menus"]:
                    food = foods[menu["food_id"]]
                    cur.execute("INSERT INTO menus (id,restaurant_id,menu_name,price) VALUES (%s,%s,%s,%s)",(menu["id"],menu["restaurant_id"],food["name"],menu["price"]))
                    flavors.append((menu["id"],food["name"],*food["taste"],"Synthetic demo values, not measured food properties.",
                                    json.dumps(food["semantic_embedding"]),*food["taste"],"Fictional review, not a real user experience.",
                                    json.dumps(food["review_embedding"]),json.dumps(food["tags"],ensure_ascii=False)))
                    row={"menu_name":food["name"],"menu_tags":food["tags"]}
                    tags.extend((menu["id"],"normalized",tag) for tag in scoring._menu_tags_for_row(row))
                cur.executemany("INSERT INTO menu_flavors VALUES ("+",".join(["%s"]*17)+")",flavors)
                cur.executemany("INSERT INTO menu_tag_map VALUES (%s,%s,%s)",tags)
                cur.executemany("INSERT INTO reviews (id,restaurant_id,content,review_score) VALUES (%s,%s,%s,%s)",
                                [(r["id"],r["restaurant_id"],r["content"],r["review_score"]) for r in data["reviews"]])
                cur.execute("INSERT INTO deployment_state VALUES ('dataset_sha256',%s)",(digest,))
                conn.commit()
            for table, expected in (("restaurants",manifest["restaurants"]),("menus",manifest["menus"]),("menu_flavors",manifest["menus"]),("reviews",manifest["reviews"])):
                cur.execute(f"SELECT COUNT(*) n FROM {table}")
                if cur.fetchone()["n"] != expected:
                    raise RuntimeError("Stored demo data is incomplete; refusing to pretend initialization succeeded")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    q = QdrantClient(url=os.environ["QDRANT_URL"],timeout=60)
    for attempt in range(60):
        try:
            q.get_collections()
            break
        except Exception:
            if attempt == 59: raise
            time.sleep(1)
    collection = os.environ["QDRANT_COLLECTION"]
    foods={f["id"]:f for f in data["foods"]}
    owner = {"dataset_id": digest, "mode": "demo", "version": 1}
    desired = {menu["id"]: {"menu": foods[menu["food_id"]]["semantic_embedding"],
                            "review": foods[menu["food_id"]]["review_embedding"]} for menu in data["menus"]}
    index_digest = reconcile(q, collection, desired, owner, data["dimensions"], allow_legacy=True, payload={"dataset_sha256": digest})
    conn = pymysql.connect(host=os.environ["DB_HOST"], user=os.environ["DB_USER"], password=os.environ["DB_PASSWORD"],
                           database=os.environ["DB_NAME"], charset="utf8mb4")
    try:
        with conn.cursor() as cur:
            for key, value in {"index_owner": json.dumps(owner), "index_ids_digest": index_digest,
                               "index_summary": json.dumps({"points": manifest["menus"], "menu_vectors": manifest["menus"], "review_vectors": manifest["menus"]})}.items():
                cur.execute("INSERT INTO deployment_state VALUES (%s,%s) ON DUPLICATE KEY UPDATE state_value=VALUES(state_value)", (key, value))
        conn.commit()
    finally:
        conn.close()
    print(json.dumps({"status":"initialized","fictional":True,"restaurants":manifest["restaurants"],"menus":manifest["menus"],"dataset_sha256":digest}))


if __name__ == "__main__":
    main()
