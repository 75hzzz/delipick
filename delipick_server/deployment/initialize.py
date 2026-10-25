"""Build derived tags/indexes from the existing SQL dump; never call an LLM."""
import json
import math
import os
from pathlib import Path
import time
import uuid

from qdrant_client import QdrantClient, models
import pymysql

from delipick_server import main as backend
from . import import_state
from .index_sync import reconcile


def vector(raw, dimension):
    try:
        values = json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(values, list) and len(values) == dimension:
            values = [float(value) for value in values]
            if all(math.isfinite(value) for value in values) and any(values):
                return values
    except (ValueError, TypeError, OverflowError):
        pass
    return None


def client():
    q = QdrantClient(url=os.environ["QDRANT_URL"], timeout=120)
    for attempt in range(60):
        try:
            q.get_collections()
            return q
        except Exception:
            if attempt == 59:
                raise
            time.sleep(1)


def main():
    mode = os.getenv("DATASET_MODE", "existing")
    if mode == "demo":
        manifest = json.loads((Path(__file__).resolve().parents[1] / "data/demo/manifest.json").read_text(encoding="utf-8"))
        if os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small") != manifest["embedding_model"]:
            raise RuntimeError("Embedding model differs from the bundled vectors; regenerate vectors instead of relabeling them")
        from .seed import main as seed
        seed()
        return
    if mode != "existing":
        raise RuntimeError("DATASET_MODE must be existing or demo")
    conn = backend.get_db_connection()
    try:
        with conn.cursor() as cur:
            for table in ("categories", "restaurants", "menus", "menu_flavors", "reviews"):
                cur.execute(f"SELECT COUNT(*) n FROM `{table}`")
                count = cur.fetchone()["n"]
                if table in {"menus", "menu_flavors"} and not count:
                    raise RuntimeError("The imported SQL needs menus and precomputed menu_flavors. Schema-only dumps cannot provide vector recommendations.")
            cur.execute("CREATE TABLE IF NOT EXISTS deployment_state (state_key VARCHAR(64) PRIMARY KEY,state_value TEXT NOT NULL)")
            cur.execute("SELECT state_key,state_value FROM deployment_state")
            old_state = {row["state_key"]: row["state_value"] for row in cur.fetchall()}
            cur.execute("SELECT state_value FROM deployment_state WHERE state_key='dataset_sha256'")
            if cur.fetchone():
                raise RuntimeError("This is a demo database. Use a separate Compose project for existing data.")
            cur.execute("SELECT state_value FROM deployment_state WHERE state_key='embedding_model'")
            stored_model = cur.fetchone()
            if stored_model and stored_model["state_value"] != os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"):
                raise RuntimeError("Embedding model differs from the initialized vectors; regenerate vectors instead of relabeling them")
            import_state.validate(conn, old_state)
            cur.execute("CREATE TABLE IF NOT EXISTS menu_tag_map (menu_id INT NOT NULL,tag_type VARCHAR(32) NOT NULL,tag_value VARCHAR(64) NOT NULL,PRIMARY KEY(menu_id,tag_type,tag_value),INDEX idx_tag_lookup(tag_value,menu_id)) CHARACTER SET utf8mb4")
            for table, name, columns in (("menus", "idx_lab_price_rest", "price,restaurant_id,id"),
                                         ("menus", "idx_lab_rest_price", "restaurant_id,price,id"),
                                         ("restaurants", "idx_lab_category_id", "category_id,id"),
                                         ("reviews", "idx_lab_review_score", "restaurant_id,review_score")):
                cur.execute(f"SHOW INDEX FROM `{table}` WHERE Key_name=%s", (name,))
                if not cur.fetchone():
                    cur.execute(f"CREATE INDEX `{name}` ON `{table}` ({columns})")
            cur.execute("SELECT m.id AS menu_id,m.menu_name,r.category_id,mf.menu_tags FROM menus m "
                        "JOIN restaurants r ON r.id=m.restaurant_id LEFT JOIN menu_flavors mf ON mf.menu_id=m.id")
            tags = [(row["menu_id"], "normalized", tag) for row in cur.fetchall() for tag in backend.scoring._menu_tags_for_row(row)]
            tags = sorted(set(tags))
        q = client()
        name = os.environ["QDRANT_COLLECTION"]
        dimension = 1536
        counts = {"points": 0, "menu_vectors": 0, "review_vectors": 0, "missing_menu_vectors": 0}
        desired = {}
        with conn.cursor(pymysql.cursors.SSDictCursor) as cur:
            cur.execute("SELECT m.id AS menu_id,mf.semantic_embedding,mf.review_embedding FROM menus m "
                        "JOIN restaurants r ON r.id=m.restaurant_id LEFT JOIN menu_flavors mf ON mf.menu_id=m.id ORDER BY m.id")
            while rows := cur.fetchmany(64):
                for row in rows:
                    vectors = {}
                    for field, key in (("semantic_embedding", "menu"), ("review_embedding", "review")):
                        value = vector(row[field], dimension)
                        if value is not None:
                            vectors[key] = value
                            counts[key + "_vectors"] += 1
                    if "menu" not in vectors:
                        counts["missing_menu_vectors"] += 1
                    if vectors:
                        desired[row["menu_id"]] = vectors
        counts["points"] = len(desired)
        if not counts["menu_vectors"]:
            raise RuntimeError("No valid 1536-dimensional menu embeddings were found. Generate compatible embeddings before starting the API.")
        owner = (json.loads(old_state["index_owner"]) if old_state.get("index_owner") else
                 {"dataset_id": str(uuid.uuid4()), "mode": "existing", "version": 1})
        with conn.cursor() as cur:
            cur.execute("INSERT INTO deployment_state VALUES ('index_owner',%s) ON DUPLICATE KEY UPDATE state_value=VALUES(state_value)", (json.dumps(owner),))
        conn.commit()
        digest = reconcile(q, name, desired, owner, dimension,
                           allow_legacy=old_state.get("dataset_mode") == "existing" and bool(old_state.get("indexed_points")))
        with conn.cursor() as cur:
            cur.execute("DELETE FROM menu_tag_map WHERE tag_type='normalized'")
            for start in range(0, len(tags), 1000):
                cur.executemany("INSERT IGNORE INTO menu_tag_map VALUES (%s,%s,%s)", tags[start:start + 1000])
            for key, value in {"dataset_mode": "existing", "indexed_points": str(counts["points"]),
                               "index_ids_digest": digest,
                               "index_summary": json.dumps(counts), "embedding_model": os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")}.items():
                cur.execute("INSERT INTO deployment_state VALUES (%s,%s) ON DUPLICATE KEY UPDATE state_value=VALUES(state_value)", (key, value))
        conn.commit()
        print(json.dumps({"status": "initialized", "fictional": False, **counts}), flush=True)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
