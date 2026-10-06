import json
import random
from pathlib import Path

from config import QUIZ_DIR
from utils.memory import load_memory, save_memory

QUIZ_SIZE = 10

# Eight subject runs per push/manual execution. Five use the dedicated banks
# shipped with this repository; the remaining three are selected from the
# mixed 50,000-question bank by category.
SUBJECT_JOBS = [
    {"subject": "ENGLISH", "file": "smart_learning_lab_english_grammar_10000_questions_reshuffled.json"},
    {"subject": "GENERAL SCIENCE", "file": "smart_learning_lab_general_science_10000_questions_reshuffled.json"},
    {"subject": "GK", "file": "smart_learning_lab_gk_10000_questions_reshuffled.json"},
    {"subject": "MATH", "file": "smart_learning_lab_math_10000_questions_reshuffled.json"},
    {"subject": "REASONING", "file": "smart_learning_lab_reasoning_10000_questions_reshuffled.json"},
    {"subject": "HISTORY", "file": "smart_learning_lab_50000_mixed_questions.json", "category": "History"},
    {"subject": "GEOGRAPHY", "file": "smart_learning_lab_50000_mixed_questions.json", "category": "Geography"},
    {"subject": "POLITY", "file": "smart_learning_lab_50000_mixed_questions.json", "category": "Polity"},
    {"subject": "COMPUTER SCIENCE", "file": "computer_science_10000_bilingual_ssc_cgl_reshuffled.json"},
    {"subject": "RAJASTHAN GK", "file": "rajasthan_gk_10000_bilingual_ssc_cgl_reshuffled.json"},
]


def _load_json(path: Path):
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a JSON array")
    return data


def _matches_category(item, category):
    return str(item.get("category", "")).strip().casefold() == category.casefold()


def _select_questions(data, job, counter):
    category = job.get("category")
    if category:
        pool = [item for item in data if _matches_category(item, category)]
    else:
        pool = data

    if len(pool) < QUIZ_SIZE:
        raise ValueError(
            f"Not enough questions for {job['subject']}: {len(pool)} available; "
            f"need at least {QUIZ_SIZE}."
        )

    if counter + QUIZ_SIZE > len(pool):
        counter = 0

    batch = list(pool[counter:counter + QUIZ_SIZE])
    if len(batch) != QUIZ_SIZE:
        raise ValueError(
            f"Could not select {QUIZ_SIZE} questions for {job['subject']} "
            f"at counter {counter}."
        )
    random.shuffle(batch)
    return batch, counter, len(pool)


def fetch_quizzes(subject_index=None):
    """Return subject quizzes; when subject_index is set, return only that subject."""
    files = {p.name: p for p in Path(QUIZ_DIR).glob("*.json")}
    if not files:
        raise FileNotFoundError(f"No quiz JSON files found in {QUIZ_DIR}")

    memory = load_memory()
    counters = memory.get("counters")
    if not isinstance(counters, dict):
        counters = {}

    jobs = []
    selected_jobs = SUBJECT_JOBS
    if subject_index is not None:
        subject_index = int(subject_index)
        if subject_index < 0 or subject_index >= len(SUBJECT_JOBS):
            raise ValueError(f"SUBJECT_INDEX must be 0-{len(SUBJECT_JOBS)-1}; got {subject_index}")
        selected_jobs = [SUBJECT_JOBS[subject_index]]

    for job in selected_jobs:
        path = files.get(job["file"])
        if path is None:
            raise FileNotFoundError(
                f"Required quiz bank missing for {job['subject']}: {job['file']}"
            )

        data = _load_json(path)
        source_key = path.name + (f"::{job['category']}" if job.get("category") else "")
        counter = int(counters.get(source_key, 0) or 0)
        batch, counter, pool_size = _select_questions(data, job, counter)

        item = {
            "questions": batch,
            "subject": job["subject"],
            "source_file": source_key,
            "source_path": path.name,
            "category": job.get("category"),
            "quiz_number": (counter // QUIZ_SIZE) + 1,
            "quiz_count_for_source": max(1, pool_size // QUIZ_SIZE),
            "counter": counter,
        }
        jobs.append(item)
        print(
            f"🎯 {job['subject']}: {QUIZ_SIZE} questions | "
            f"source={path.name} | counter={counter}"
        )

    print(f"📦 Total videos this run: {len(jobs)}")
    return jobs


def commit_quiz_counter(source_file: str, amount: int = QUIZ_SIZE) -> int:
    memory = load_memory()
    counters = memory.get("counters")
    if not isinstance(counters, dict):
        counters = {}
    current = int(counters.get(source_file, 0) or 0)
    new_value = current + int(amount)
    counters[source_file] = new_value
    memory["counters"] = counters
    save_memory(memory)
    print(f"💾 Counter committed: {source_file}: {current} -> {new_value}")
    return new_value
