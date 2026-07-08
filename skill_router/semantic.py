"""Семантический поиск по эмбеддингам (BAAI/bge-small-en). Пути — из config."""
import io
import json

from . import config

MODEL = "BAAI/bge-small-en-v1.5"
_STATE = {}


def available():
    return config.semantic_ready()


def _load():
    if "vecs" not in _STATE:
        import numpy as np
        from fastembed import TextEmbedding
        _STATE["np"] = np
        _STATE["vecs"] = np.load(config.semantic_path()).astype(np.float32)
        _STATE["ids"] = json.loads(io.open(config.semantic_ids_path(), encoding="utf-8").read())
        try:
            _STATE["model"] = TextEmbedding(MODEL)
        except Exception as e:
            # первый запуск качает модель с HuggingFace — сети нет → без сырого трейсбека
            raise RuntimeError(
                f"Could not load the embedding model {MODEL} "
                "(first run downloads it from HuggingFace). "
                f"Check network access and retry. Original error: {e}") from e
    return _STATE


def embed(texts):
    """Список строк → нормированная матрица эмбеддингов (numpy)."""
    import numpy as np
    s = _load()
    model = s["model"]
    embed_q = getattr(model, "query_embed", None) or model.embed
    rows = [next(iter(embed_q([t]))) for t in texts]
    m = np.array(rows, dtype=np.float32)
    m /= (np.linalg.norm(m, axis=1, keepdims=True) + 1e-9)
    return m


def search(query, top=20):
    """→ [(entity_id, score)] по косинусной близости."""
    s = _load()
    np = s["np"]
    q = embed([query])[0]
    sims = s["vecs"] @ q
    k = min(top, len(sims))
    idx = np.argpartition(-sims, k - 1)[:k]
    idx = idx[np.argsort(-sims[idx])]
    return [(s["ids"][i], float(sims[i])) for i in idx]
