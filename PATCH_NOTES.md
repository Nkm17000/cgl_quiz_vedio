# Instagram Quiz Publishing Behavior

- The project has 10 independent subject question banks: English, General Science, GK, Math, Reasoning, History, Geography, Polity, Computer Science, and Rajasthan GK.
- Every question bank is physically shuffled and contains its own independent sequence.
- Each generated quiz contains exactly 10 questions.
- Generation runs all 10 subjects in parallel with a maximum of 5 jobs at once.
- Instagram publishing is limited to one video at a time.
- Source counters advance only after successful Instagram publishing.
- If some Instagram publishers fail, only successfully published subjects advance their counters/history.
- The old mixed History/Geography/Polity JSON is no longer used.
- The Instagram publishing flow uses a temporary public GitHub Release asset as the Reel `video_url`.
