from pathlib import Path

import numpy as np
import pytest
import cv2

from image_culler import core
from image_culler.detect import Thresholds

# Pipeline tests isolate exposure/blur + IO from the MediaPipe blink stage.
NO_BLINK = Thresholds(check_blink=False)


def _touch(path: Path) -> Path:
    path.write_bytes(b"x")
    return path


def _write_sharp_image(path: Path) -> Path:
    """A well-exposed, sharp image (random noise): a guaranteed keeper."""
    rng = np.random.default_rng(0)
    img = rng.integers(40, 215, size=(256, 256, 3), dtype=np.uint8)
    cv2.imwrite(str(path), img)
    return path


def _write_black_image(path: Path) -> Path:
    cv2.imwrite(str(path), np.zeros((256, 256, 3), dtype=np.uint8))
    return path


def test_find_images_top_level_only(tmp_path: Path) -> None:
    _touch(tmp_path / "a.jpg")
    _touch(tmp_path / "b.CR2")
    _touch(tmp_path / "notes.txt")
    sub = tmp_path / "nested"
    sub.mkdir()
    _touch(sub / "deep.jpg")

    found = core.find_images(tmp_path)

    assert [p.name for p in found] == ["a.jpg", "b.CR2"]


def test_find_images_is_case_insensitive_on_extension(tmp_path: Path) -> None:
    _touch(tmp_path / "x.JPG")
    _touch(tmp_path / "y.Nef")

    found = {p.name for p in core.find_images(tmp_path)}

    assert found == {"x.JPG", "y.Nef"}


def test_find_images_rejects_non_folder(tmp_path: Path) -> None:
    f = _touch(tmp_path / "single.jpg")
    with pytest.raises(NotADirectoryError):
        core.find_images(f)


def test_copy_to_selects_copies_all(tmp_path: Path) -> None:
    images = [_touch(tmp_path / f"img{i}.jpg") for i in range(3)]
    dest = tmp_path / core.SELECTS_DIRNAME

    copied = core.copy_to_selects(images, dest)

    assert copied == 3
    assert sorted(p.name for p in dest.iterdir()) == ["img0.jpg", "img1.jpg", "img2.jpg"]


def test_process_folder_keeps_good_rejects_bad(tmp_path: Path) -> None:
    _write_sharp_image(tmp_path / "good.png")
    _write_black_image(tmp_path / "dark.png")

    summary = core.process_folder(tmp_path, thresholds=NO_BLINK)

    selects = tmp_path / core.SELECTS_DIRNAME
    assert summary.total == 2
    assert summary.kept == 1
    assert summary.rejected == 1
    assert [p.name for p in selects.iterdir()] == ["good.png"]


def test_process_folder_writes_report(tmp_path: Path) -> None:
    _write_sharp_image(tmp_path / "good.png")
    _write_black_image(tmp_path / "dark.png")

    summary = core.process_folder(tmp_path, thresholds=NO_BLINK)

    report = tmp_path / core.REPORT_FILENAME
    assert summary.report_path == report
    text = report.read_text(encoding="utf-8")
    assert "file,verdict,reason" in text
    assert "good.png,keep" in text
    assert "dark.png,reject" in text
    assert "underexposed" in text


def test_process_folder_collapses_a_burst_to_one_keeper(tmp_path: Path) -> None:
    rng = np.random.default_rng(0)
    frame = rng.integers(40, 215, size=(256, 256, 3), dtype=np.uint8)
    for name in ("b1.png", "b2.png", "b3.png"):
        cv2.imwrite(str(tmp_path / name), frame)

    summary = core.process_folder(tmp_path, thresholds=NO_BLINK)

    selects = tmp_path / core.SELECTS_DIRNAME
    assert summary.kept == 1
    assert len([p for p in selects.iterdir()]) == 1
    report = (tmp_path / core.REPORT_FILENAME).read_text(encoding="utf-8")
    assert "group_id,group_rank" in report
    assert "duplicate" in report


def test_grouping_can_be_disabled(tmp_path: Path) -> None:
    rng = np.random.default_rng(0)
    frame = rng.integers(40, 215, size=(256, 256, 3), dtype=np.uint8)
    for name in ("b1.png", "b2.png", "b3.png"):
        cv2.imwrite(str(tmp_path / name), frame)

    summary = core.process_folder(
        tmp_path, thresholds=Thresholds(check_blink=False, group_bursts=False)
    )

    assert summary.kept == 3


def test_process_folder_handles_empty_folder(tmp_path: Path) -> None:
    summary = core.process_folder(tmp_path, thresholds=NO_BLINK)
    assert summary.total == 0
    assert summary.kept == 0
    assert summary.report_path is None
