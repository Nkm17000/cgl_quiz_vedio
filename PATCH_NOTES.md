# Instagram Quiz Publishing Behavior

- Manual `workflow_dispatch` or a normal `push`: exactly 1 quiz video.
- Scheduled workflow: exactly 6 videos per run when the 6 JSON sources are present: English, General Science, GK, Math, Reasoning, and Mixed.
- Each source produces one 5-question quiz per scheduled run.
- Source counters advance only after successful Instagram publishing.
- If Meta returns the Content Publishing API media-creation limit, the run stops immediately and saves a 24-hour cooldown; the generated MP4 is retained.
- Scheduled runs continue to the next subject when a non-limit source error occurs.
- Quiz counters are committed with `if: always()` so successful uploads earlier in a partially failed run are not lost.
