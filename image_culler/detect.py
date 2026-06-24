"""Phase 1 defect detection: exposure + blur.

Pure pixel math via OpenCV/numpy, fast enough to run over thousands of frames.
Tuning is deliberately aggressive (commercial use, false positives are fine per
Carlo, 2026-06-24): we would rather flag a borderline-good frame than let a
technically-bad one through. Nothing is ever deleted, so over-culling is
recoverable from the original folder.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .core import _RAW_EXTENSIONS

# Long edge (px) the image is scaled to before metrics. Fixes the Laplacian
# variance scale so the blur threshold means the same thing for a phone JPEG and
# a 50MP RAW, and keeps the per-image cost bounded.
_ANALYSIS_LONG_EDGE = 1024


@dataclass(frozen=True)
class Thresholds:
    """Reject thresholds. Defaults tuned aggressively for commercial culling."""

    min_brightness: float = 40.0      # mean luma below this -> underexposed
    max_brightness: float = 220.0     # mean luma above this -> overexposed
    max_clip_high: float = 0.20       # >20% pixels at ceiling -> blown highlights
    max_clip_low: float = 0.45        # >45% pixels at floor   -> crushed shadows
    min_blur_var: float = 100.0       # Laplacian variance below this -> blurry
    ear_closed: float = 0.18          # eye-aspect-ratio below this -> closed eye
    check_blink: bool = True          # run MediaPipe blink detection


@dataclass(frozen=True)
class ImageVerdict:
    path: Path
    keep: bool
    reasons: tuple[str, ...]
    brightness: float
    clip_high: float
    clip_low: float
    blur_var: float
    faces: int = 0
    min_ear: float = math.inf

    @property
    def reason_text(self) -> str:
        return "; ".join(self.reasons) if self.reasons else "ok"


def load_image(path: Path) -> np.ndarray | None:
    """Load any supported image as a BGR uint8 array, or ``None`` if undecodable.

    RAW files are decoded via rawpy: the embedded full-size preview is used when
    present (fast), falling back to a full libraw develop. If rawpy is missing or
    the file cannot be read, returns ``None`` so the caller can keep the frame
    rather than risk dropping something it could not judge.
    """
    path = Path(path)
    if path.suffix.lower() in _RAW_EXTENSIONS:
        return _load_raw(path)

    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    return image if image is not None and image.size else None


def _load_raw(path: Path) -> np.ndarray | None:
    try:
        import rawpy
    except ImportError:
        return None

    try:
        with rawpy.imread(str(path)) as raw:
            try:
                thumb = raw.extract_thumb()
            except (rawpy.LibRawNoThumbnailError, rawpy.LibRawUnsupportedThumbnailError):
                thumb = None
            if thumb is not None and thumb.format == rawpy.ThumbFormat.JPEG:
                buffer = np.frombuffer(thumb.data, dtype=np.uint8)
                decoded = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
                if decoded is not None and decoded.size:
                    return decoded
            if thumb is not None and thumb.format == rawpy.ThumbFormat.BITMAP:
                return cv2.cvtColor(thumb.data, cv2.COLOR_RGB2BGR)
            rgb = raw.postprocess()
            return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    except Exception:  # noqa: BLE001 - any decode failure means "can't judge"
        return None


def _resize_for_analysis(image: np.ndarray) -> np.ndarray:
    height, width = image.shape[:2]
    longest = max(height, width)
    if longest <= _ANALYSIS_LONG_EDGE:
        return image
    scale = _ANALYSIS_LONG_EDGE / longest
    return cv2.resize(
        image,
        (max(1, round(width * scale)), max(1, round(height * scale))),
        interpolation=cv2.INTER_AREA,
    )


def analyze_image(
    path: Path, thresholds: Thresholds | None = None
) -> ImageVerdict:
    """Score one image for exposure and blur and decide keep vs reject."""
    thresholds = thresholds or Thresholds()
    path = Path(path)

    image = load_image(path)
    if image is None:
        # Could not decode -> keep it; never drop a frame we cannot judge.
        return ImageVerdict(path, True, ("undecodable",), 0.0, 0.0, 0.0, 0.0)

    bgr = _resize_for_analysis(image)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    brightness = float(gray.mean())
    total = gray.size
    clip_high = float(np.count_nonzero(gray >= 250) / total)
    clip_low = float(np.count_nonzero(gray <= 5) / total)
    blur_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())

    reasons: list[str] = []
    if brightness < thresholds.min_brightness:
        reasons.append("underexposed")
    if brightness > thresholds.max_brightness:
        reasons.append("overexposed")
    if clip_high > thresholds.max_clip_high:
        reasons.append("blown-highlights")
    if clip_low > thresholds.max_clip_low:
        reasons.append("crushed-shadows")
    if blur_var < thresholds.min_blur_var:
        reasons.append("blurry")

    # Blink detection is the expensive stage; only run it on frames that would
    # otherwise be keepers, since an already-rejected frame stays rejected.
    faces = 0
    min_ear = math.inf
    if thresholds.check_blink and not reasons:
        from .blink import detect_closed_eyes

        blink = detect_closed_eyes(bgr, thresholds.ear_closed)
        faces = blink.faces
        min_ear = blink.min_ear
        if blink.any_closed:
            reasons.append("eyes-closed")

    return ImageVerdict(
        path=path,
        keep=not reasons,
        reasons=tuple(reasons),
        brightness=brightness,
        clip_high=clip_high,
        clip_low=clip_low,
        blur_var=blur_var,
        faces=faces,
        min_ear=min_ear,
    )
