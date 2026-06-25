import math
from pathlib import Path

import numpy as np
import piexif

from image_culler.detect import (
    ImageVerdict,
    Thresholds,
    hamming_distance,
    perceptual_hash,
)
from image_culler.grouping import capture_time, group_bursts


# --- perceptual hash -------------------------------------------------------


def _gradient(shift: int = 0) -> np.ndarray:
    base = np.tile(np.arange(32, dtype=np.uint8) * 8, (32, 1))
    return np.roll(base, shift, axis=1)


def test_phash_identical_images_distance_zero() -> None:
    img = _gradient()
    assert hamming_distance(perceptual_hash(img), perceptual_hash(img.copy())) == 0


def test_phash_is_deterministic() -> None:
    img = _gradient(3)
    assert perceptual_hash(img) == perceptual_hash(img)


def test_phash_very_different_images_have_large_distance() -> None:
    rng = np.random.default_rng(7)
    a = np.zeros((64, 64), dtype=np.uint8)
    b = rng.integers(0, 256, size=(64, 64), dtype=np.uint8)
    assert hamming_distance(perceptual_hash(a), perceptual_hash(b)) > 10


# --- verdict builders ------------------------------------------------------


def _v(name: str, *, phash: int, keep: bool = True, blur: float = 500.0,
       brightness: float = 128.0, reasons: tuple[str, ...] = (),
       min_ear: float = math.inf) -> ImageVerdict:
    return ImageVerdict(
        path=Path(name), keep=keep, reasons=reasons, brightness=brightness,
        clip_high=0.0, clip_low=0.0, blur_var=blur, phash=phash, min_ear=min_ear,
    )


T = Thresholds(burst_time_gap=2.0, burst_phash_distance=10)


# --- capture time ----------------------------------------------------------


def _jpeg_with_time(path: Path, when: str) -> Path:
    import cv2

    cv2.imwrite(str(path), np.full((16, 16, 3), 128, dtype=np.uint8))
    exif = {"Exif": {piexif.ExifIFD.DateTimeOriginal: when.encode()}}
    piexif.insert(piexif.dump(exif), str(path))
    return path


def test_capture_time_reads_exif(tmp_path: Path) -> None:
    p = _jpeg_with_time(tmp_path / "a.jpg", "2026:06:25 10:00:00")
    t = capture_time(p)
    assert t is not None


def test_capture_time_missing_exif_is_none(tmp_path: Path) -> None:
    import cv2

    p = tmp_path / "noexif.png"
    cv2.imwrite(str(p), np.full((16, 16, 3), 128, dtype=np.uint8))
    assert capture_time(p) is None


# --- grouping --------------------------------------------------------------


def test_near_identical_frames_form_one_group() -> None:
    h = perceptual_hash(_gradient())
    frames = [_v(f"b{i}.jpg", phash=h, blur=500.0 + i) for i in range(3)]
    out = {v.path.name: v for v in group_bursts(frames, T)}
    assert {v.group_id for v in out.values()} == {1}
    ranks = {v.path.name: v.group_rank for v in out.values()}
    assert sorted(ranks.values()) == [1, 2, 3]


def test_scene_change_splits_group_despite_no_time() -> None:
    rng = np.random.default_rng(11)
    near = perceptual_hash(_gradient())
    far = perceptual_hash(rng.integers(0, 256, size=(64, 64), dtype=np.uint8))
    assert hamming_distance(near, far) >= T.burst_phash_distance
    frames = [_v("a.jpg", phash=near), _v("b.jpg", phash=far)]
    out = {v.path.name: v for v in group_bursts(frames, T)}
    assert out["a.jpg"].group_id != out["b.jpg"].group_id


def test_best_of_keeps_sharpest_rest_are_duplicates() -> None:
    h = perceptual_hash(_gradient())
    frames = [
        _v("dull.jpg", phash=h, blur=100.0),
        _v("sharp.jpg", phash=h, blur=900.0),
    ]
    out = {v.path.name: v for v in group_bursts(frames, T)}
    assert out["sharp.jpg"].keep and out["sharp.jpg"].group_rank == 1
    assert not out["dull.jpg"].keep
    assert "duplicate" in out["dull.jpg"].reasons


def test_all_fail_group_falls_back_to_per_frame() -> None:
    h = perceptual_hash(_gradient())
    frames = [
        _v("x.jpg", phash=h, keep=False, reasons=("eyes-closed",)),
        _v("y.jpg", phash=h, keep=False, reasons=("eyes-closed",)),
    ]
    out = {v.path.name: v for v in group_bursts(frames, T)}
    assert not any(v.keep for v in out.values())
    assert all("duplicate" not in v.reasons for v in out.values())
    assert all(v.reasons == ("eyes-closed",) for v in out.values())


def test_raw_jpeg_pair_shares_one_verdict_and_is_never_split() -> None:
    h = perceptual_hash(_gradient())
    other = perceptual_hash(_gradient(1))
    frames = [
        _v("IMG_001.CR2", phash=h, blur=300.0),
        _v("IMG_001.JPG", phash=h, blur=300.0),
        _v("IMG_002.JPG", phash=other, blur=800.0),
    ]
    out = {v.path.name: v for v in group_bursts(frames, T)}
    assert out["IMG_001.CR2"].group_id == out["IMG_001.JPG"].group_id
    assert out["IMG_001.CR2"].keep == out["IMG_001.JPG"].keep
    assert out["IMG_001.CR2"].group_rank == out["IMG_001.JPG"].group_rank


def test_singleton_keeper_stays_kept() -> None:
    h = perceptual_hash(np.zeros((32, 32), dtype=np.uint8))
    out = {v.path.name: v for v in group_bursts([_v("solo.jpg", phash=h)], T)}
    assert out["solo.jpg"].keep and out["solo.jpg"].group_rank == 1
