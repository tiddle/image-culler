# Image Culler

> ## This is AI slop
>
> **Read this before you trust a single line below.** This entire project (the
> code, the tests, this README, all of it) was written by an AI agent with
> minimal human review. It has **never been run end to end against a real photo
> library**. Nobody has verified that the blur, exposure, or blink detection
> actually make good keep/reject decisions on real shoots. The claims in this
> document are what the AI *intended* to build, not independently confirmed
> behaviour.
>
> **If you point this at photos you care about:**
> - Back them up first. Always.
> - Use the default (non-destructive) copy mode. Do not use "Move rejects" on
>   originals you cannot afford to lose.
> - Verify the results yourself. "An AI said it works" is not a safety
>   guarantee, and this one has not even been tested.
>
> You have been warned. This is a toy / experiment, not production software.

A standalone Windows app for commercial photographers: point it at a folder of
photos, and it copies the keepers into a `selects/` subfolder, leaving the
sub-optimal shots (over/under-exposed, blurry, blinking) behind. Non-destructive
by default: the originals are never moved or deleted (unless you explicitly pick
the "Move rejects" mode).

## Status

**v0.6.0 — exposure + blur + blink + burst grouping + unified output modes.**
Point it at a folder; it scores every top-level image, collapses near-duplicate
bursts down to a single best keeper, and delivers the cull one of four ways
(copy to `selects/`, XMP sidecars, both, or move rejects out). It always writes
`report.csv` auditing every frame. Scoring runs across CPU cores
(`multiprocessing`) with a serial fallback. Tuning is aggressive on purpose
(commercial use, false positives are acceptable).

Again: none of this has been validated on a real shoot. See the AI slop warning
above.

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

## Output modes

Pick exactly one output mode in the window (they are mutually exclusive):

- **Copy keepers to `selects/`** (default, non-destructive) — copies keepers
  into a `selects/` subfolder. Originals are untouched.
- **XMP sidecars** — writes a sibling `.xmp` next to each RAW carrying the verdict
  as `xmp:Rating` + colour `xmp:Label` (Green keep / Red reject / Yellow
  duplicate) plus `Culled:*` keywords, so you filter the cull inside Lightroom or
  Capture One. JPEG keepers still fall back to a `selects/` copy, since LR only
  reads sidecars for RAW. Existing sidecars are *merged*, never clobbered: your
  own ratings and keywords are preserved, and an unreadable sidecar is skipped and
  reported rather than overwritten.
- **Both** — copies keepers *and* writes RAW sidecars.
- **Move rejects to `rejected/`** (destructive) — physically moves every
  non-keeper (quality rejects and collapsed burst duplicates alike) out of the
  source folder into a `rejected/` subfolder, sorting the folder in place.
  Keepers stay put and get no `selects/` copy. This one *moves your originals*,
  so back up first and be sure before you run it.

In Lightroom you may need *Metadata ▸ Read Metadata from File* (or "automatically
write/read XMP" enabled) for sidecars to register.

## Roadmap

- **Phase 0** — Tkinter window, folder picker, progress bar, copy-through. *Done.*
- **Phase 1** — exposure + blur via OpenCV; keepers only; `report.csv`. *Done.*
- **Phase 2** — blink / closed-eye detection (MediaPipe Face Landmarker, eye
  aspect ratio). *Done.*
- **Phase 3** — package a single-file Windows `.exe` via PyInstaller (bundles
  the `.task` model + MediaPipe runtime). *Done* (GitHub Actions builds it).
  Threshold tuning on a real shoot still pending.
- **Phase 4** — burst / near-duplicate grouping; keep the best frame of each
  burst. *Done.*
- **Phase 5** — Lightroom / Capture One XMP sidecar output. *Done.*
- **Phase 5.6** — unify delivery into a single mutually-exclusive output mode
  (`copy` / `sidecar` / `both` / `move`). *Done (v0.6.0).*

Note the "Done" markers describe what was coded, not what has been proven to work
on real photos. See the AI slop warning.

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

`.github/workflows/release.yml` builds the exe on a Windows runner. Bump the
version in `image_culler/__init__.py`, then push a matching version tag to
publish a GitHub Release with the exe attached:

```bash
git tag v0.6.1 && git push origin v0.6.1
```

Or run the **Build & Release** workflow manually (`workflow_dispatch`) to get the
exe as a downloadable build artifact without cutting a release.

Reminder: the CI only proves the exe *builds and packages*. It does not run
detection on real photos. Nothing here is validated.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```
