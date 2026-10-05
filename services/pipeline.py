import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from config import OUTPUT_DIR, PAGE_URL
from services.quiz_service import QUIZ_SIZE, fetch_quizzes
from services.video_service import create_video, generate_images
from services.audio_service import ensure_question_audio_batch
from services.instagram_service import post_instagram
from utils.file_utils import cleanup


PENDING_FILE = OUTPUT_DIR / "pending_publish.json"


def _caption(subject: str) -> str:
    return f"""📊 ALL Subject Exam Focus

📚 Daily practice for serious aspirants

🎯 SSC | UPSC | Banking | Railway | RAS | IAS

For more quizzes, visit: {PAGE_URL}

💬 Drop your answer below

#sscpreparation #upsc #bankexam #railwayexam #mocktest #govtexams #studyreels"""


def _safe_name(value: str) -> str:
    return "".join(
        ch.lower() if ch.isalnum() else "_"
        for ch in value
    ).strip("_")


def _output_path(item) -> Path:
    source = _safe_name(Path(item["source_file"]).stem)
    number = item["quiz_number"]
    subject = _safe_name(item["subject"])
    return OUTPUT_DIR / f"instagram_{subject}_quiz_{source}_{number:05d}.mp4"


def _generate_one(item, work_dir: Path):
    quiz = item["questions"]
    if len(quiz) != QUIZ_SIZE:
        raise RuntimeError(
            f"{item['source_file']} quiz must contain exactly {QUIZ_SIZE} "
            f"questions; got {len(quiz)}"
        )

    print("\n" + "=" * 80)
    print(f"🎯 Generating exactly {QUIZ_SIZE}-question Instagram Reel")
    print(f"📊 Source: {item['source_file']} | counter: {item['counter']}")
    print("=" * 80)

    images = []
    output_video = _output_path(item)
    output_video.unlink(missing_ok=True)

    try:
        work_dir.mkdir(parents=True, exist_ok=True)
        print("🖼️ Rendering slides...")
        images = generate_images(quiz, subject=item["subject"], work_dir=work_dir)

        print("🎬 Creating video...")
        create_video(quiz, output_video, subject=item["subject"], work_dir=work_dir)

        if not output_video.is_file() or output_video.stat().st_size <= 0:
            raise RuntimeError(
                f"Video file was not created correctly: {output_video}"
            )

        caption = _caption(item["subject"])


        # The default GitHub workflow publishes through the public GitHub
        # Release URL after this generation step. Direct URL publishing remains
        # available for local/manual use by setting PUBLIC_VIDEO_URL.
        video_url = os.getenv("PUBLIC_VIDEO_URL", "").strip()
        if video_url and os.getenv("DEFER_INSTAGRAM_PUBLISH", "").lower() != "true":
            print("📤 Publishing Reel using public video URL...")
            result = post_instagram(video_url, caption)
            print(f"✅ Instagram published successfully: {result}")

        return str(output_video)
    finally:
        cleanup(images)


def run_pipeline():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    jobs = fetch_quizzes()
    if len(jobs) != 10:
        raise RuntimeError(f"Expected exactly 10 subject quizzes, got {len(jobs)}")

    event = os.getenv("GITHUB_EVENT_NAME", "").strip().lower()
    print("=" * 80)
    print(f"🚀 {event or 'local'} run: generating all 10 subject quizzes")
    print(f"📊 Questions per quiz: {QUIZ_SIZE}")
    print("📦 Videos this run: 10")
    print("=" * 80)

    # Generate all narration first. This removes ten sequential TTS wait cycles
    # and lets Edge TTS use the configured concurrency across the whole run.
    all_questions = [q for item in jobs for q in item["questions"]]
    print(f"\n🔊 Pre-generating narration for {len(all_questions)} questions...")
    ensure_question_audio_batch(all_questions)
    print("✅ Narration cache ready. Starting parallel video rendering...")

    generated = [None] * len(jobs)
    workers = max(1, min(2, int(os.getenv("VIDEO_WORKERS", "2"))))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {}
        for index, item in enumerate(jobs, 1):
            print(f"\n🔹 QUEUED SUBJECT {index}/10: {item['subject']}")
            work_dir = OUTPUT_DIR / "work" / f"subject_{index:02d}"
            future = executor.submit(_generate_one, item, work_dir)
            future_map[future] = index - 1

        for future in as_completed(future_map):
            idx = future_map[future]
            generated[idx] = future.result()
            print(f"✅ SUBJECT {idx + 1}/10 video ready: {generated[idx]}")

    # Publish is intentionally handled by publish.py after public GitHub
    # Release URLs are created. The pending file contains all 10 jobs.
    pending_file = OUTPUT_DIR / "pending_publish.json"
    pending_file.write_text(
        json.dumps(
            [
                {
                    "source_file": item["source_file"],
                    "subject": item["subject"],
                    "quiz_number": item["quiz_number"],
                    "counter": item["counter"],
                    "questions": QUIZ_SIZE,
                    "video_file": Path(video).name,
                    "caption": _caption(item["subject"]),
                }
                for item, video in zip(jobs, generated)
            ],
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    print("\n✅ All 10 videos generated. Instagram publication is handled separately by the workflow.")
