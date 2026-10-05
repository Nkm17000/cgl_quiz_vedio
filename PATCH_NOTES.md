# Quiz Subject Patch

Added:
- COMPUTER SCIENCE from `computer_science_10000_bilingual_ssc_cgl_reshuffled.json`
- RAJASTHAN GK from `rajasthan_gk_10000_bilingual_ssc_cgl_reshuffled.json`

Code changes:
- Explicit subject detection for both new sources.
- `rajasthan_gk` is matched before generic `gk` so it is not classified as GK.
- Manual/push runs explicitly select ENGLISH, preserving existing behavior after adding the new source.
- Scheduled runs automatically process all discovered JSON sources, so the two new subjects are included without another hard-coded list.
