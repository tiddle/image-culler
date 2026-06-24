from pathlib import Path

import pytest

from image_culler import core


def _touch(path: Path) -> Path:
    path.write_bytes(b"x")
    return path


def test_find_images_top_level_only(tmp_path: Path) -> None:
    _touch(tmp_path / "a.jpg")
    _touch(tmp_path / "b.CR2")
    _touch(tmp_path / "notes.txt")
    sub = tmp_path / "nested"
    sub.mkdir()
    _touch(sub / "deep.jpg")

    found = core.find_images(tmp_path)

    names = [p.name for p in found]
    assert names == ["a.jpg", "b.CR2"]


def test_find_images_is_case_insensitive_on_extension(tmp_path: Path) -> None:
    _touch(tmp_path / "x.JPG")
    _touch(tmp_path / "y.Nef")

    found = {p.name for p in core.find_images(tmp_path)}

    assert found == {"x.JPG", "y.Nef"}


def test_find_images_rejects_non_folder(tmp_path: Path) -> None:
    f = _touch(tmp_path / "single.jpg")
    with pytest.raises(NotADirectoryError):
        core.find_images(f)


def test_copy_to_selects_copies_all_and_reports_progress(tmp_path: Path) -> None:
    images = [_touch(tmp_path / f"img{i}.jpg") for i in range(3)]
    dest = tmp_path / core.SELECTS_DIRNAME

    seen: list[tuple[int, int]] = []
    copied = core.copy_to_selects(
        images, dest, on_progress=lambda done, total, _p: seen.append((done, total))
    )

    assert copied == 3
    assert sorted(p.name for p in dest.iterdir()) == [
        "img0.jpg",
        "img1.jpg",
        "img2.jpg",
    ]
    assert seen == [(1, 3), (2, 3), (3, 3)]


def test_process_folder_creates_selects_with_keepers(tmp_path: Path) -> None:
    _touch(tmp_path / "a.jpg")
    _touch(tmp_path / "b.png")
    _touch(tmp_path / "skip.txt")

    copied = core.process_folder(tmp_path)

    selects = tmp_path / core.SELECTS_DIRNAME
    assert copied == 2
    assert selects.is_dir()
    assert sorted(p.name for p in selects.iterdir()) == ["a.jpg", "b.png"]


def test_process_folder_handles_empty_folder(tmp_path: Path) -> None:
    assert core.process_folder(tmp_path) == 0
