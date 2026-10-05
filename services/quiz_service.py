import json
import random
from pathlib import Path

from config import QUIZ_DIR
from utils.memory import load_memory, save_memory

# Never create a quiz smaller than this.
QUIZ_SIZE = 10
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


def _ensure_subject_history(memory, source_key, subject, total_questions):
    history = memory.setdefault("subjects", {})
    entry = history.setdefault(source_key, {})
    entry.setdefault("subject", subject)
    entry["total_questions"] = total_questions
    entry.setdefault("next_question_index", 0)
    entry.setdefault("quizzes_generated", 0)
    entry.setdefault("last_quiz_number", 0)
    entry.setdefault("last_questions", QUIZ_SIZE)
    return entry


def fetch_quizzes():
    """Build one >=10-question quiz for every JSON source.

    Each source has an independent persistent next_question_index, so every
    subject continues from its own position instead of sharing one counter.
    The mixed source is also retained, producing the eighth video when present.
    """
    files = sorted(Path(QUIZ_DIR).glob("*.json"))
    if not files:
        raise FileNotFoundError(f"No quiz JSON files found in {QUIZ_DIR}")

    mix_files = [path for path in files if _is_mix_file(path)]
    if len(mix_files) > 1:
        raise ValueError("Only one mixed-question JSON file is supported; found: " + ", ".join(path.name for path in mix_files))

    memory = load_memory()
    subjects = memory.setdefault("subjects", {})
    counters = memory.setdefault("counters", {})
    quizzes = []

    for path in files:
        data = _load_json(path)
        if len(data) < QUIZ_SIZE:
            raise ValueError(f"{path.name} contains only {len(data)} questions; at least {QUIZ_SIZE} are required.")

        source_key = path.name
        subject = _subject_from_file(path)
        entry = _ensure_subject_history(memory, source_key, subject, len(data))

        # Prefer the new subject/source track. Fall back to the old counter so
        # an existing deployment does not lose its previous progress.
        if source_key in subjects and "next_question_index" in entry:
            counter = int(entry.get("next_question_index", 0) or 0)
        else:
            counter = int(counters.get(source_key, 0) or 0)

        # The track is a cyclic pointer into the source JSON.
        counter %= len(data)
        end = counter + QUIZ_SIZE
        if end <= len(data):
            batch = list(data[counter:end])
        else:
            batch = list(data[counter:]) + list(data[: end - len(data)])

        if len(batch) < QUIZ_SIZE:
            raise ValueError(f"Could not select at least {QUIZ_SIZE} questions from {source_key}")

        random.shuffle(batch)
        quiz_number = int(entry.get("quizzes_generated", 0) or 0) + 1
        quiz_count_for_source = max(1, (len(data) + QUIZ_SIZE - 1) // QUIZ_SIZE)

        quizzes.append({
            "questions": batch,
            "subject": subject,
            "source_file": source_key,
            "quiz_number": quiz_number,
            "quiz_count_for_source": quiz_count_for_source,
            "counter": counter,
            "start_question_index": counter,
        })
        print(
            f"🎯 {subject}: planned quiz of {QUIZ_SIZE} questions from {source_key}; "
            f"starting question index {counter}"
        )

    # Persist discovery of every subject before generation begins.
    save_memory(memory)
    print(f"📦 Total quizzes this run: {len(quizzes)}")
    return quizzes


def get_manual_quiz(quizzes):
    """Backward-compatible helper: return the English quiz if requested."""
    for item in quizzes:
        if item["subject"] == "ENGLISH":
            return item
    raise RuntimeError("English quiz source was not found.")


def commit_quiz_counter(source_file: str, amount: int = QUIZ_SIZE, subject: str | None = None) -> int:
    """Advance only the successfully published source and update subject history."""
    memory = load_memory()
    subjects = memory.setdefault("subjects", {})
    counters = memory.setdefault("counters", {})
    entry = subjects.setdefault(source_file, {})

    current = int(entry.get("next_question_index", counters.get(source_file, 0)) or 0)
    total = int(entry.get("total_questions", 0) or 0)
    amount = int(amount)
    new_value = current + amount
    if total > 0:
        new_value %= total

    entry["subject"] = subject or entry.get("subject") or source_file
    entry["next_question_index"] = new_value
    entry["quizzes_generated"] = int(entry.get("quizzes_generated", 0) or 0) + 1
    entry["last_quiz_number"] = entry["quizzes_generated"]
    entry["last_questions"] = amount

    # Keep the legacy counter synchronized for compatibility with old tooling.
    counters[source_file] = new_value
    memory["counters"] = counters
    memory["subjects"] = subjects
    save_memory(memory)
    print(f"💾 Track committed: {source_file}: {current} -> {new_value} (next question index)")
    return new_value
