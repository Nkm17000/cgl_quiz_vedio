#!/usr/bin/env python3
import json
import os
from pathlib import Path

from config import OUTPUT_DIR
from services.instagram_service import post_instagram
from services.quiz_service import QUIZ_SIZE, commit_quiz_counter

ROOT = Path(__file__).resolve().parent
PENDING_FILE = OUTPUT_DIR / "pending_publish.json"


def main():
    if not PENDING_FILE.exists():
        raise RuntimeError(f"{PENDING_FILE} not found. Run app.py first.")

    pending_all = json.loads(PENDING_FILE.read_text(encoding="utf-8"))
    if isinstance(pending_all, dict):
        pending_all = [pending_all]
    if not isinstance(pending_all, list) or len(pending_all) != 8:
        raise RuntimeError(f"Expected exactly 8 pending quizzes, got {len(pending_all) if isinstance(pending_all, list) else 'invalid'}")

    index = int(os.getenv("PENDING_INDEX", "0"))
    if index < 0 or index >= len(pending_all):
        raise RuntimeError(f"PENDING_INDEX must be 0-7; got {index}")

    pending = pending_all[index]
    video_url = os.getenv("INSTAGRAM_VIDEO_URL", "").strip()
    if not video_url:
        raise RuntimeError("INSTAGRAM_VIDEO_URL is missing.")

    if int(pending.get("questions", 0)) != QUIZ_SIZE:
        raise RuntimeError(
            f"Pending video has {pending.get('questions')} questions; expected exactly {QUIZ_SIZE}."
        )

    print("=" * 80)
    print(f"📤 Publishing subject {index + 1}/8 to Instagram")
    print(f"📚 Subject: {pending['subject']}")
    print(f"📊 Questions: {pending['questions']}")
    print(f"📁 Source: {pending['source_file']}")
    print(f"🔢 Quiz number: {pending['quiz_number']}")
    print(f"🔗 Video URL: {video_url}")
    print("=" * 80)

    result = post_instagram(video_url, pending["caption"])
    print(f"✅ Instagram published successfully: {result}")

    new_counter = commit_quiz_counter(pending["source_file"], QUIZ_SIZE)

    history_file = ROOT / "data" / "history" / "history.json"
    history = {}
    if history_file.exists():
        try:
            history = json.loads(history_file.read_text(encoding="utf-8"))
        except Exception:
            history = {}

    last_run = history.setdefault("last_run", {})
    last_run[pending["source_file"]] = {
        "subject": pending["subject"],
        "quiz_number": pending["quiz_number"],
        "source_counter_after": new_counter,
        "platform": "instagram",
        "questions": QUIZ_SIZE,
    }
    history_file.write_text(
        json.dumps(history, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"💾 {pending['subject']} counter committed after successful publication.")


if __name__ == "__main__":
    main()
