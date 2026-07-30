from pathlib import Path

import cv2
import numpy as np

from image_culler.detect import load_image


def _write_jpeg(path: Path) -> None:
    # Encode then write bytes ourselves so the fixture does not itself depend on
    # cv2.imwrite's path handling (the very thing under test on the read side).
    ok, encoded = cv2.imencode(".jpg", np.full((16, 16, 3), 128, dtype=np.uint8))
    assert ok
    encoded.tofile(str(path))


def test_load_image_handles_spaces_and_unicode_in_path(tmp_path: Path) -> None:
    folder = tmp_path / "holiday 2026 café"
    folder.mkdir()
    photo = folder / "my great photo 01.jpg"
    _write_jpeg(photo)
    image = load_image(photo)
    assert image is not None and image.size


def test_load_image_missing_file_is_none(tmp_path: Path) -> None:
    assert load_image(tmp_path / "not here.jpg") is None
