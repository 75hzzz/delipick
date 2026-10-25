"""Real Docker DB/Qdrant tests for either trusted SQL or fictional demo data."""
import os
import random
import subprocess
import sys
import types

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from delipick_server import main, vector_search
from delipick_server.deployment.app import app
from delipick_server.deployment.replay import records


@pytest.fixture
def conn():
    connection = main.get_db_connection()
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture
def fixed_eta(monkeypatch):
    original = main.calculate_queueing_metrics
    def fixed(prep, delivery, hour):
        context = {**original.__globals__, "random": random.Random(f"integration:{prep}:{delivery}")}
        return types.FunctionType(original.__code__, context, original.__name__, original.__defaults__, original.__closure__)(prep, delivery, 12)
    monkeypatch.setattr(main, "calculate_queueing_metrics", fixed)


def test_health_and_existing_routes():
    with TestClient(app) as client:
        assert client.get("/deployment/health").status_code == 200
        assert client.get("/categories").status_code == 200
        assert client.get("/restaurants").status_code == 200
        assert client.post("/recommendations", json={"taste_levels": {"spicy": 0}, "limit": 5}).status_code == 200
        assert client.post("/recommendations", json={"preference_text": "not a recorded query"}).status_code == 422


@pytest.mark.parametrize("case", records(), ids=lambda c: c["id"])
@pytest.mark.parametrize("user_type", ["convenience", "gourmet", "budget"])
@pytest.mark.parametrize("taste", [{}, {"spicy": 0}, {"spicy": 2, "salty": 2}])
def test_results_match_filtered_full(case, user_type, taste, conn, fixed_eta, monkeypatch):
    request = main.RecommendationRequest(preference_text=case["text"], user_type=user_type, taste_levels=taste, limit=5)
    monkeypatch.setenv("RETRIEVAL_ENGINE", "sql")
    reference = main.run_recommendation(request, conn)
    monkeypatch.setenv("RETRIEVAL_ENGINE", "qdrant")
    monkeypatch.setenv("RECALL_EXACT_THRESHOLD", "0")
    actual = main.run_recommendation(request, conn)
    assert [(i.id, i.menu_id) for i in actual.items] == [(i.id, i.menu_id) for i in reference.items]
    assert [i.final_score for i in actual.items] == pytest.approx([i.final_score for i in reference.items], abs=1e-9)
    assert main._retrieval_context.get() is None
    if os.getenv("DATASET_MODE") == "demo":
        assert actual.count > 0


def test_price_category_and_recognized_exclusions(conn):
    case = next(c for c in records() if c["id"] == "soup_mild")
    request = main.RecommendationRequest(preference_text=case["text"], category_ids=[1], max_price=10000, limit=5)
    result = main.run_recommendation(request, conn)
    required, excluded, terms = vector_search.conditions(case["intent"])
    with conn.cursor() as cur:
        for item in result.items:
            cur.execute("SELECT m.id AS menu_id,m.menu_name,m.price,r.category_id,mf.menu_tags FROM menus m JOIN restaurants r ON r.id=m.restaurant_id LEFT JOIN menu_flavors mf ON mf.menu_id=m.id WHERE m.id=%s", (item.menu_id,))
            row = cur.fetchone()
            tags = main.scoring._menu_tags_for_row(row)
            assert row["category_id"] == 1 and row["price"] <= 10000
            assert set(required) <= tags
            assert not set(excluded) & tags
            assert not any(term.replace(" ", "") in row["menu_name"].replace(" ", "") for term in terms)


def test_qdrant_failure_returns_503(conn, monkeypatch):
    monkeypatch.setenv("RECALL_EXACT_THRESHOLD", "0")
    def fail(*args, **kwargs):
        raise ConnectionError("Injected outage")
    monkeypatch.setattr(vector_search, "search", fail)
    with pytest.raises(HTTPException) as error:
        main.run_recommendation(main.RecommendationRequest(preference_text=records()[0]["text"]), conn)
    assert error.value.status_code == 503
    assert main._retrieval_context.get() is None


def test_live_requires_personal_key():
    env = {**os.environ, "QUERY_MODE": "live", "OPENAI_API_KEY": ""}
    result = subprocess.run([sys.executable, "-c", "import delipick_server.deployment.app"], env=env, capture_output=True, text=True)
    assert result.returncode != 0
    assert "requires your own OPENAI_API_KEY" in result.stderr


def test_replay_rejects_different_embedding_model():
    env = {**os.environ, "QUERY_MODE": "replay", "OPENAI_API_KEY": "", "OPENAI_EMBEDDING_MODEL": "different-model"}
    result = subprocess.run([sys.executable, "-c", "import delipick_server.deployment.app"], env=env, capture_output=True, text=True)
    assert result.returncode != 0
    assert "embedding model" in result.stderr.lower()


def test_initializer_does_not_relabel_existing_vectors():
    env = {**os.environ, "OPENAI_API_KEY": "", "OPENAI_EMBEDDING_MODEL": "different-model"}
    result = subprocess.run([sys.executable, "-m", "delipick_server.deployment.initialize"], env=env, capture_output=True, text=True)
    assert result.returncode != 0
    assert "model differs" in result.stderr.lower()
