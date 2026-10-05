import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path

from config import (
    VIDEO_CRF,
    VIDEO_PRESET,
    ANSWER_SLIDE_DURATION,
    BACKGROUND_AUDIO,
    BACKGROUND_VOLUME,
    CORRECT_AUDIO,
    CORRECT_VOLUME,
    COUNTDOWN_SECONDS,
    FPS,
    OUTPUT_DIR,
    POST_AUDIO_WAIT_SECONDS,
    TICK_AUDIO,
    TICK_VOLUME,
    VIDEO_HEIGHT,
    VIDEO_WIDTH,
)
from services.audio_service import ensure_question_audio_batch
from services.renderer import render_answer, render_question


def _run(command):
    print("▶", " ".join(shlex.quote(str(x)) for x in command))
    subprocess.run(command, check=True)


def _ffprobe_duration(path: str) -> float:
    """Return exact media duration using ffprobe, with an ffmpeg fallback.

    GitHub/Render images do not always expose ffprobe on PATH even when
    ffmpeg is installed. The fallback keeps duration detection portable.
    """
    path = str(path)
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        result = subprocess.run(
            [
                ffprobe, "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", path,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        value = result.stdout.strip()
        if value:
            return max(0.01, float(value))

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError(
            "FFmpeg is required for video generation, but neither ffprobe nor "
            "ffmpeg was found on PATH."
        )

    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", path],
        check=False,
        capture_output=True,
        text=True,
    )
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", result.stderr)
    if not match:
        raise RuntimeError(
            f"Could not determine audio duration for {path}. "
            f"ffmpeg output did not contain a Duration field."
        )
    hours, minutes, seconds = match.groups()
    return max(0.01, int(hours) * 3600 + int(minutes) * 60 + float(seconds))


def generate_images(quiz, subject=None):
    images = []
    # Defensive guard: one logical quiz question produces countdown, question,
    # and answer slides, but the number of logical questions must stay fixed.
    from services.quiz_service import QUIZ_SIZE
    if len(quiz) != QUIZ_SIZE:
        raise ValueError(
            f"generate_images expected exactly {QUIZ_SIZE} questions, got {len(quiz)}"
        )
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for index, question in enumerate(quiz):
        for timer in (3, 2, 1):
            path = OUTPUT_DIR / f"slide_{index}_{timer}.jpg"
            render_question(question, index, timer, path, subject=subject)
            images.append(str(path))

        question_path = OUTPUT_DIR / f"question_{index}.jpg"
        render_question(question, index, None, question_path, subject=subject)
        images.append(str(question_path))

        answer_path = OUTPUT_DIR / f"answer_{index}.jpg"
        render_answer(question, index, answer_path, subject=subject)
        images.append(str(answer_path))
    return images


def _write_concat_file(slides):
    concat_path = OUTPUT_DIR / "slides.txt"
    with concat_path.open("w", encoding="utf-8") as file:
        for image, duration in slides:
            file.write(f"file {shlex.quote(str(Path(image).resolve()))}\n")
            file.write(f"duration {duration:.6f}\n")
        # concat demuxer applies the final duration only when another file
        # follows it, so repeat the last image without adding extra duration.
        file.write(f"file {shlex.quote(str(Path(slides[-1][0]).resolve()))}\n")
    return concat_path


def _build_timeline(quiz, subject=None):
    slides = []
    narration_events = []
    tick_events = []
    correct_events = []
    timeline = 0.0
    countdown_step = COUNTDOWN_SECONDS / 3.0

    # Generate missing narration files concurrently before building the timeline.
    audio_paths = ensure_question_audio_batch(quiz)

    for index, question in enumerate(quiz):
        # Countdown: exactly three seconds total.
        for timer in (3, 2, 1):
            slides.append((OUTPUT_DIR / f"slide_{index}_{timer}.jpg", countdown_step))
            tick_events.append(timeline)
            timeline += countdown_step

        audio_path = audio_paths[index]
        narration_duration = _ffprobe_duration(audio_path)
        narration_start = timeline
        narration_events.append((audio_path, narration_start))

        # The question stays visible until narration ends, then remains for
        # exactly three more seconds. No audio is sped up or stretched.
        slides.append((OUTPUT_DIR / f"question_{index}.jpg", narration_duration + POST_AUDIO_WAIT_SECONDS))
        timeline += narration_duration + POST_AUDIO_WAIT_SECONDS

        answer_path = OUTPUT_DIR / f"answer_{index}.jpg"
        slides.append((answer_path, ANSWER_SLIDE_DURATION))
        correct_events.append(timeline)
        timeline += ANSWER_SLIDE_DURATION

    return slides, narration_events, tick_events, correct_events, timeline


def _make_video(slides, duration):
    concat = _write_concat_file(slides)
    silent = OUTPUT_DIR / "video_silent.mp4"
    _run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", str(concat),
        "-r", str(FPS),
        "-c:v", "libx264", "-preset", VIDEO_PRESET, "-tune", "stillimage", "-crf", str(VIDEO_CRF),
        "-pix_fmt", "yuv420p", "-an",
        str(silent),
    ])
    return silent


