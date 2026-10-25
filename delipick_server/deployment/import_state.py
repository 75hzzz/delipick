"""Validate trusted dump provenance and recognize only completed imports."""
import json
import os
from pathlib import Path


def read_metadata():
    configured = os.getenv("IMPORT_METADATA_PATH")
    path = Path(configured) if configured else Path("/database/import_metadata.json")
    if not configured and not path.is_file():
        path = Path(__file__).resolve().parents[1] / "database/import_metadata.json"
    if not path.is_file():
        raise RuntimeError("Missing database/import_metadata.json; provide trusted dump model and checksum metadata")
    metadata = json.loads(path.read_text(encoding="utf-8-sig"))
    if metadata.get("dimensions") != 1536 or metadata.get("embedding_model") != os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"):
        raise RuntimeError("Embedding model differs from trusted dump metadata; regenerate vectors instead of relabeling them")
    digest = metadata.get("sql_sha256", "")
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise RuntimeError("Invalid trusted SQL checksum")
    return metadata


def validate(conn, old_state):
    metadata = read_metadata()
    with conn.cursor() as cur:
        cur.execute("SHOW TABLES LIKE 'delipick_import_state'")
        marker_exists = bool(cur.fetchone())
        marker = None
        if marker_exists:
            cur.execute("SELECT status,sql_sha256 FROM delipick_import_state WHERE id=1")
            marker = cur.fetchone()
        if marker and marker["status"] != "complete":
            raise RuntimeError("SQL import is incomplete; recover it explicitly rather than reusing partial data")
        legacy = marker is None and old_state.get("dataset_mode") == "existing" and old_state.get("indexed_points")
        if not marker and not legacy:
            raise RuntimeError("Database has no recognized completed import; automatic adoption is forbidden")
        if marker and marker["sql_sha256"] != metadata["sql_sha256"]:
            raise RuntimeError("SQL import checksum differs from trusted metadata")
        if legacy or old_state.get("dataset_mode") != "existing":
            expected = metadata.get("expected_counts", {})
            for table in ("categories", "restaurants", "menus", "menu_flavors", "reviews"):
                if table not in expected:
                    raise RuntimeError("Trusted metadata must include all source table counts")
                cur.execute(f"SELECT COUNT(*) n FROM `{table}`")
                if cur.fetchone()["n"] != expected[table]:
                    raise RuntimeError("Source table counts differ from the trusted dump; partial import is possible")
        if legacy:
            cur.execute("CREATE TABLE delipick_import_state (id INT PRIMARY KEY,status VARCHAR(16) NOT NULL,sql_sha256 CHAR(64) NOT NULL)")
            cur.execute("INSERT INTO delipick_import_state VALUES (1,'complete',%s)", (metadata["sql_sha256"],))
    return metadata
