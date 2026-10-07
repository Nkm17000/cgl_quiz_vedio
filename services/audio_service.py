import asyncio
import hashlib
from pathlib import Path
from typing import Optional

from config import QUESTION_AUDIO_DIR, TTS_CONCURRENCY, TTS_RATE, TTS_VOICE, TTS_VOLUME


def question_text(question: dict) -> str:
    custom = question.get("audio_text")
    if isinstance(custom, str) and custom.strip():
        return custom.strip()

    value = question.get("question", "")
    if isinstance(value, dict):
        return str(value.get("en") or value.get("hi") or "").strip()
    return str(value).strip()


def _content_key(question: dict) -> str:
    # IDs are intentionally not used: the supplied datasets reuse IDs 1..N
    # independently in every subject file. Content hashing prevents audio from
    # one question being reused for a different question after shuffling.
    text = question_text(question).strip().casefold()
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:20]


def _generated_path(question: dict) -> Path:
    return QUESTION_AUDIO_DIR / f"question_{_content_key(question)}.mp3"


def find_existing_audio(question: dict) -> Optional[str]:
    explicit = question.get("audio_file")
    if explicit:
        path = Path(str(explicit)).expanduser()
        if path.is_file() and path.stat().st_size > 0:
            return str(path)

    path = _generated_path(question)
    if path.is_file() and path.stat().st_size > 0:
        return str(path)

    return None


async def _generate(text: str, output_path: Path) -> None:
    try:
        import edge_tts
    except ImportError as exc:
        raise RuntimeError(
            "edge-tts is required when question audio is not supplied."
        ) from exc

    speaker = edge_tts.Communicate(
        text=text,
        voice=TTS_VOICE,
        rate=TTS_RATE,
        volume=TTS_VOLUME,
    )
    await speaker.save(str(output_path))


def ensure_question_audio(question: dict) -> str:
    existing = find_existing_audio(question)
    if existing:
        return existing

    text = question_text(question)
    if not text:
        raise ValueError("Question has no text available for narration")

    QUESTION_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    output = _generated_path(question)
    asyncio.run(_generate(text, output))
    return str(output)


def ensure_question_audio_batch(questions):
    """Ensure all quiz narration files exist, generating missing files concurrently."""
    results = [None] * len(questions)

    async def _run_batch():
        semaphore = asyncio.Semaphore(TTS_CONCURRENCY)

        async def generate_one(index, question):
            existing = find_existing_audio(question)
            if existing:
                results[index] = existing
                return

            text = question_text(question)
            if not text:
                raise ValueError(f"Question {index + 1} has no text available for narration")

            QUESTION_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
            output = _generated_path(question)
            async with semaphore:
                # Re-check after waiting in case another task produced the same hash.
                existing_after_wait = find_existing_audio(question)
                if existing_after_wait:
                    results[index] = existing_after_wait
                    return
                await _generate(text, output)
            results[index] = str(output)

        await asyncio.gather(*(generate_one(i, q) for i, q in enumerate(questions)))

    asyncio.run(_run_batch())
    return results
