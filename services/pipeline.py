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
    return f"""📊 {subject} Exam Focus

📚 Daily practice for serious aspirants

🎯 SSC | UPSC | Banking | Railway | RAS | IAS

For more quizzes, visit: {PAGE_URL}

💬 Drop your answer below

#sscpreparation #upsc #bankexam #railwayexam #mocktest #govtexams #studyreels"""


def _safe_name(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_")


def _output_path(item) -> Path:
    source = _safe_name(Path(item["source_file"].split("::", 1)[0]).stem)
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
    print(f"📊 Subject: {item['subject']} | Source: {item['source_file']} | counter: {item['counter']}")
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
            raise RuntimeError(f"Video file was not created correctly: {output_video}")

        return str(output_video)
    finally:
        cleanup(images)


def run_pipeline():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    raw_index = os.getenv("SUBJECT_INDEX", "").strip()
    subject_index = int(raw_index) if raw_index else None
    jobs = fetch_quizzes(subject_index=subject_index)

    expected = 1 if subject_index is not None else 10
    if len(jobs) != expected:
        raise RuntimeError(f"Expected {expected} subject quiz(es), got {len(jobs)}")

    event = os.getenv("GITHUB_EVENT_NAME", "").strip().lower()
    label = f"subject {subject_index + 1}/10" if subject_index is not None else "all 10 subjects"
    print("=" * 80)
    print(f"🚀 {event or 'local'} run: generating {label}")
    print(f"📊 Questions per quiz: {QUIZ_SIZE}")
    print("📦 Videos this job: 1" if subject_index is not None else "📦 Videos this job: 10")
    print("=" * 80)

    all_questions = [q for item in jobs for q in item["questions"]]
    print(f"\n🔊 Pre-generating narration for {len(all_questions)} questions...")
    ensure_question_audio_batch(all_questions)
    print("✅ Narration cache ready. Starting video rendering...")

    generated = [None] * len(jobs)
    workers = max(1, min(2, int(os.getenv("VIDEO_WORKERS", "2"))))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {}
        for index, item in enumerate(jobs, 1):
            print(f"\n🔹 QUEUED SUBJECT {index}: {item['subject']}")
            work_dir = OUTPUT_DIR / "work" / f"subject_{subject_index + 1:02d}" if subject_index is not None else OUTPUT_DIR / "work" / f"subject_{index:02d}"
            future_map[executor.submit(_generate_one, item, work_dir)] = index - 1

        for future in as_completed(future_map):
            idx = future_map[future]
            generated[idx] = future.result()
            print(f"✅ SUBJECT VIDEO READY: {generated[idx]}")

    pending = []
    for item, video in zip(jobs, generated):
        pending.append({
            "subject_index": subject_index,
            "source_file": item["source_file"],
            "subject": item["subject"],
            "quiz_number": item["quiz_number"],
            "counter": item["counter"],
            "questions": QUIZ_SIZE,
            "video_file": Path(video).name,
            "caption": _caption(item["subject"]),
        })

    PENDING_FILE.write_text(
        json.dumps(pending, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"\n✅ Generated {len(pending)} video(s). Instagram publication is handled by the final sequential publish job.")
