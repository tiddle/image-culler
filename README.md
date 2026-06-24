# Image Culler

A standalone Windows app for commercial photographers: point it at a folder of
photos, and it copies the keepers into a `selects/` subfolder, leaving the
sub-optimal shots (over/under-exposed, blurry, blinking) behind. Non-destructive
by design: the originals are never moved or deleted.

## Status

**Phase 2 — exposure + blur + blink detection.** Point it at a folder; it scores
every top-level image, copies the keepers into `selects/`, and writes
`report.csv` auditing every frame. Scoring runs across CPU cores
(`multiprocessing`) with a serial fallback. Tuning is aggressive on purpose
(commercial use, false positives are acceptable).

## What gets flagged

| Reason | How it's measured |
|--------|-------------------|
| `underexposed` / `overexposed` | mean luminance outside `[40, 220]` |
| `blown-highlights` | >20% of pixels at the ceiling (≥250) |
| `crushed-shadows` | >45% of pixels at the floor (≤5) |
| `blurry` | Laplacian variance below 100 (measured at a fixed 1024px long edge) |
| `eyes-closed` | any face with an eye-aspect-ratio below 0.18 (MediaPipe Face Landmarker) |

Blink detection only runs on frames that pass exposure and blur, since the
expensive face pass is wasted on a frame that is already rejected. Anything that
can't be decoded is **kept**, never dropped, and if the MediaPipe runtime can't
load, the blink check is skipped (reported, never silently disabled). Thresholds
live in `image_culler/detect.py` (`Thresholds`).

The Face Landmarker model ships in `image_culler/assets/face_landmarker.task`.

## Roadmap

- **Phase 0** — Tkinter window, folder picker, progress bar, copy-through. *Done.*
- **Phase 1** — exposure + blur via OpenCV; keepers only; `report.csv`. *Done.*
- **Phase 2** — blink / closed-eye detection (MediaPipe Face Landmarker, eye
  aspect ratio). *Done.*
- **Phase 3** — threshold tuning on a real shoot; package a single-file Windows
  `.exe` via PyInstaller (bundle the `.task` model).

## Run from source

```bash
python -m image_culler
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```
