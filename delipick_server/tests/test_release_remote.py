"""Optional mutation tests: run only in a disposable audit project."""
import os
import uuid
import pytest
from qdrant_client import QdrantClient, models
from delipick_server.deployment import initialize
from delipick_server import main
from delipick_server.deployment.index_sync import reconcile, point_ids

pytestmark = pytest.mark.skipif(os.getenv("RELEASE_AUDIT_MUTATIONS") != "true", reason="Disposable release-audit environment only")


@pytest.fixture
def conn():
    connection = main.get_db_connection()
    yield connection
    connection.close()


def test_real_qdrant_owner_guard_and_reconciliation():
    q = QdrantClient(url=os.environ["QDRANT_URL"])
    name = "release_audit_" + uuid.uuid4().hex
    owner = {"dataset_id": name, "mode": "test", "version": 1}
    try:
        q.create_collection(name, vectors_config={key: models.VectorParams(size=3, distance=models.Distance.COSINE) for key in ("menu", "review")})
        q.upsert(name, points=[models.PointStruct(id=1, vector={"menu": [0.0, 1.0, 0.0]})], wait=True)
        with pytest.raises(RuntimeError, match="unrecognized"):
            reconcile(q, name, {1: {"menu": [1.0, 0.0, 0.0]}}, owner, dimension=3)
        assert q.retrieve(name, ids=[1], with_vectors=True)[0].vector["menu"] == [0.0, 1.0, 0.0]
        reconcile(q, name, {1: {"menu": [0.0, 1.0, 0.0]}}, owner, dimension=3, allow_legacy=True)
        assert q.get_collection(name).config.metadata["delipick"] == owner
        with pytest.raises(RuntimeError, match="another dataset"):
            reconcile(q, name, {1: {"menu": [0.0, 1.0, 0.0]}}, {**owner, "dataset_id": "other"}, dimension=3)
    finally:
        if q.collection_exists(name):
            q.delete_collection(name)
        q.close()


def test_real_qdrant_removes_obsolete_ids_and_review_vectors():
    q = QdrantClient(url=os.environ["QDRANT_URL"])
    name = "release_audit_" + uuid.uuid4().hex
    owner = {"dataset_id": name, "mode": "test", "version": 1}
    try:
        reconcile(q, name, {1: {"menu": [1.0, 0.0, 0.0], "review": [0.0, 1.0, 0.0]}, 2: {"menu": [0.0, 0.0, 1.0]}}, owner, dimension=3)
        reconcile(q, name, {1: {"menu": [1.0, 0.0, 0.0]}}, owner, dimension=3)
        assert point_ids(q, name) == {1}
        assert set(q.retrieve(name, ids=[1], with_vectors=True)[0].vector) == {"menu"}
    finally:
        if q.collection_exists(name):
            q.delete_collection(name)
        q.close()


def test_reinitialization_removes_stale_normalized_tags_but_keeps_manual_tags(conn):
    if os.getenv("DATASET_MODE") == "demo":
        pytest.skip("Normalized SQL rebuild applies to imported real-data mode")
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM menus ORDER BY id LIMIT 1")
        menu_id = cur.fetchone()["id"]
        cur.execute("INSERT INTO menu_tag_map VALUES (%s,'normalized','__audit_stale__')", (menu_id,))
        cur.execute("INSERT INTO menu_tag_map VALUES (%s,'manual','__audit_manual__')", (menu_id,))
    conn.commit()
    try:
        initialize.main()
        with conn.cursor() as cur:
            cur.execute("SELECT tag_type,tag_value FROM menu_tag_map WHERE menu_id=%s", (menu_id,))
            values = {(row["tag_type"], row["tag_value"]) for row in cur.fetchall()}
        assert ("normalized", "__audit_stale__") not in values
        assert ("manual", "__audit_manual__") in values
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM menu_tag_map WHERE menu_id=%s AND tag_value IN ('__audit_stale__','__audit_manual__')", (menu_id,))
        conn.commit()
