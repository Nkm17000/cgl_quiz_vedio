import json
import random
from pathlib import Path

from config import QUIZ_DIR
from utils.memory import load_memory, save_memory

QUIZ_SIZE = 5
MIX_QUIZ_COUNT = 1


def _load_json(path: Path):
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a JSON array")
    return data


def _is_mix_file(path: Path) -> bool:
    return "mixed" in path.stem.casefold()


def _subject_from_file(path: Path) -> str:
    stem = path.stem.casefold()
    if _is_mix_file(path):
        return "ALL SUBJECTS"
    exact_patterns = (
        # Keep specific subjects before generic GK so rajasthan_gk is not
        # accidentally classified as the generic GK subject.
        ("english_grammar", "ENGLISH"),
        ("general_science", "GENERAL SCIENCE"),
        ("computer_science", "COMPUTER SCIENCE"),
        ("rajasthan_gk", "RAJASTHAN GK"),
        ("reasoning", "REASONING"),
        ("math", "MATH"),
        ("gk", "GK"),
    )
    for pattern, subject in exact_patterns:
        if pattern in stem:
            return subject
    return path.stem.replace("_", " ").upper()


def fetch_quizzes():
    """Return one quiz for every supported JSON source.

    Normal subject files produce one 5-question quiz each. The mixed file
    produces one 5-question quiz. Each source has its own persistent counter.
    """
    files = sorted(Path(QUIZ_DIR).glob("*.json"))
    if not files:
        raise FileNotFoundError(f"No quiz JSON files found in {QUIZ_DIR}")

    mix_files = [path for path in files if _is_mix_file(path)]
    if len(mix_files) > 1:
        raise ValueError("Only one mixed-question JSON file is supported; found: " + ", ".join(path.name for path in mix_files))

    memory = load_memory()
    counters = memory.get("counters")
    if not isinstance(counters, dict):
        counters = {}

    quizzes = []
    for path in files:
        data = _load_json(path)
        if len(data) < QUIZ_SIZE:
            raise ValueError(f"{path.name} contains only {len(data)} questions; at least {QUIZ_SIZE} are required.")

        source_key = path.name
        counter = int(counters.get(source_key, 0) or 0)
        if counter + QUIZ_SIZE > len(data):
            counter = 0

        batch = list(data[counter:counter + QUIZ_SIZE])
        if len(batch) != QUIZ_SIZE:
            raise ValueError(f"Could not select {QUIZ_SIZE} questions from {source_key} at counter {counter}")
        random.shuffle(batch)

        subject = _subject_from_file(path)
        quizzes.append({
            "questions": batch,
            "subject": subject,
            "source_file": source_key,
            "quiz_number": (counter // QUIZ_SIZE) + 1,
            "quiz_count_for_source": max(1, len(data) // QUIZ_SIZE),
            "counter": counter,
        })
        print(f"🎯 {subject}: planned 1 quiz of {QUIZ_SIZE} questions from {source_key}; starting counter {counter}")

    print(f"📦 Total quizzes this run: {len(quizzes)}")
    return quizzes


def get_manual_quiz(quizzes):
    """Return the English quiz for manual/push runs.

    The list is alphabetically sorted, so adding a new source such as
    computer_science must not change the existing manual-run subject.
    """
    for item in quizzes:
        if item["subject"] == "ENGLISH":
            return item
    raise RuntimeError("Manual run requires the ENGLISH quiz source, but it was not found.")


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
