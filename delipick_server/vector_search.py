"""Two-stage retrieval; MySQL is authoritative, Qdrant is a derived index."""
import json
import os
from functools import lru_cache

from qdrant_client import QdrantClient, models

SAFE_REQUIRED = {"국물", "면", "밥", "죽", "음료", "따뜻함", "차가움"}
EXPERIENCE = {"혼밥", "아이동반", "속편함", "해장", "야식", "든든함", "가벼움", "가족식사"}


@lru_cache(maxsize=1)
def client():
    return QdrantClient(url=os.getenv("QDRANT_URL", "http://127.0.0.1:16333"), timeout=60)


def collection():
    return os.getenv("QDRANT_COLLECTION", "delipick_lab_1")


def conditions(intent):
    required = sorted(set(intent.get("must_tags", [])) & SAFE_REQUIRED)
    excluded = sorted(set(intent.get("avoid_tags", [])) - EXPERIENCE)
    terms = sorted(set(intent.get("avoid_terms", [])))
    return required, excluded, terms


def metadata_sql(req, intent, filtered=True, details=False):
    clauses = ["m.price BETWEEN %s AND %s", "(r.category_id=7 OR m.price >= 4000)"]
    params = [req.min_price, req.max_price]
    if req.category_ids:
        clauses.append("r.category_id IN (" + ",".join(["%s"] * len(req.category_ids)) + ")")
        params.extend(req.category_ids)
    if filtered:
        required, excluded, terms = conditions(intent)
        for tag in required:
            clauses.append("EXISTS (SELECT 1 FROM menu_tag_map t WHERE t.menu_id=m.id AND t.tag_value=%s)")
            params.append(tag)
        if excluded:
            clauses.append("NOT EXISTS (SELECT 1 FROM menu_tag_map t WHERE t.menu_id=m.id AND t.tag_value IN (" + ",".join(["%s"] * len(excluded)) + "))")
            params.extend(excluded)
        for term in terms:
            clauses.append("LOCATE(%s, REPLACE(m.menu_name, ' ', ''))=0")
            params.append(term.replace(" ", ""))
    fields = "m.id AS menu_id, m.restaurant_id"
    join = "JOIN restaurants r ON r.id=m.restaurant_id "
    if details:
        fields += (", m.menu_name, m.price, r.category_id, r.name AS restaurant_name, mf.menu_tags, "
                   "mf.salty, mf.sweet, mf.sour, mf.umami, mf.spicy, "
                   "mf.review_salty, mf.review_sweet, mf.review_sour, mf.review_umami, mf.review_spicy")
        join += "LEFT JOIN menu_flavors mf ON mf.menu_id=m.id "
    return ("SELECT " + fields + " FROM menus m " + join + "WHERE " + " AND ".join(clauses)), params


def filter_candidates(conn, req, intent):
    sql, params = metadata_sql(req, intent, details=True)
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def search(candidate_ids, menu_vector, review_vector, limit=None):
    if not candidate_ids:
        return []
    k = limit or int(os.getenv("RETRIEVAL_K", "100"))
    query_filter = models.Filter(must=[models.HasIdCondition(has_id=candidate_ids)])
    # Union protects experience-oriented requests from menu-only retrieval bias.
    ids = set()
    for name, vector in (("menu", menu_vector), ("review", review_vector)):
        if vector:
            result = client().query_points(
                collection_name=collection(), using=name, query=vector,
                query_filter=query_filter, limit=k, with_payload=False,
                with_vectors=False, search_params=models.SearchParams(hnsw_ef=512),
            )
            ids.update(int(point.id) for point in result.points)
    return sorted(ids)


def flatten_tags(raw):
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            return []
    if not isinstance(raw, dict):
        return []
    return [(str(kind), str(tag)) for kind, values in raw.items()
            if isinstance(values, list) for tag in values if isinstance(tag, str)]
