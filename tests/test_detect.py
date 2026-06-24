from pathlib import Path

import cv2
import numpy as np

from image_culler.detect import Thresholds, analyze_image


def _save(path: Path, img: np.ndarray) -> Path:
    cv2.imwrite(str(path), img)
    return path


def _sharp_noise(seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.integers(40, 215, size=(256, 256, 3), dtype=np.uint8)


def test_well_exposed_sharp_image_is_kept(tmp_path: Path) -> None:
    p = _save(tmp_path / "good.png", _sharp_noise())
    verdict = analyze_image(p)
    assert verdict.keep
    assert verdict.reasons == ()


def test_black_image_is_underexposed(tmp_path: Path) -> None:
    p = _save(tmp_path / "black.png", np.zeros((256, 256, 3), dtype=np.uint8))
    verdict = analyze_image(p)
    assert not verdict.keep
    assert "underexposed" in verdict.reasons


def test_white_image_is_overexposed(tmp_path: Path) -> None:
    p = _save(tmp_path / "white.png", np.full((256, 256, 3), 255, dtype=np.uint8))
    verdict = analyze_image(p)
    assert not verdict.keep
    assert "overexposed" in verdict.reasons
    assert "blown-highlights" in verdict.reasons


def test_blurred_image_is_flagged_blurry(tmp_path: Path) -> None:
    # Start from sharp noise, blur it heavily so detail (high-freq) collapses.
    blurred = cv2.GaussianBlur(_sharp_noise(), (0, 0), sigmaX=8)
    p = _save(tmp_path / "blur.png", blurred)
    verdict = analyze_image(p)
    assert not verdict.keep
    assert "blurry" in verdict.reasons


def test_undecodable_file_is_kept_as_safety(tmp_path: Path) -> None:
    p = tmp_path / "broken.jpg"
    p.write_bytes(b"not an image")
    verdict = analyze_image(p)
    assert verdict.keep
    assert "undecodable" in verdict.reasons


def test_thresholds_are_tunable(tmp_path: Path) -> None:
    # A mid-gray flat frame: blur variance ~0. Lenient blur threshold keeps it.
    flat = np.full((256, 256, 3), 128, dtype=np.uint8)
    p = _save(tmp_path / "flat.png", flat)
    strict = analyze_image(p, Thresholds(min_blur_var=100.0))
    lenient = analyze_image(p, Thresholds(min_blur_var=0.0))
    assert "blurry" in strict.reasons
    assert lenient.keep
