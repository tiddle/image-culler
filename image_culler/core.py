"""Core IO logic for the image culler.

Phase 0: pure enumerate + copy-through. No defect detection yet — every image
in the chosen folder is copied into ``selects/`` so the GUI and IO loop can be
proven end to end. Filtering arrives in Phase 1.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable, Iterable

# Extensions we treat as images. Lower-cased; matching is case-insensitive.
# RAW formats are included now so Phase 1 detection can decode them later.
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

ProgressCallback = Callable[[int, int, Path], None]


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
        if entry.is_file() and entry.suffix.lower() in IMAGE_EXTENSIONS
    ]
    return sorted(images, key=lambda p: p.name.lower())


def copy_to_selects(
    images: Iterable[Path],
    dest: Path,
    on_progress: ProgressCallback | None = None,
) -> int:
    """Copy each image into ``dest``, creating it if needed. Returns the count.

    ``shutil.copy2`` preserves timestamps/metadata. ``on_progress`` is called
    after each copy with ``(done, total, current_path)`` so a GUI can render a
    progress bar.
    """
    images = list(images)
    total = len(images)
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)

    for index, image in enumerate(images, start=1):
        shutil.copy2(image, dest / image.name)
        if on_progress is not None:
            on_progress(index, total, image)
    return total


def process_folder(
    folder: Path,
    on_progress: ProgressCallback | None = None,
) -> int:
    """Phase 0 pipeline: enumerate top-level images, copy all into ``selects/``.

    Returns the number of images copied. ``selects/`` is created inside the
    chosen folder.
    """
    folder = Path(folder)
    images = find_images(folder)
    dest = folder / SELECTS_DIRNAME
    return copy_to_selects(images, dest, on_progress)
