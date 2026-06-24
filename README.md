# Image Culler

A standalone Windows app for commercial photographers: point it at a folder of
photos, and it copies the keepers into a `selects/` subfolder, leaving the
sub-optimal shots (over/under-exposed, blurry, blinking) behind. Non-destructive
by design: the originals are never moved or deleted.

## Status

**Phase 0 — scaffold + GUI shell + IO loop.** The window, folder picker,
progress bar, and copy-through pipeline are in place. No defect detection yet:
Start currently copies *every* image into `selects/`. This proves the UX and IO
end to end before detection lands.

## Roadmap

- **Phase 0** (this) — Tkinter window, folder picker, progress bar, copy-through.
- **Phase 1** — exposure (luminance histogram / clipping) + blur (variance of
  Laplacian) via OpenCV; only keepers copied; `report.csv` written.
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
