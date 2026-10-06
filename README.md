# Smart Learning Lab — Instagram Quiz Reel Generator

Generates and publishes **10 subject Instagram Reels per scheduled workflow run**, with exactly **10 questions per Reel**, containing exactly **10 questions**.

## Pipeline

```text
10 independent subject JSON question banks
        ↓
10-question subject selector
        ↓
Shuffle
        ↓
Pillow slides
        ↓
TTS narration
        ↓
FFmpeg MP4
        ↓
Temporary public GitHub Release asset
        ↓
Instagram Graph API video_url
        ↓
Instagram processing check
        ↓
Instagram media_publish
        ↓
Commit source counter
```

## Instagram upload implementation

The Instagram publishing flow now follows the working DIVINE_INDIA implementation:

1. Generate the local MP4.
2. Upload it to a temporary public GitHub Release.
3. Build the public release download URL.
4. Create an Instagram `REELS` media container using `video_url`.
5. Wait until Meta reports `FINISHED`.
6. Call `media_publish`.
7. Delete the temporary GitHub Release.
8. Commit the question counter only after successful publication.

The old direct/resumable binary Instagram upload has been removed.

## GitHub Secrets

Required:

- `INSTAGRAM_BUSINESS_ACCOUNT_ID`
- `INSTAGRAM_ACCESS_TOKEN`

Optional:

- `PAGE_URL`

The repository must be **public** because Instagram needs to download the MP4 from the public GitHub Release URL.

## Run frequency

The workflow supports:

- Manual `workflow_dispatch`
- Push to `main`
- Scheduled runs at 02:00, 08:00, 14:00 and 20:00 UTC

Scheduled runs generate one video per subject (10 subject videos total), with exactly 10 questions per video. Instagram publishing is performed one video at a time.

## Local test

```bash
python app.py
```

For local Instagram publishing, set `PUBLIC_VIDEO_URL` to a publicly reachable MP4 URL and run through the normal pipeline, or use the workflow's GitHub Release flow.
