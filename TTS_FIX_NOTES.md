# TTS fallback fix

This full-project package preserves the existing quiz/video/publishing code and updates only the narration/dependency/workflow setup.

Narration order:
1. Edge TTS with bounded retry.
2. gTTS if Edge TTS fails.
3. Local espeak-ng + FFmpeg if gTTS also fails.

The GitHub Actions generation job installs `espeak-ng` and `ffmpeg`, while `requirements.txt` includes `gTTS`. Edge TTS can still return 403 due to upstream Microsoft endpoint restrictions; the fallback chain is designed to keep narration working where at least one provider is available.

Environment options:
- `TTS_EDGE_RETRIES=1`
- `TTS_EDGE_TIMEOUT=30`
- `TTS_FALLBACK=gtts` (`gtts`, `auto`, or `both`)
- `TTS_FALLBACK_LANGUAGE=en` (set `hi` for Hindi gTTS)
- `ESPEAK_VOICE=en` (use an installed espeak voice)

Existing question audio files are reused via the original content-hash cache. The source question selection, video rendering, timing, and publishing services are otherwise preserved.
