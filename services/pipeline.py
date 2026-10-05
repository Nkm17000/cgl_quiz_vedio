import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

from config import INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_BUSINESS_ACCOUNT_ID, OUTPUT_DIR, PAGE_URL
from services.instagram_service import publish_video_to_instagram
from services.quiz_service import QUIZ_SIZE, commit_quiz_counter, fetch_quizzes
from services.video_service import create_video, generate_images
from utils.file_utils import cleanup
from utils.memory import load_memory, save_memory


class InstagramPublishingLimitError(RuntimeError):
    """Raised when Meta blocks further Content Publishing API media creation."""


IG_COOLDOWN_KEY = "instagram_upload_blocked_until"


def _instagram_upload_blocked() -> bool:
    memory = load_memory()
    raw = memory.get(IG_COOLDOWN_KEY)
    if not raw:
        return False
    try:
        blocked_until = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        memory.pop(IG_COOLDOWN_KEY, None)
        save_memory(memory)
        return False
    if blocked_until <= datetime.now(timezone.utc):
        memory.pop(IG_COOLDOWN_KEY, None)
        save_memory(memory)
        return False
    print(f"⏸️ Instagram upload cooldown active until {blocked_until.strftime('%Y-%m-%d %H:%M:%S UTC')}. Skipping this run.")
    return True


def _set_instagram_cooldown(hours: int = 24) -> None:
    blocked_until = datetime.now(timezone.utc) + timedelta(hours=hours)
    memory = load_memory()
    memory[IG_COOLDOWN_KEY] = blocked_until.isoformat()
    save_memory(memory)
    print(f"⏸️ Instagram publishing limit reached. Cooldown saved until {blocked_until.strftime('%Y-%m-%d %H:%M:%S UTC')}.")


def _caption(subject: str) -> str:
    return f"""📊 {subject} Exam Focus

📚 Daily practice for serious aspirants

🎯 SSC | UPSC | Banking | Railway | RAS | IAS

For more quizzes, visit: {PAGE_URL}

💬 Drop your answer below

#sscpreparation #upsc #bankexam #railwayexam #mocktest #govtexams #studyreels"""


def _safe_name(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_")


def _output_path(item) -> Path:
    source = _safe_name(Path(item["source_file"]).stem)
    number = item["quiz_number"]
    return OUTPUT_DIR / f"instagram_mixed_quiz_{source}_{number:05d}.mp4"


def _generate_one(item):
    quiz = item["questions"]
    if len(quiz) < QUIZ_SIZE:
        raise RuntimeError(
            f"{item['source_file']} quiz must contain at least {QUIZ_SIZE} questions; "
            f"got {len(quiz)}"
        )

    print("\n" + "=" * 80)
    print(f"🎯 Generating Instagram Reel: {QUIZ_SIZE}-question quiz")
    print(f"📊 Subject: {item['subject']}")
    print(f"📊 Source: {item['source_file']}")
    print(f"📍 Starting question index: {item['start_question_index']}")
    print(f"🔢 Quiz number: {item['quiz_number']}")
    print("=" * 80)

    images = []
    output_video = _output_path(item)
    output_video.unlink(missing_ok=True)

    try:
        print("🖼️ Rendering slides...")
        images = generate_images(quiz, subject=item["subject"])

        print("🎬 Creating video...")
        create_video(quiz, output_video, subject=item["subject"])

        if not output_video.is_file() or output_video.stat().st_size <= 0:
            raise RuntimeError(f"Video file was not created correctly: {output_video}")

        if not INSTAGRAM_BUSINESS_ACCOUNT_ID or not INSTAGRAM_ACCESS_TOKEN:
            raise RuntimeError(
                "Instagram credentials are missing. Set "
                "INSTAGRAM_BUSINESS_ACCOUNT_ID and INSTAGRAM_ACCESS_TOKEN."
            )

        print("📤 Publishing Reel to Instagram...")
        result = publish_video_to_instagram(str(output_video), _caption(item["subject"]))
        if result is None:
            raise InstagramPublishingLimitError(
                "Meta Content Publishing API limit reached; video was generated but not published."
            )
        print(f"✅ Instagram published successfully: {result}")

        new_counter = commit_quiz_counter(
            item["source_file"], QUIZ_SIZE, subject=item["subject"]
        )
        memory = load_memory()
        last_run = memory.setdefault("last_run", {})
        last_run[item["source_file"]] = {
            "subject": item["subject"],
            "quiz_number": item["quiz_number"],
            "source_counter_after": new_counter,
            "next_question_index": new_counter,
            "platform": "instagram",
            "questions": QUIZ_SIZE,
            "start_question_index": item["start_question_index"],
        }
        save_memory(memory)
        return str(output_video)
    finally:
        cleanup(images)


def run_pipeline():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if _instagram_upload_blocked():
        return

    print("📥 Preparing quizzes for Instagram...")
    quiz_jobs = fetch_quizzes()
    if not quiz_jobs:
        raise RuntimeError("No quizzes available")

    event = os.getenv("GITHUB_EVENT_NAME", "").strip().lower()
    is_manual_or_push = event in {"workflow_dispatch", "push", ""}

    # Manual runs, pushes, and scheduled runs all process every source.
    # With the current 8 JSON sources this produces up to 8 videos per run.
    jobs_to_process = quiz_jobs

    if is_manual_or_push:
        print(
            f"🖐️ Manual/push run: generating ALL subject/source videos "
            f"({len(jobs_to_process)} total, expected around 8)."
        )
    else:
        print(
            f"🗓️ Scheduled run: generating {len(jobs_to_process)} "
            "Instagram videos (one per subject/source)."
        )

    completed = 0
    failed = 0
    for item in jobs_to_process:
        try:
            _generate_one(item)
            completed += 1
        except InstagramPublishingLimitError as exc:
            failed += 1
            _set_instagram_cooldown()
            print(f"⏸️ Stopping run after Instagram publishing-limit error: {exc}")
            break
        except Exception as exc:
            failed += 1
            print(
                f"❌ Failed {item['subject']} quiz {item['quiz_number']} "
                f"from {item['source_file']}: {exc}"
            )
            continue

    print("=" * 80)
    print(f"✅ Instagram completed: {completed}/{len(jobs_to_process)}")
    print(f"❌ Instagram failed: {failed}/{len(jobs_to_process)}")
    print("=" * 80)
