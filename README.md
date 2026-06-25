# Image Culler

A standalone Windows app for commercial photographers: point it at a folder of
photos, and it copies the keepers into a `selects/` subfolder, leaving the
sub-optimal shots (over/under-exposed, blurry, blinking) behind. Non-destructive
by design: the originals are never moved or deleted.

## Status

**Phase 5 — exposure + blur + blink + burst grouping + XMP sidecar output.**
Point it at a folder; it scores every top-level image, collapses near-duplicate
bursts down to a single best keeper, and either copies the keepers into
`selects/` or writes XMP sidecars that Lightroom / Capture One read. It always
writes `report.csv` auditing every frame. Scoring runs across CPU cores
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

## Burst grouping

Cameras shooting continuous bursts produce many near-identical frames. The culler
walks frames in capture order (EXIF `DateTimeOriginal`, falling back to filename
order) and joins adjacent frames into a burst when they are both close in time
*and* visually similar (a perceptual-hash check). It keeps the single best frame
of each burst (sharpest, then best-exposed, then eyes-most-open) and marks the
rest `duplicate`. RAW+JPEG pairs of the same shot are treated as one capture and
never split. `report.csv` records the `group_id` and `group_rank` of every frame.
Turn it off with the **Group bursts** checkbox.

## Output: `selects/` copy or XMP sidecars

Three output modes (chosen in the window):

- **Copy to `selects/`** (default) — copies keepers into a `selects/` subfolder.
- **XMP sidecars** — writes a sibling `.xmp` next to each RAW carrying the verdict
  as `xmp:Rating` + colour `xmp:Label` (Green keep / Red reject / Yellow
  duplicate) plus `Culled:*` keywords, so you filter the cull inside Lightroom or
  Capture One. JPEG keepers still fall back to a `selects/` copy, since LR only
  reads sidecars for RAW. Existing sidecars are *merged*, never clobbered: your
  own ratings and keywords are preserved, and an unreadable sidecar is skipped and
  reported rather than overwritten.
- **Both** — copies keepers *and* writes RAW sidecars.

In Lightroom you may need *Metadata ▸ Read Metadata from File* (or "automatically
write/read XMP" enabled) for sidecars to register.

## Roadmap

- **Phase 0** — Tkinter window, folder picker, progress bar, copy-through. *Done.*
- **Phase 1** — exposure + blur via OpenCV; keepers only; `report.csv`. *Done.*
- **Phase 2** — blink / closed-eye detection (MediaPipe Face Landmarker, eye
  aspect ratio). *Done.*
- **Phase 3** — package a single-file Windows `.exe` via PyInstaller (bundles
  the `.task` model + MediaPipe runtime). *Build setup done* (`image-culler.spec`,
  `build_windows.ps1`); run it on Windows to produce `dist\ImageCuller.exe`.
  Threshold tuning on a real shoot still pending.
- **Phase 4** — burst / near-duplicate grouping; keep the best frame of each
  burst. *Done.*
- **Phase 5** — Lightroom / Capture One XMP sidecar output with a `copy` /
  `sidecar` / `both` toggle. *Done.*

## Run from source

```bash
python -m image_culler
```

## Build a single-file Windows `.exe`

PyInstaller is not a cross-compiler, so the `.exe` must be built **on Windows**.
From the repo root:

```powershell
powershell -ExecutionPolicy Bypass -File build_windows.ps1
```

Or manually:

```powershell
pip install -r requirements.txt -r requirements-build.txt
pyinstaller image-culler.spec
```

The result is `dist\ImageCuller.exe`: self-contained (no Python install needed),
with the Face Landmarker model and MediaPipe's runtime data bundled inside. The
spec (`image-culler.spec`) collects `mediapipe`'s graph configs and native libs
in addition to our `assets/face_landmarker.task`.

### …or let GitHub Actions build it

`.github/workflows/release.yml` builds the exe on a Windows runner. Push a
version tag to publish a GitHub Release with the exe attached:

```bash
git tag v0.3.0 && git push origin v0.3.0
```

Or run the **Build & Release** workflow manually (`workflow_dispatch`) to get the
exe as a downloadable build artifact without cutting a release.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```
