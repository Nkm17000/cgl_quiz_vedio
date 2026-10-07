import json
from pathlib import Path

# Keep history anchored to the project directory rather than the process cwd.
BASE_DIR = Path(__file__).resolve().parents[1]
MEMORY_FILE = BASE_DIR / "data" / "history" / "history.json"
MEMORY_VERSION = 3


def _default_memory():
    return {
        "version": MEMORY_VERSION,
        "counters": {},
        "last_run": {},
    }


def _normalize_memory(data):
    """Normalize old/new history formats without losing valid per-source counters."""
    if not isinstance(data, dict):
        return _default_memory()

    # New format.
    counters = data.get("counters")
    if isinstance(counters, dict):
        normalized = _default_memory()
        normalized["counters"] = {
            str(key): max(0, int(value or 0))
            for key, value in counters.items()
        }
        last_run = data.get("last_run")
        if isinstance(last_run, dict):
            normalized["last_run"] = last_run
        return normalized

    # Old format had one global counter (usually from the old 4-question
    # selection logic). It cannot safely be applied to independent 20-question
    # source windows, so migrate to the new schema with fresh per-source
    # counters. The old value is intentionally not reused.
    return _default_memory()


def load_memory():
    if not MEMORY_FILE.exists():
        return _default_memory()

    try:
        data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        return _normalize_memory(data)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return _default_memory()


def save_memory(memory):
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    normalized = _normalize_memory(memory)
    temp_file = MEMORY_FILE.with_suffix(".tmp")
    temp_file.write_text(
        json.dumps(normalized, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temp_file.replace(MEMORY_FILE)
