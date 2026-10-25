"""Ownership-checked reconciliation of derived Qdrant data."""
import hashlib
import json
import math

from qdrant_client import models


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


def point_ids(q, name):
    ids, offset = set(), None
    while True:
        points, offset = q.scroll(name, limit=256, offset=offset, with_payload=False, with_vectors=False)
        ids.update(int(point.id) for point in points)
        if offset is None:
            return ids


def ids_digest(ids):
    return hashlib.sha256(json.dumps(sorted(ids), separators=(",", ":")).encode()).hexdigest()


def legacy_vectors_match(q, name, expected):
    seen, offset = set(), None
    while True:
        points, offset = q.scroll(name, limit=64, offset=offset, with_payload=False, with_vectors=True)
        for point in points:
            menu_id = int(point.id)
            actual = point.vector or {}
            if menu_id not in expected or set(actual) != set(expected[menu_id]):
                return False
            for key, raw in expected[menu_id].items():
                norm = math.sqrt(sum(value * value for value in raw))
                wanted = [value / norm for value in raw]
                if len(actual[key]) != len(wanted) or not all(math.isclose(a, b, abs_tol=1e-6, rel_tol=1e-5) for a, b in zip(actual[key], wanted)):
                    return False
            seen.add(menu_id)
        if offset is None:
            return seen == set(expected)


def ensure_collection(q, name, dimension, owner, expected, allow_legacy=False):
    if not q.collection_exists(name):
        q.create_collection(name, vectors_config={key: models.VectorParams(size=dimension, distance=models.Distance.COSINE) for key in ("menu", "review")},
                            hnsw_config=models.HnswConfigDiff(m=16, ef_construct=100, full_scan_threshold=20000),
                            optimizers_config=models.OptimizersConfigDiff(indexing_threshold=64, default_segment_number=1),
                            metadata={"delipick": owner})
        return
    info = q.get_collection(name)
    config = info.config.params.vectors
    if set(config) != {"menu", "review"} or any(v.size != dimension or v.distance != models.Distance.COSINE for v in config.values()):
        raise RuntimeError("Existing Qdrant collection has incompatible vector settings")
    existing_owner = (info.config.metadata or {}).get("delipick")
    if existing_owner == owner:
        return
    if existing_owner is not None:
        raise RuntimeError("Qdrant collection belongs to another dataset; choose a new collection name")
    count = q.count(name, exact=True).count
    if count and not (allow_legacy and legacy_vectors_match(q, name, expected)):
        raise RuntimeError("Refusing to overwrite an unrecognized nonempty Qdrant collection")
    # Old project volumes can be adopted only after every ID and vector matches.
    q.update_collection(name, metadata={"delipick": owner})


def reconcile(q, name, expected, owner, dimension=1536, allow_legacy=False, payload=None):
    ensure_collection(q, name, dimension, owner, expected, allow_legacy=allow_legacy)
    ids = sorted(expected)
    for start in range(0, len(ids), 64):
        batch = ids[start:start + 64]
        q.upsert(name, points=[models.PointStruct(id=menu_id, vector=expected[menu_id],
                 payload={"menu_id": menu_id, **(payload or {})}) for menu_id in batch], wait=True)
        for key in ("menu", "review"):
            absent = [menu_id for menu_id in batch if key not in expected[menu_id]]
            if absent:
                q.delete_vectors(name, vectors=[key], points=absent, wait=True)
    obsolete = sorted(point_ids(q, name) - set(ids))
    for start in range(0, len(obsolete), 256):
        q.delete(name, points_selector=models.PointIdsList(points=obsolete[start:start + 256]), wait=True)
    if point_ids(q, name) != set(ids):
        raise RuntimeError("Qdrant point IDs differ from the validated SQL source")
    for key in ("menu", "review"):
        wanted = sum(key in values for values in expected.values())
        actual = q.count(name, count_filter=models.Filter(must=[models.HasVectorCondition(has_vector=key)]), exact=True).count
        if actual != wanted:
            raise RuntimeError("Qdrant named-vector coverage differs from the validated SQL source")
    return ids_digest(ids)
