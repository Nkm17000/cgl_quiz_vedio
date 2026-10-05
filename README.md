# Smart Learning Lab — Instagram Quiz Reel Generator

Instagram-only quiz Reel generation pipeline for Smart Learning Lab.

## Current test scope

This version intentionally runs **one mixed quiz of exactly 5 questions per workflow run**.
It uses only:

`assets/quiz_data/smart_learning_lab_50000_mixed_questions.json`

Questions are selected from a persistent source counter and shuffled inside the 5-question quiz.
The counter advances only after the Instagram Reel is successfully published.

## Pipeline

```text
Mixed JSON question bank
        ↓
5-question selector
        ↓
Shuffle
        ↓
Pillow slides
        ↓
TTS narration
        ↓
FFmpeg MP4
        ↓
720x1280 Reel validation
        ↓
Instagram resumable Reel upload
        ↓
Instagram processing check
        ↓
Instagram publish
        ↓
Commit source counter
```

## GitHub Secrets

Required:

- `INSTAGRAM_BUSINESS_ACCOUNT_ID`
- `INSTAGRAM_ACCESS_TOKEN`

Optional:

- `PAGE_URL`

The workflow uses `META_GRAPH_VERSION=v23.0`.

## Important Instagram validation fix

The account preflight requests only `id,username`.
It does **not** request `account_type`, because that field can produce Meta Graph API error `#100` for this account endpoint.

## Schedule

The workflow runs at 02:00, 08:00, 14:00 and 20:00 UTC and also supports manual runs and pushes to `main`.

## Old Facebook code

Facebook publishing is no longer part of the active pipeline. Delete `services/facebook_service.py` from the repository if it is still present from the previous version.
