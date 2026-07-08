"""Движок среднего яруса B→C: грани → широкий recall (rating≥5) → разнообразный отбор (MMR).

Балл 0.65·релевантность + 0.25·rating + 0.1·installs; MMR с бонусом за непокрытую грань,
мягкие квоты на узкие грани, потолок на грань, дедуп почти-дублей, порог релевантности.
Грань кандидату — по СЫРОЙ близости (о чём скилл), вес влияет на балл (не на назначение).
"""
import io
import json
import math

import numpy as np

from . import config, semantic

_POOL = {}


def _load_catalog():
    cat = {}
    for l in io.open(config.catalog_path(), encoding="utf-8"):
        l = l.strip()
        if not l:
            continue
        try:
            c = json.loads(l)
        except Exception:
            continue
        cat[c["entity_id"]] = c
    return cat


def load_pool(min_rating=5.0):
    """Пул rating≥min с эмбеддингами (нормированы). Кэш на процесс."""
    key = round(min_rating, 2)
    if key in _POOL:
        return _POOL[key]
    ids = json.loads(io.open(config.semantic_ids_path(), encoding="utf-8").read())
    vecs = np.load(config.semantic_path()).astype(np.float32)
    cat = _load_catalog()
    keep, meta = [], []
    for i, eid in enumerate(ids):
        c = cat.get(eid)
        if not c or c.get("hard_block"):
            continue
        if (c.get("rating") or 0) < min_rating:
            continue
        keep.append(i)
        meta.append(c)
    res = (vecs[keep], meta)
    _POOL[key] = res
    return res


def _norm01(x):
    x = np.asarray(x, dtype=np.float32)
    lo, hi = float(x.min()), float(x.max())
    return (x - lo) / (hi - lo) if hi > lo else np.zeros_like(x)


def select(facets, target=45, k_per_facet=150, lam=0.75, min_rating=5.0,
           min_quota=2, dup_cos=0.90, cov_bonus=0.15, min_rel=0.28):
    """Грани [{facet,weight}] → отобранные ~40-50 разнообразных (list[dict])."""
    if not facets:
        return []
    pool_vecs, meta = load_pool(min_rating)
    if len(meta) == 0:
        return []
    fvecs = semantic.embed([f["facet"] for f in facets])
    weights = np.array([float(f.get("weight", 1.0)) for f in facets], dtype=np.float32)

    sim = fvecs @ pool_vecs.T
    best_facet = np.argmax(sim, axis=0)          # по СЫРОЙ близости
    best_raw = np.max(sim, axis=0)

    cand = set()
    for f in range(len(facets)):
        cand.update(np.argsort(-sim[f])[:k_per_facet].tolist())
    cand = np.array([i for i in sorted(cand) if best_raw[i] >= min_rel], dtype=np.int64)
    if len(cand) == 0:
        return []

    cfacet = best_facet[cand]
    # релевантность = СЫРАЯ близость×вес (без min-max: он раздувал мелкие разницы косинусов)
    rel = best_raw[cand] * weights[cfacet]
    rating = np.array([(meta[i].get("rating") or 0) for i in cand], dtype=np.float32) / 10.0
    inst = np.array([math.log10((meta[i].get("installs") or 0) + 1) for i in cand], dtype=np.float32)
    inst = _norm01(inst)
    score = 0.65 * rel + 0.25 * rating + 0.10 * inst

    cvecs = pool_vecs[cand]
    n = len(cand)
    fcap = max(min_quota + 1, int(math.ceil(target / len(facets) * 2)))

    chosen = []
    covered = set()
    facet_count = {}
    taken = np.zeros(n, dtype=bool)
    sel_sims = np.full(n, -1.0, dtype=np.float32)

    def _commit(j):
        taken[j] = True
        chosen.append(j)
        f = int(cfacet[j])
        covered.add(f)
        facet_count[f] = facet_count.get(f, 0) + 1
        np.maximum(sel_sims, cvecs @ cvecs[j], out=sel_sims)

    # 1) квота-проход — гарантируем покрытие
    for f in range(len(facets)):
        picked = 0
        for j in np.argsort(-score):
            if picked >= min_quota:
                break
            if taken[j] or int(cfacet[j]) != f or sel_sims[j] > dup_cos:
                continue
            _commit(j)
            picked += 1

    # 2) MMR-добор до target
    while len(chosen) < target:
        mmr = lam * score - (1.0 - lam) * np.where(sel_sims < 0, 0.0, sel_sims)
        for j in range(n):
            if int(cfacet[j]) not in covered:
                mmr[j] += cov_bonus
        mmr[taken] = -1e9
        mmr[sel_sims > dup_cos] = -1e9
        for j in range(n):
            if facet_count.get(int(cfacet[j]), 0) >= fcap:
                mmr[j] = -1e9
        j = int(np.argmax(mmr))
        if mmr[j] <= -1e8:
            break
        _commit(j)

    out = []
    for j in chosen:
        c = meta[int(cand[j])]
        out.append({
            "name": c.get("name"), "rating": c.get("rating"), "canon": c.get("canon"),
            "canon_path": c.get("canon_path"), "risk": c.get("risk"),
            "hard_block": bool(c.get("hard_block")), "needs_review": bool(c.get("needs_review")),
            "needs_audit": bool(c.get("needs_audit")), "installs": c.get("installs"),
            "sha256": c.get("sha256"), "facet": facets[int(cfacet[j])]["facet"],
            "rel": round(float(rel[j]), 3),
        })
    out.sort(key=lambda r: -(r["rating"] or 0))
    return out
