"""Phase 2 blink / closed-eye detection (MediaPipe Tasks FaceLandmarker).

The Face Landmarker returns the 468-point face mesh per face; we turn the six
classic eye points into an eye-aspect-ratio (EAR). A low EAR means a near-shut
eye. Per Carlo (2026-06-24), any closed eye in a group shot rejects the whole
frame, so one eye on one face below the threshold is enough to reject.

The landmarker (and its bundled ``face_landmarker.task`` model) is built once
per process and reused, so a multiprocessing pool spins up one detector per
worker rather than per image. If MediaPipe or its native libraries are missing,
``BlinkResult.available`` is False and the caller keeps the frame rather than
silently dropping the whole blink check.
"""

from __future__ import annotations

import math
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# Six-point eye landmarks in the MediaPipe 468-point face-mesh topology.
# Order per eye: outer corner, upper-1, upper-2, inner corner, lower-2, lower-1.
_LEFT_EYE = (33, 160, 158, 133, 153, 144)
_RIGHT_EYE = (362, 385, 387, 263, 373, 380)
_MAX_FACES = 20
_MODEL_FILENAME = "face_landmarker.task"

_landmarker = None       # per-process lazy singleton
_unavailable = False     # set once if the engine can't be built
_lock = threading.Lock()


@dataclass(frozen=True)
class BlinkResult:
    faces: int
    any_closed: bool
    min_ear: float          # smallest EAR across all eyes; inf when no face
    available: bool = True   # False if the blink engine could not be built


def model_path() -> Path:
    # AIDEV-NOTE: under a PyInstaller onefile build the package data is
    # extracted to sys._MEIPASS; fall back to the source-tree location dev runs.
    base = getattr(sys, "_MEIPASS", None)
    if base is not None:
        bundled = Path(base) / "image_culler" / "assets" / _MODEL_FILENAME
        if bundled.is_file():
            return bundled
    return Path(__file__).resolve().parent / "assets" / _MODEL_FILENAME


def eye_aspect_ratio(points: list[tuple[float, float]]) -> float:
    """EAR from six (x, y) eye points: (|p2-p6| + |p3-p5|) / (2 * |p1-p4|)."""
    p1, p2, p3, p4, p5, p6 = points
    vertical = _dist(p2, p6) + _dist(p3, p5)
    horizontal = _dist(p1, p4)
    if horizontal == 0:
        return 0.0
    return vertical / (2.0 * horizontal)


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _get_landmarker():
    global _landmarker, _unavailable
    if _landmarker is not None or _unavailable:
        return _landmarker
    with _lock:
        if _landmarker is None and not _unavailable:
            try:
                from mediapipe.tasks import python
                from mediapipe.tasks.python import vision

                options = vision.FaceLandmarkerOptions(
                    base_options=python.BaseOptions(model_asset_path=str(model_path())),
                    num_faces=_MAX_FACES,
                    output_face_blendshapes=False,
                )
                _landmarker = vision.FaceLandmarker.create_from_options(options)
            except Exception:  # noqa: BLE001 - missing libs/model -> mark unavailable
                _unavailable = True
    return _landmarker


def blink_available() -> bool:
    return _get_landmarker() is not None


def detect_closed_eyes(image_bgr: np.ndarray, ear_threshold: float) -> BlinkResult:
    """Return blink info for ``image_bgr``. No face -> nothing to judge."""
    landmarker = _get_landmarker()
    if landmarker is None:
        return BlinkResult(faces=0, any_closed=False, min_ear=math.inf, available=False)

    import cv2
    import mediapipe as mp

    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    result = landmarker.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
    faces = result.face_landmarks
    if not faces:
        return BlinkResult(faces=0, any_closed=False, min_ear=math.inf)

    height, width = image_bgr.shape[:2]
    min_ear = math.inf
    for face in faces:
        for indices in (_LEFT_EYE, _RIGHT_EYE):
            points = [(face[i].x * width, face[i].y * height) for i in indices]
            min_ear = min(min_ear, eye_aspect_ratio(points))

    return BlinkResult(faces=len(faces), any_closed=min_ear < ear_threshold, min_ear=min_ear)
