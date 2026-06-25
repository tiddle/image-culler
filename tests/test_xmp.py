import re
import xml.etree.ElementTree as ET
from pathlib import Path

from image_culler.detect import ImageVerdict
from image_culler.xmp import (
    build_xmp,
    merge_xmp,
    sidecar_path,
    write_sidecar,
)

_NS = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "xmp": "http://ns.adobe.com/xap/1.0/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "imageculler": "http://ns.imageculler.app/1.0/",
}


def _v(name: str, *, keep: bool, reasons: tuple[str, ...] = ()) -> ImageVerdict:
    return ImageVerdict(
        path=Path(name), keep=keep, reasons=reasons, brightness=128.0,
        clip_high=0.0, clip_low=0.0, blur_var=500.0,
    )


def _description(xmp: str) -> ET.Element:
    """Parse an XMP packet (stripping xpacket PIs) and return rdf:Description."""
    body = re.sub(r"<\?xpacket[^?]*\?>", "", xmp).strip()
    root = ET.fromstring(body)
    desc = root.find(f".//{{{_NS['rdf']}}}Description")
    assert desc is not None
    return desc


def _keywords(desc: ET.Element) -> list[str]:
    return [
        li.text
        for li in desc.findall(
            f"{{{_NS['dc']}}}subject/{{{_NS['rdf']}}}Bag/{{{_NS['rdf']}}}li"
        )
    ]


# --- sidecar path ----------------------------------------------------------


def test_sidecar_path_swaps_extension() -> None:
    assert sidecar_path(Path("/p/IMG_0001.CR2")) == Path("/p/IMG_0001.xmp")
    assert sidecar_path(Path("a.jpg")) == Path("a.xmp")


# --- build: valid XML + verdict mapping ------------------------------------


def test_build_keep_is_green_two_stars_no_keywords() -> None:
    desc = _description(build_xmp(_v("a.dng", keep=True)))
    assert desc.get(f"{{{_NS['xmp']}}}Label") == "Green"
    assert desc.get(f"{{{_NS['xmp']}}}Rating") == "2"
    assert desc.get(f"{{{_NS['imageculler']}}}verdict") == "keep"
    assert _keywords(desc) == []


def test_build_reject_is_red_with_reason_keywords() -> None:
    desc = _description(build_xmp(_v("a.dng", keep=False, reasons=("blurry",))))
    assert desc.get(f"{{{_NS['xmp']}}}Label") == "Red"
    assert desc.get(f"{{{_NS['xmp']}}}Rating") == "1"
    assert desc.get(f"{{{_NS['imageculler']}}}verdict") == "reject"
    assert _keywords(desc) == ["Culled:blurry"]


def test_build_duplicate_is_yellow() -> None:
    desc = _description(build_xmp(_v("a.dng", keep=False, reasons=("duplicate",))))
    assert desc.get(f"{{{_NS['xmp']}}}Label") == "Yellow"
    assert desc.get(f"{{{_NS['imageculler']}}}verdict") == "duplicate"
    assert _keywords(desc) == ["Culled:duplicate"]


# --- merge: preserve the photographer's metadata ---------------------------


_EXISTING = (
    '<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>'
    '<x:xmpmeta xmlns:x="adobe:ns:meta/">'
    '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
    '<rdf:Description rdf:about=""'
    ' xmlns:xmp="http://ns.adobe.com/xap/1.0/"'
    ' xmlns:dc="http://purl.org/dc/elements/1.1/"'
    ' xmp:Rating="5" xmp:Label="Blue">'
    "<dc:subject><rdf:Bag>"
    "<rdf:li>Portrait</rdf:li><rdf:li>Culled:stale</rdf:li>"
    "</rdf:Bag></dc:subject>"
    "</rdf:Description></rdf:RDF></x:xmpmeta>"
    '<?xpacket end="w"?>'
)


def test_merge_updates_our_fields_and_keeps_user_keywords() -> None:
    merged = merge_xmp(_EXISTING, _v("a.dng", keep=False, reasons=("blurry",)))
    assert merged is not None
    desc = _description(merged)
    # Our verdict overwrites the old rating/label.
    assert desc.get(f"{{{_NS['xmp']}}}Rating") == "1"
    assert desc.get(f"{{{_NS['xmp']}}}Label") == "Red"
    keywords = _keywords(desc)
    assert "Portrait" in keywords          # user's own keyword preserved
    assert "Culled:stale" not in keywords  # our stale keyword refreshed away
    assert "Culled:blurry" in keywords     # current verdict applied


def test_merge_unparseable_returns_none() -> None:
    assert merge_xmp("<not xml <<<", _v("a.dng", keep=True)) is None


# --- write_sidecar: status + non-destructive on parse failure --------------


def test_write_sidecar_fresh(tmp_path: Path) -> None:
    raw = tmp_path / "IMG_1.CR2"
    status = write_sidecar(_v(str(raw), keep=True))
    assert status == "written"
    assert (tmp_path / "IMG_1.xmp").exists()


def test_write_sidecar_merges_existing(tmp_path: Path) -> None:
    side = tmp_path / "IMG_1.xmp"
    side.write_text(_EXISTING, encoding="utf-8")
    status = write_sidecar(_v(str(tmp_path / "IMG_1.CR2"), keep=False, reasons=("blurry",)))
    assert status == "merged"
    assert "Portrait" in side.read_text(encoding="utf-8")


def test_write_sidecar_skips_unparseable_and_leaves_it(tmp_path: Path) -> None:
    side = tmp_path / "IMG_1.xmp"
    side.write_text("<<< not valid xmp", encoding="utf-8")
    status = write_sidecar(_v(str(tmp_path / "IMG_1.CR2"), keep=False, reasons=("blurry",)))
    assert status == "skipped"
    assert side.read_text(encoding="utf-8") == "<<< not valid xmp"
