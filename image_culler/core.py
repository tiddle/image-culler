"""Core IO + orchestration for the image culler.

Phase 1: enumerate the top level of a folder, score each image for exposure and
blur, copy only the keepers into ``selects/``, and write ``report.csv`` so the
cull can be audited. Nothing is moved or deleted; rejects stay in the original
folder.
"""

from __future__ import annotations

import csv
import os
import shutil
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Iterable

if TYPE_CHECKING:
    from .detect import ImageVerdict, Thresholds

# Extensions we treat as images. Lower-cased; matching is case-insensitive.
# RAW formats are included so detection can decode them via rawpy.
_RASTER_EXTENSIONS = frozenset(
    {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp", ".heic"}
)
_RAW_EXTENSIONS = frozenset(
    {
        ".cr2", ".cr3", ".nef", ".arw", ".raf", ".orf", ".rw2",
        ".dng", ".pef", ".srw", ".raw", ".nrw", ".sr2",
    }
)
IMAGE_EXTENSIONS = _RASTER_EXTENSIONS | _RAW_EXTENSIONS

SELECTS_DIRNAME = "selects"
REPORT_FILENAME = "report.csv"

# Called after each image with (done, total, current_path).
ProgressCallback = Callable[[int, int, Path], None]


@dataclass(frozen=True)
class CullSummary:
    total: int
    kept: int
    rejected: int
    report_path: Path | None
    blink_used: bool = True  # False if blink detection was requested but unavailable


def find_images(folder: Path) -> list[Path]:
    """Return image files in the top level of ``folder``, sorted by name.

    Non-recursive by design (Carlo, 2026-06-24): only the top level of the
    chosen folder is scanned. The ``selects/`` output dir, if present, is
    skipped so re-runs do not fold prior outputs back into the input.
    """
    folder = Path(folder)
    if not folder.is_dir():
        raise NotADirectoryError(f"Not a folder: {folder}")

    images = [
        entry
        for entry in folder.iterdir()
        if entry.is_file()
        and entry.suffix.lower() in IMAGE_EXTENSIONS
        and entry.parent.name != SELECTS_DIRNAME
    ]
    return sorted(images, key=lambda p: p.name.lower())


def copy_to_selects(images: Iterable[Path], dest: Path) -> int:
    """Copy each image into ``dest`` (created if needed). Returns the count.

    ``shutil.copy2`` preserves timestamps/metadata.
    """
    images = list(images)
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    for image in images:
        shutil.copy2(image, dest / image.name)
    return len(images)


def write_report(report_path: Path, verdicts: Iterable[ImageVerdict]) -> None:
    """Write a per-image CSV audit of the cull."""
    with open(report_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "file", "verdict", "reason", "brightness",
                "clip_high", "clip_low", "blur_var", "faces", "min_ear",
            ]
        )
        for v in verdicts:
            writer.writerow(
                [
                    v.path.name,
                    "keep" if v.keep else "reject",
                    v.reason_text,
                    f"{v.brightness:.1f}",
                    f"{v.clip_high:.4f}",
                    f"{v.clip_low:.4f}",
                    f"{v.blur_var:.1f}",
                    v.faces,
                    "" if v.min_ear == float("inf") else f"{v.min_ear:.3f}",
                ]
            )


def _iter_verdicts(images, thresholds, workers):
    """Yield ImageVerdicts in input order, parallelising when worthwhile.

    Falls back to a serial scan if a process pool cannot be created (e.g. a
    locked-down environment), so the cull always completes.
    """
    from .detect import analyze_image  # local import keeps cv2 off the IO path

    scorer = partial(analyze_image, thresholds=thresholds)
    if workers <= 1 or len(images) <= 1:
        yield from (scorer(image) for image in images)
        return

    try:
        from concurrent.futures import ProcessPoolExecutor

        with ProcessPoolExecutor(max_workers=workers) as pool:
            # map preserves input order; chunksize amortises IPC over many files.
            yield from pool.map(scorer, images, chunksize=8)
    except Exception:  # noqa: BLE001 - any pool failure -> finish serially
        yield from (scorer(image) for image in images)


def process_folder(
    folder: Path,
    on_progress: ProgressCallback | None = None,
    thresholds: Thresholds | None = None,
    workers: int | None = None,
) -> CullSummary:
    """Phase 1 pipeline: score every top-level image, copy keepers to ``selects/``.

    Writes ``report.csv`` next to ``selects/``. Returns a :class:`CullSummary`.
    ``workers`` defaults to the CPU count; pass 1 to force a serial scan.
    """
    folder = Path(folder)
    images = find_images(folder)
    total = len(images)
    if total == 0:
        return CullSummary(0, 0, 0, None)

    if workers is None:
        workers = os.cpu_count() or 1

    check_blink = thresholds.check_blink if thresholds is not None else True
    blink_used = True
    if check_blink:
        from .blink import blink_available

        blink_used = blink_available()

    dest = folder / SELECTS_DIRNAME
    dest.mkdir(parents=True, exist_ok=True)

    verdicts: list[ImageVerdict] = []
    kept = 0
    for index, verdict in enumerate(_iter_verdicts(images, thresholds, workers), start=1):
        if verdict.keep:
            shutil.copy2(verdict.path, dest / verdict.path.name)
            kept += 1
        verdicts.append(verdict)
        if on_progress is not None:
            on_progress(index, total, verdict.path)

    report_path = folder / REPORT_FILENAME
    write_report(report_path, verdicts)
    return CullSummary(
        total=total,
        kept=kept,
        rejected=total - kept,
        report_path=report_path,
        blink_used=blink_used,
    )
