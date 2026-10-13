"""Robust question narration: Edge TTS -> gTTS -> espeak-ng + FFmpeg.

Preserves this project's content-hash cache and public helper functions.
"""
import asyncio
import hashlib
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from config import QUESTION_AUDIO_DIR, TTS_CONCURRENCY, TTS_RATE, TTS_VOICE, TTS_VOLUME

log = logging.getLogger(__name__)
EDGE_RETRIES = max(0, int(os.getenv("TTS_EDGE_RETRIES", "1")))
EDGE_TIMEOUT = max(5, int(os.getenv("TTS_EDGE_TIMEOUT", "30")))
TTS_FALLBACK_LANGUAGE = os.getenv("TTS_FALLBACK_LANGUAGE", "en")
TTS_FALLBACK = os.getenv("TTS_FALLBACK", "gtts").strip().lower()


def question_text(question: dict) -> str:
    custom = question.get("audio_text")
    if isinstance(custom, str) and custom.strip():
        return custom.strip()
    value = question.get("question", "")
    if isinstance(value, dict):
        return str(value.get("en") or value.get("hi") or "").strip()
    return str(value).strip()


def _content_key(question: dict) -> str:
    # IDs are intentionally not used: source files can reuse IDs 1..N.
    text = question_text(question).strip().casefold()
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:20]


def _generated_path(question: dict) -> Path:
    return Path(QUESTION_AUDIO_DIR) / f"question_{_content_key(question)}.mp3"


def _valid_audio(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 512


def find_existing_audio(question: dict) -> Optional[str]:
    explicit = question.get("audio_file")
    if explicit:
        path = Path(str(explicit)).expanduser()
        if path.is_file() and path.stat().st_size > 0:
            return str(path)
    path = _generated_path(question)
    return str(path) if _valid_audio(path) else None


async def _generate_edge(text: str, path: Path) -> None:
    import edge_tts
    last_error = None
    for attempt in range(EDGE_RETRIES + 1):
        try:
            speaker = edge_tts.Communicate(
                text=text, voice=TTS_VOICE, rate=TTS_RATE, volume=TTS_VOLUME
            )
            await asyncio.wait_for(speaker.save(str(path)), timeout=EDGE_TIMEOUT)
            if _valid_audio(path):
                return
            raise RuntimeError("Edge TTS returned an empty/invalid audio file")
        except Exception as exc:
            last_error = exc
            path.unlink(missing_ok=True)
            if attempt < EDGE_RETRIES:
                await asyncio.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Edge TTS failed after retries: {last_error}") from last_error


def _generate_gtts(text: str, path: Path) -> None:
    from gtts import gTTS
    gTTS(text=text, lang=TTS_FALLBACK_LANGUAGE, slow=False).save(str(path))
    if not _valid_audio(path):
        raise RuntimeError("gTTS returned an empty/invalid audio file")


def _generate_espeak(text: str, path: Path) -> None:
    exe = shutil.which("espeak-ng") or shutil.which("espeak")
    if not exe:
        raise RuntimeError("espeak-ng/espeak is not installed")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required for the local TTS fallback")
    wav = path.with_suffix(".fallback.wav")
    try:
        voice = os.getenv("ESPEAK_VOICE", "en")
        subprocess.run(
            [exe, "-v", voice, "-w", str(wav), text[:4000]],
            check=True, timeout=90, capture_output=True,
        )
        subprocess.run(
            [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(wav),
             "-codec:a", "libmp3lame", "-q:a", "5", str(path)],
            check=True, timeout=90, capture_output=True,
        )
        if not _valid_audio(path):
            raise RuntimeError("espeak fallback produced an empty/invalid MP3")
    finally:
        wav.unlink(missing_ok=True)


async def _generate(text: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Generate to temporary files, so interrupted requests never leave a
    # corrupt cache entry that subsequent runs mistake for valid audio.
    errors = []
    edge_tmp = output_path.with_name(output_path.stem + ".edge.tmp.mp3")
    gtts_tmp = output_path.with_name(output_path.stem + ".gtts.tmp.mp3")
    try:
        try:
            await _generate_edge(text, edge_tmp)
            edge_tmp.replace(output_path)
            return
        except Exception as exc:
            errors.append(f"Edge TTS: {exc}")
            log.warning("Edge TTS failed; trying fallback: %s", exc)

        if TTS_FALLBACK in ("gtts", "auto", "both"):
            try:
                await asyncio.to_thread(_generate_gtts, text, gtts_tmp)
                gtts_tmp.replace(output_path)
                log.info("Narration generated with gTTS: %s", output_path.name)
                return
            except Exception as exc:
                errors.append(f"gTTS: {exc}")
                log.warning("gTTS fallback failed: %s", exc)

        try:
            await asyncio.to_thread(_generate_espeak, text, output_path)
            log.info("Narration generated with espeak fallback: %s", output_path.name)
            return
        except Exception as exc:
            errors.append(f"espeak: {exc}")
            output_path.unlink(missing_ok=True)
            raise RuntimeError(
                "All narration providers failed. " + " | ".join(errors)
            ) from exc
    finally:
        edge_tmp.unlink(missing_ok=True)
        gtts_tmp.unlink(missing_ok=True)


def ensure_question_audio(question: dict) -> str:
    existing = find_existing_audio(question)
    if existing:
        return existing
    text = question_text(question)
    if not text:
        raise ValueError("Question has no text available for narration")
    output = _generated_path(question)
    asyncio.run(_generate(text, output))
    return str(output)


def ensure_question_audio_batch(questions):
    """Ensure all quiz narration exists, using the project's content-hash cache."""
    results = [None] * len(questions)

    async def _run_batch():
        semaphore = asyncio.Semaphore(max(1, int(TTS_CONCURRENCY)))

        async def generate_one(index, question):
            existing = find_existing_audio(question)
            if existing:
                results[index] = existing
                return
            text = question_text(question)
            if not text:
                raise ValueError(f"Question {index + 1} has no text available for narration")
            output = _generated_path(question)
            output.parent.mkdir(parents=True, exist_ok=True)
            async with semaphore:
                existing_after_wait = find_existing_audio(question)
                if existing_after_wait:
                    results[index] = existing_after_wait
                    return
                await _generate(text, output)
            results[index] = str(output)

        await asyncio.gather(*(generate_one(i, q) for i, q in enumerate(questions)))

    asyncio.run(_run_batch())
    return results
