import math

import numpy as np

from image_culler import blink


def test_ear_open_eye_is_high():
    # Wide-open eye: corners 40px apart, lids ~16px apart -> EAR ~0.4.
    points = [(0, 0), (12, -8), (28, -8), (40, 0), (28, 8), (12, 8)]
    assert blink.eye_aspect_ratio(points) > 0.3


def test_ear_closed_eye_is_low():
    # Shut eye: lids nearly touching the horizontal line -> EAR near 0.
    points = [(0, 0), (12, -1), (28, -1), (40, 0), (28, 1), (12, 1)]
    assert blink.eye_aspect_ratio(points) < 0.1


def test_ear_handles_degenerate_horizontal():
    points = [(5, 0), (5, -3), (5, -3), (5, 0), (5, 3), (5, 3)]
    assert blink.eye_aspect_ratio(points) == 0.0


def test_model_asset_is_bundled():
    assert blink.model_path().is_file()


def test_no_face_or_unavailable_is_never_flagged_closed():
    # Random noise has no face. Whether or not the MediaPipe runtime is present,
    # the result must never report a closed eye and must not raise.
    rng = np.random.default_rng(1)
    img = rng.integers(0, 255, size=(128, 128, 3), dtype=np.uint8)
    result = blink.detect_closed_eyes(img, ear_threshold=0.18)
    assert result.any_closed is False
    assert result.faces == 0
    assert result.min_ear == math.inf