def _make_audio(duration, narration_events, tick_events, correct_events):
    """Build one mixed audio track without opening tick/correct files once per event."""
    inputs = []
    filters = []
    mix_labels = []
    input_index = 0

    if BACKGROUND_AUDIO.is_file():
        inputs += ["-stream_loop", "-1", "-i", str(BACKGROUND_AUDIO)]
        filters.append(f"[0:a]volume={BACKGROUND_VOLUME},atrim=duration={duration:.6f}[bg]")
        mix_labels.append("[bg]")
        input_index = 1

    for path, start in narration_events:
        inputs += ["-i", str(path)]
        label = f"n{input_index}"
        delay = int(round(start * 1000))
        filters.append(f"[{input_index}:a]adelay={delay}|{delay},volume=1[{label}]")
        mix_labels.append(f"[{label}]")
        input_index += 1

    def add_event_track(source, events, volume, prefix):
        nonlocal input_index
        if not events or not source.is_file():
            return

        source_index = input_index
        inputs.extend(["-i", str(source)])
        input_index += 1

        branches = [f"{prefix}{i}" for i in range(len(events))]
        split_outputs = "".join(f"[{name}]" for name in branches)
        filters.append(f"[{source_index}:a]asplit={len(events)}{split_outputs}")

        delayed = []
        for i, start in enumerate(events):
            label = f"{prefix}d{i}"
            delay = int(round(start * 1000))
            filters.append(
                f"[{prefix}{i}]adelay={delay}|{delay},volume={volume}[{label}]"
            )
            delayed.append(f"[{label}]")

        track_label = f"{prefix}track"
        filters.append(
            "".join(delayed)
            + f"amix=inputs={len(delayed)}:duration=longest:dropout_transition=0[{track_label}]"
        )
        mix_labels.append(f"[{track_label}]")

    add_event_track(TICK_AUDIO, tick_events, TICK_VOLUME, "t")
    add_event_track(CORRECT_AUDIO, correct_events, CORRECT_VOLUME, "c")

    if not mix_labels:
        return None

    filters.append(
        "".join(mix_labels)
        + f"amix=inputs={len(mix_labels)}:duration=longest:dropout_transition=0,"
        f"atrim=duration={duration:.6f},asetpts=N/SR/TB[mix]"
    )

    audio_file = OUTPUT_DIR / "audio_mix.m4a"
    _run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        *inputs,
        "-filter_complex", ";".join(filters),
        "-map", "[mix]", "-t", f"{duration:.6f}",
        "-c:a", "aac", "-b:a", "192k", str(audio_file),
    ])
    return audio_file


def create_video(quiz, output_file, subject=None):
    if not quiz:
        raise ValueError("quiz is empty")

    output_file = Path(output_file)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("🎬 Building exact audio-driven timeline...")
    slides, narration_events, tick_events, correct_events, duration = _build_timeline(quiz, subject=subject)
    print(f"⏱️ Planned duration: {duration:.2f}s")

    silent_video = _make_video(slides, duration)
    audio_file = _make_audio(duration, narration_events, tick_events, correct_events)

    if audio_file:
        _run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(silent_video), "-i", str(audio_file),
            "-map", "0:v:0", "-map", "1:a:0", "-sn", "-c:v", "copy", "-c:a", "copy",
            "-movflags", "+faststart", "-shortest", str(output_file),
        ])
    else:
        silent_video.replace(output_file)

    print(f"✅ Video created: {output_file} ({duration:.2f}s)")
    return str(output_file)
