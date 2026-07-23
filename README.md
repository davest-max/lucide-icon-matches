# icon-lucide-match

Matches custom "ccf" icons used in the Agent Workspace app to their closest [Lucide](https://lucide.dev) equivalents, so we can move to a standard icon set. Produced for AW-60964.

## What's in here

- **`worksheet/`** — the interactive review worksheet (`index.html`). Open it directly in a browser (no server needed). Every icon has a suggested Lucide match, a confidence tier (High/Medium/Low/No match), and controls to override either one.
- **`scripts/`** — the Python pipeline that generates the worksheet:
  - `repair_and_render.py` — repairs malformed source SVGs and renders them to PNG
  - `build_lucide_masks.py` / `build_lucide_index.py` — precompute Lucide icon shape masks and name/tag indexes used for matching
  - `match_icons.py` — the matching engine (name/tag scoring + visual shape similarity) — outputs `match_results.json`
  - `fill_worksheet.py` — builds the final `worksheet/index.html` from the match results
- **`exports/`** — drop zone for exports downloaded from the worksheet (see workflow below). Empty until someone exports.

## Review workflow

1. Open `worksheet/index.html` in a browser.
2. Use the confidence filter chips (High/Medium/Low) to focus your review.
3. For any icon, use "Search Lucide icons…" to pick a different match, or the confidence dropdown to override the tier. Changes are saved in your browser only.
4. When done (or periodically, so you don't lose work), click **Download CSV for devs** and/or **Download updated worksheet (.html)**.
5. Drop the downloaded file(s) into `exports/` with a dated filename (e.g. `exports/2026-07-23_matches.csv`), commit, and push. This is what devs should reference — it reflects the current reviewed/overridden state, not just the raw algorithmic suggestions.

## Regenerating the worksheet

Only needed if the source icon set or Lucide's icon set changes:

```
python3 scripts/build_lucide_masks.py    # rebuild Lucide shape masks
python3 scripts/build_lucide_index.py    # rebuild Lucide name/tag index
python3 scripts/match_icons.py           # re-run matching -> match_results.json
python3 scripts/fill_worksheet.py        # rebuild worksheet/index.html
```

Requires the original source icon SVGs (`wrapper-icons/`, `inline-svgs/`) and a local copy of `lucide-static` icons — not included here to keep the repo lean; ask in the team channel if you need to regenerate from scratch.

## Notes on confidence tiers

- **High** — strong name/tag match, or strong name match + strong visual match.
- **Medium** — moderate name or visual signal.
- **Low** — weak signal either way; check carefully.
- **No match** — likely a custom brand mark or concept with no Lucide equivalent (flagged, not forced).

Visual similarity is shape-based (silhouette overlap) and has known blind spots: icons that are rotated or differ mainly in stroke thickness relative to their Lucide counterpart can score lower than they should. Always eyeball Low-tier and No-match icons rather than trusting the score alone.
