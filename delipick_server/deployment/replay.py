"""Replay recorded external responses, never invent vectors or silently call APIs."""
from copy import deepcopy
import json
from pathlib import Path

from fastapi import HTTPException

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "data/demo/query_fixtures.json"


def records():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["cases"]


def install(module):
    cases = records()
    by_text = {c["text"]: c for c in cases}
    by_menu = {c["intent"].get("menu_embedding_text") or c["text"]: c["taste"] for c in cases}
    by_vectors = {}
    for case in cases:
        menu = case["intent"].get("menu_embedding_text") or case["text"]
        review = case["intent"].get("review_embedding_text") or menu
        by_vectors[(menu, review)] = case["vectors"]

    def intent(text):
        if not text.strip():
            return {"intent_type":"general","must_tags":[],"prefer_tags":[],"avoid_tags":[],
                    "avoid_terms":[],"menu_embedding_text":"","review_embedding_text":""}
        if text not in by_text:
            raise HTTPException(422, detail={"message": "Replay mode only supports recorded examples. Use QUERY_MODE=live for arbitrary text.", "examples": list(by_text)})
        return deepcopy(by_text[text]["intent"])

    def taste(text):
        if not text.strip():
            return {key:.5 for key in ("salty","sweet","sour","umami","spicy")}
        if text not in by_menu:
            raise HTTPException(422, detail="No recorded taste analysis for this text.")
        return deepcopy(by_menu[text])

    def embeddings(texts):
        if not any(str(text).strip() for text in texts):
            return [[] for _ in texts]
        key = tuple(texts)
        if key not in by_vectors:
            raise HTTPException(422, detail="No recorded query vectors for this input.")
        return deepcopy(by_vectors[key])

    module.build_preference_tag_intent = intent
    module.build_taste_vector_from_text = taste
    module.build_text_embeddings = embeddings
