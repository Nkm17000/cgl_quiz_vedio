"""Question narration generation with resilient TTS fallback.

Primary: Edge TTS. If Microsoft's consumer endpoint returns 403 or is unavailable,
fallback to gTTS, then to local espeak if installed. Existing cached MP3 files
are always preserved and reused.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from config import QUESTION_AUDIO_DIR, TTS_VOICE, TTS_RATE, TTS_VOLUME, TTS_CONCURRENCY

log = logging.getLogger(__name__)
QUESTION_AUDIO_DIR = Path(QUESTION_AUDIO_DIR)
EDGE_RETRIES = max(0, int(os.getenv("TTS_EDGE_RETRIES", "1")))
EDGE_TIMEOUT = max(5, int(os.getenv("TTS_EDGE_TIMEOUT", "25")))
FALLBACK_TTS = os.getenv("TTS_FALLBACK", "gtts").strip().lower()
LANGUAGE = os.getenv("TTS_LANGUAGE", "en")


def _question_text(question: Any) -> str:
    """Accept common dataset formats without narrating Python dict syntax."""
    if isinstance(question, str):
        return question.strip()
    if not isinstance(question, dict):
        return str(question or "").strip()

    def val(value):
        if isinstance(value, dict):
            return str(value.get("en") or value.get("text") or value.get("hi") or "").strip()
        return str(value or "").strip()

    parts = []
    for key in ("question", "options"):
        value = question.get(key)
        if key == "question":
            text = val(value)
            if text:
                parts.append(text)
        elif isinstance(value, dict):
            opts = value.get("en")
            if isinstance(opts, list):
                parts.extend(f"Option {chr(65+i)}: {val(v)}" for i, v in enumerate(opts[:4]))
            elif opts:
                parts.append(val(opts))
        elif isinstance(value, (list, tuple)):
            parts.extend(
                f"Option {chr(65+i)}: {val(v)}" for i, v in enumerate(value[:4])
            )
    return ". ".join(p for p in parts if p).strip()


def _question_id(question: Any, text: str) -> str:
    if isinstance(question, dict):
        for key in ("question_id", "id", "qid", "question_no", "source_id"):
            value = question.get(key)
            if value is not None and str(value).strip():
                return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value).strip())[:100]
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def _valid_audio(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 512


async def _edge_generate(text: str, output_path: Path) -> None:
    import edge_tts
    last_error = None
    for attempt in range(EDGE_RETRIES + 1):
        try:
            speaker = edge_tts.Communicate(
                text=text, voice=TTS_VOICE, rate=TTS_RATE, volume=TTS_VOLUME
            )
            await asyncio.wait_for(speaker.save(str(output_path)), timeout=EDGE_TIMEOUT)
            if _valid_audio(output_path):
                return
            raise RuntimeError("Edge TTS returned an empty or invalid audio file")
        except Exception as exc:
            last_error = exc
            output_path.unlink(missing_ok=True)
            # 403 is generally endpoint/token blocking; a short retry is enough.
            if attempt < EDGE_RETRIES:
                await asyncio.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Edge TTS failed after retries: {last_error}") from last_error


def _gtts_generate(text: str, output_path: Path) -> None:
    from gtts import gTTS
    lang = os.getenv("GTTS_LANGUAGE", LANGUAGE)
    gTTS(text=text, lang=lang, slow=False).save(str(output_path))
    if not _valid_audio(output_path):
        raise RuntimeError("gTTS returned an empty or invalid audio file")


def _espeak_generate(text: str, output_path: Path) -> None:
    executable = shutil.which("espeak-ng") or shutil.which("espeak")
    if not executable:
        raise RuntimeError("Neither espeak-ng nor espeak is installed")
    wav_path = output_path.with_suffix(".wav")
    try:
        subprocess.run(
            [executable, "-w", str(wav_path), text[:4000]],
            check=True, timeout=60, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        # Convert to MP3 when ffmpeg is present; otherwise preserve WAV and rename
        # is deliberately avoided because the extension must match the encoding.
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            subprocess.run(
                [ffmpeg, "-y", "-loglevel", "error", "-i", str(wav_path),
                 "-codec:a", "libmp3lame", "-q:a", "5", str(output_path)],
                check=True, timeout=60, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
        else:
            raise RuntimeError("ffmpeg is required to convert espeak WAV to MP3")
        if not _valid_audio(output_path):
            raise RuntimeError("espeak fallback produced invalid audio")
    finally:
        wav_path.unlink(missing_ok=True)


async def _generate(text: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_name(output_path.stem + ".tmp.mp3")
    errors = []
    try:
        try:
            await _edge_generate(text, temp_path)
            temp_path.replace(output_path)
            return
        except Exception as exc:
            errors.append(f"Edge TTS: {exc}")
            log.warning("Edge TTS unavailable; trying fallback TTS. Reason: %s", exc)

        if FALLBACK_TTS in ("gtts", "auto", "both"):
            try:
                await asyncio.to_thread(_gtts_generate, text, temp_path)
                temp_path.replace(output_path)
                log.info("Narration generated with gTTS: %s", output_path.name)
                return
            except Exception as exc:
                errors.append(f"gTTS: {exc}")
                temp_path.unlink(missing_ok=True)
                log.warning("gTTS fallback failed: %s", exc)

        try:
            await asyncio.to_thread(_espeak_generate, text, output_path)
            return
        except Exception as exc:
            errors.append(f"espeak: {exc}")
            raise RuntimeError(
                "All narration providers failed. " + " | ".join(errors)
            ) from exc
    finally:
        temp_path.unlink(missing_ok=True)


async def _run_batch(questions):
    semaphore = asyncio.Semaphore(TTS_CONCURRENCY)

    async def generate_one(index, question):
        text = _question_text(question)
        if not text:
            log.warning("Skipping question %d because it has no narration text", index + 1)
            return
        output = QUESTION_AUDIO_DIR / f"{_question_id(question, text)}.mp3"
        if _valid_audio(output):
            return
        async with semaphore:
            try:
                await _generate(text, output)
            except Exception as exc:
                # Don't silently continue: the pipeline should report the exact
                # question that could not be narrated.
                raise RuntimeError(f"Narration failed for question {index + 1}: {exc}") from exc

    await asyncio.gather(*(generate_one(i, q) for i, q in enumerate(questions)))


def ensure_question_audio_batch(questions):
    """Generate missing audio concurrently; reuse existing cached question audio."""
    QUESTION_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    if not questions:
        return
    asyncio.run(_run_batch(questions))
