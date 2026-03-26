# faiss cache

from typing import Dict, Any

# in-memory cache
faiss_cache: Dict[str, Any] = {}

# optional: limit cache size (prevents memory overflow)
MAX_CACHE_SIZE = 10


def get_cache_key(semester, department, program) -> str:
    # normalize inputs to avoid mismatch
    semester = int(semester) if semester is not None else "NA"
    department = (department or "NA").strip().lower()
    program = (program or "NA").strip().lower()

    return f"{department}:{program}:{semester}"


def set_cache(cache_key: str, data: Any):
    # evict oldest if cache full
    if len(faiss_cache) >= MAX_CACHE_SIZE:
        oldest_key = next(iter(faiss_cache))
        faiss_cache.pop(oldest_key, None)

    faiss_cache[cache_key] = data


def get_cache(cache_key: str):
    return faiss_cache.get(cache_key)


def invalidate_cache(cache_key: str):
    faiss_cache.pop(cache_key, None)


def clear_all_cache():
    faiss_cache.clear()