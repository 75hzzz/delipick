"""Optional Docker adapter; conventional main.py remains usable directly."""
import json
import os
from pathlib import Path

from fastapi import HTTPException
from delipick_server import main, vector_search
from .replay import install, records
from .index_sync import point_ids, ids_digest
from qdrant_client import models

DATASET = os.getenv("DATASET_MODE", "existing")
MODE = os.getenv("QUERY_MODE", "replay")
if DATASET not in {"existing", "demo"} or MODE not in {"replay", "live"}:
    raise RuntimeError("Invalid DATASET_MODE or QUERY_MODE")
if MODE == "replay":
    install(main)
elif not os.getenv("OPENAI_API_KEY", "").strip():
    raise RuntimeError("QUERY_MODE=live requires your own OPENAI_API_KEY")
fixtures = json.loads((Path(__file__).resolve().parents[1] / "data/demo/query_fixtures.json").read_text(encoding="utf-8"))
if (MODE == "replay" or DATASET == "demo") and os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small") != fixtures["embedding_model"]:
    raise RuntimeError("Replay query vectors require the recorded embedding model")
app = main.app


@app.get("/deployment/info")
def info():
    return {"query_mode": MODE, "dataset_mode": DATASET, "fictional_dataset": DATASET == "demo",
            "examples": [case["text"] for case in records()], "live_mode_may_incur_api_charges": True,
            "scope": "Replay supports four fixed requests, not arbitrary natural language. Existing SQL and embeddings are supplied separately."}


@app.get("/deployment/health")
def health():
    try:
        connection = main.get_db_connection()
        try:
            with connection.cursor() as cur:
                cur.execute("SELECT state_key,state_value FROM deployment_state")
                state = {row["state_key"]: row["state_value"] for row in cur.fetchall()}
                if DATASET == "demo":
                    manifest = json.loads((Path(__file__).resolve().parents[1] / "data/demo/manifest.json").read_text(encoding="utf-8"))
                    if state.get("dataset_sha256") != manifest["sha256"]:
                        raise RuntimeError("Demo data mismatch")
                    expected = manifest["menus"]
                else:
                    if state.get("dataset_mode") != "existing":
                        raise RuntimeError("Existing-data initialization is incomplete")
                    if state.get("embedding_model") != os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"):
                        raise RuntimeError("Embedding model mismatch; do not relabel existing vectors")
                    expected = int(state["indexed_points"])
        finally:
            connection.close()
        q, collection = vector_search.client(), vector_search.collection()
        info = q.get_collection(collection)
        if (info.config.metadata or {}).get("delipick") != json.loads(state["index_owner"]):
            raise RuntimeError("Vector collection belongs to a different dataset")
        ids = point_ids(q, collection)
        if len(ids) != expected or ids_digest(ids) != state["index_ids_digest"]:
            raise RuntimeError("Vector index is incomplete")
        summary = json.loads(state["index_summary"])
        for key in ("menu", "review"):
            count = q.count(collection, count_filter=models.Filter(must=[models.HasVectorCondition(has_vector=key)]), exact=True).count
            if count != summary[key + "_vectors"]:
                raise RuntimeError("Named-vector coverage differs from the SQL index snapshot")
    except Exception as error:
        raise HTTPException(503, detail="MySQL or Qdrant is not initialized for this dataset mode") from error
    return {"status": "ok", "dataset_mode": DATASET, "fictional_dataset": DATASET == "demo", "query_mode": MODE, "indexed_points": expected}
