import copy
import json
from types import SimpleNamespace

import pytest
from qdrant_client import QdrantClient, models
from delipick_server.deployment import import_state
from delipick_server.deployment.index_sync import ensure_collection, reconcile, point_ids
from delipick_server.deployment.initialize import vector


@pytest.fixture
def q():
    client = QdrantClient(":memory:")
    yield client
    client.close()


OWNER = {"dataset_id": "test-owned", "mode": "existing", "version": 1}
EXPECTED = {1: {"menu": [1.0, 0.0, 0.0]}}


def unowned(q, vector_value):
    q.create_collection("test", vectors_config={key: models.VectorParams(size=3, distance=models.Distance.COSINE) for key in ("menu", "review")})
    q.upsert("test", points=[models.PointStruct(id=1, vector={"menu": vector_value})])


def test_unknown_nonempty_collection_is_untouched(q):
    unowned(q, [0.0, 1.0, 0.0])
    with pytest.raises(RuntimeError, match="unrecognized"):
        reconcile(q, "test", EXPECTED, OWNER, dimension=3)
    assert q.retrieve("test", ids=[1], with_vectors=True)[0].vector["menu"] == [0.0, 1.0, 0.0]
    assert not q.get_collection("test").config.metadata


def test_legacy_adoption_requires_every_vector_to_match(q):
    unowned(q, [0.0, 1.0, 0.0])
    with pytest.raises(RuntimeError, match="unrecognized"):
        reconcile(q, "test", EXPECTED, OWNER, dimension=3, allow_legacy=True)
    q.upsert("test", points=[models.PointStruct(id=1, vector=EXPECTED[1])])
    reconcile(q, "test", EXPECTED, OWNER, dimension=3, allow_legacy=True)
    assert q.get_collection("test").config.metadata["delipick"] == OWNER


def test_other_dataset_owner_is_never_overwritten(q):
    reconcile(q, "test", EXPECTED, OWNER, dimension=3)
    with pytest.raises(RuntimeError, match="another dataset"):
        reconcile(q, "test", EXPECTED, {**OWNER, "dataset_id": "another"}, dimension=3, allow_legacy=True)
    assert q.get_collection("test").config.metadata["delipick"] == OWNER


def test_reconcile_removes_stale_points_and_removed_named_vectors(q):
    initial = {1: {"menu": [1.0, 0.0, 0.0], "review": [0.0, 1.0, 0.0]}, 2: {"menu": [0.0, 0.0, 1.0]}}
    reconcile(q, "test", initial, OWNER, dimension=3)
    reconcile(q, "test", EXPECTED, OWNER, dimension=3)
    assert point_ids(q, "test") == {1}
    assert set(q.retrieve("test", ids=[1], with_vectors=True)[0].vector) == {"menu"}


@pytest.mark.parametrize("raw", [None, "not-json", "[0,0,0]", "[NaN,1,2]", "[1,2]", '["bad",1,2]'])
def test_invalid_vectors_are_not_indexed(raw):
    assert vector(raw, 3) is None


class Cursor:
    def __init__(self, marker, counts):
        self.marker, self.counts, self.value = marker, counts, None
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def execute(self, sql, args=None):
        if sql.startswith("SHOW TABLES"):
            self.value = {"table": "delipick_import_state"} if self.marker is not None else None
        elif sql.startswith("SELECT status"):
            self.value = self.marker
        elif sql.startswith("SELECT COUNT"):
            table = sql.split('`')[1]
            self.value = {"n": self.counts[table]}
        else:
            self.value = None
    def fetchone(self): return self.value


@pytest.fixture
def metadata(tmp_path, monkeypatch):
    data = {"embedding_model": "text-embedding-3-small", "dimensions": 1536, "sql_sha256": "a" * 64,
            "expected_counts": {key: 1 for key in ("categories", "restaurants", "menus", "menu_flavors", "reviews")}}
    path = tmp_path / "metadata.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setenv("IMPORT_METADATA_PATH", str(path))
    monkeypatch.setenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    return data


def connection(metadata, marker):
    cur = Cursor(marker, dict(metadata["expected_counts"]))
    return SimpleNamespace(cursor=lambda: cur), cur


def test_incomplete_import_is_rejected(metadata):
    conn, _ = connection(metadata, {"status": "importing", "sql_sha256": "a" * 64})
    with pytest.raises(RuntimeError, match="incomplete"):
        import_state.validate(conn, {})


def test_unknown_nonempty_database_is_not_adopted(metadata):
    conn, _ = connection(metadata, None)
    with pytest.raises(RuntimeError, match="no recognized"):
        import_state.validate(conn, {})


def test_first_import_count_mismatch_is_rejected(metadata):
    conn, cur = connection(metadata, {"status": "complete", "sql_sha256": "a" * 64})
    cur.counts["reviews"] = 0
    with pytest.raises(RuntimeError, match="partial import"):
        import_state.validate(conn, {})


def test_validated_legacy_counts_can_be_adopted(metadata):
    conn, _ = connection(metadata, None)
    assert import_state.validate(conn, {"dataset_mode": "existing", "indexed_points": "1"}) == metadata


def test_model_identity_cannot_be_inferred_from_dimension(metadata, monkeypatch):
    monkeypatch.setenv("OPENAI_EMBEDDING_MODEL", "another-1536-model")
    with pytest.raises(RuntimeError, match="model differs"):
        import_state.read_metadata()
