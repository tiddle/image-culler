# Image Culler

A standalone Windows app for commercial photographers: point it at a folder of
photos, and it copies the keepers into a `selects/` subfolder, leaving the
sub-optimal shots (over/under-exposed, blurry, blinking) behind. Non-destructive
by design: the originals are never moved or deleted.

## Status

**Phase 1 — exposure + blur detection.** Point it at a folder; it scores every
top-level image for exposure (mean luminance + highlight/shadow clipping) and
blur (variance of the Laplacian), copies the keepers into `selects/`, and writes
`report.csv` auditing every frame. Scoring runs across CPU cores
(`multiprocessing`) with a serial fallback. Tuning is aggressive on purpose
(commercial use, false positives are acceptable). Blink / closed-eye detection
is Phase 2.

## What gets flagged

| Reason | How it's measured |
|--------|-------------------|
| `underexposed` / `overexposed` | mean luminance outside `[40, 220]` |
| `blown-highlights` | >20% of pixels at the ceiling (≥250) |
| `crushed-shadows` | >45% of pixels at the floor (≤5) |
| `blurry` | Laplacian variance below 100 (measured at a fixed 1024px long edge) |

Anything that can't be decoded is **kept**, never dropped. Thresholds live in
`image_culler/detect.py` (`Thresholds`).

## Roadmap

- **Phase 0** — Tkinter window, folder picker, progress bar, copy-through. *Done.*
- **Phase 1** — exposure + blur via OpenCV; keepers only; `report.csv`. *Done.*
- **Phase 2** — blink / closed-eye detection (MediaPipe Face Mesh, eye aspect
  ratio).
- **Phase 3** — threshold tuning on a real shoot; package a single-file Windows
  `.exe` via PyInstaller.

## Run from source

```bash
python -m image_culler
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```
