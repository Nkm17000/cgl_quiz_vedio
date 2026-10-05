import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
MEMORY_FILE = BASE_DIR / "data" / "history" / "history.json"
MEMORY_VERSION = 4


def _default_memory():
    return {
        "version": MEMORY_VERSION,
        "counters": {},
        "subjects": {},
        "last_run": {},
    }


def _normalize_memory(data):
    if not isinstance(data, dict):
        return _default_memory()

    normalized = _default_memory()

    counters = data.get("counters")
    if isinstance(counters, dict):
        for key, value in counters.items():
            try:
                normalized["counters"][str(key)] = max(0, int(value or 0))
            except (TypeError, ValueError):
                continue

    subjects = data.get("subjects")
    if isinstance(subjects, dict):
        normalized["subjects"] = subjects

    last_run = data.get("last_run")
    if isinstance(last_run, dict):
        normalized["last_run"] = last_run

    # Migrate an existing source-counter history into subject tracking. The
    # subject names are completed by quiz_service when the JSON sources load.
    for source, counter in normalized["counters"].items():
        entry = normalized["subjects"].setdefault(source, {})
        entry.setdefault("next_question_index", counter)
        entry.setdefault("quizzes_generated", 0)
        entry.setdefault("last_quiz_number", 0)
        entry.setdefault("last_questions", 10)

    normalized["version"] = MEMORY_VERSION
    return normalized


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
