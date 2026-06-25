"""Phase 5: Lightroom / Capture One XMP sidecar output.

Write the cull verdict as an ``.xmp`` sidecar next to a RAW so the photographer
filters/sorts the cull inside their existing catalog instead of a ``selects/``
folder. Non-destructive: the sidecar is a NEW file; the original is never touched.

Lightroom's pick/reject flags are catalog-only and do not round-trip through XMP,
so the verdict is communicated through fields LR and Capture One *do* read from a
sidecar: ``xmp:Rating``, ``xmp:Label`` (colour), and ``dc:subject`` keywords. A
private ``imageculler:`` namespace stamps each decision so re-runs are
self-identifying.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .detect import ImageVerdict

_ICNS = "http://ns.imageculler.app/1.0/"

_NS = {
    "x": "adobe:ns:meta/",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "xmp": "http://ns.adobe.com/xap/1.0/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "imageculler": _ICNS,
}

# Verdict -> sidecar presentation. Photographers then filter by colour label
# (e.g. "show me everything that is not Red") inside Lightroom / Capture One.
_LABEL_BY_KIND = {"keep": "Green", "reject": "Red", "duplicate": "Yellow"}
_RATING_BY_KIND = {"keep": 2, "reject": 1, "duplicate": 1}

_KEYWORD_PREFIX = "Culled:"

_PACKET_TEMPLATE = (
    '<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>\n'
    '<x:xmpmeta xmlns:x="adobe:ns:meta/">\n'
    ' <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
    '  <rdf:Description rdf:about=""\n'
    '    xmlns:xmp="http://ns.adobe.com/xap/1.0/"\n'
    '    xmlns:dc="http://purl.org/dc/elements/1.1/"\n'
    '    xmlns:imageculler="{icns}"\n'
    '    xmp:Rating="{rating}"\n'
    '    xmp:Label="{label}"\n'
    '    imageculler:verdict="{verdict}"\n'
    '    imageculler:reason="{reason}">{subject}\n'
    "  </rdf:Description>\n"
    " </rdf:RDF>\n"
    "</x:xmpmeta>\n"
    '<?xpacket end="w"?>\n'
)


def sidecar_path(image_path: Path) -> Path:
    """Sibling ``.xmp`` path for an image: ``IMG_0001.CR2`` -> ``IMG_0001.xmp``."""
    return Path(image_path).with_suffix(".xmp")


def _culled_keywords(verdict: ImageVerdict) -> list[str]:
    if verdict.keep:
        return []
    return [f"{_KEYWORD_PREFIX}{reason}" for reason in verdict.reasons]


def _xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _subject_block(keywords: list[str]) -> str:
    if not keywords:
        return ""
    lines = "\n".join(f"      <rdf:li>{_xml_escape(kw)}</rdf:li>" for kw in keywords)
    return (
        "\n    <dc:subject>\n     <rdf:Bag>\n"
        f"{lines}\n     </rdf:Bag>\n    </dc:subject>"
    )


def build_xmp(verdict: ImageVerdict) -> str:
    """Build a fresh, minimal valid XMP packet describing one verdict."""
    kind = verdict.kind
    reason = "" if verdict.keep else verdict.reason_text
    return _PACKET_TEMPLATE.format(
        icns=_ICNS,
        rating=_RATING_BY_KIND[kind],
        label=_LABEL_BY_KIND[kind],
        verdict=kind,
        reason=_xml_escape(reason),
        subject=_subject_block(_culled_keywords(verdict)),
    )


def _find_description(root: ET.Element) -> ET.Element | None:
    tag = f"{{{_NS['rdf']}}}Description"
    if root.tag == tag:
        return root
    for element in root.iter(tag):
        return element
    return None


def _merge_subject(desc: ET.Element, keywords: list[str]) -> None:
    """Preserve the photographer's own keywords; refresh only our ``Culled:*``."""
    subject_tag = f"{{{_NS['dc']}}}subject"
    bag_tag = f"{{{_NS['rdf']}}}Bag"
    li_tag = f"{{{_NS['rdf']}}}li"

    preserved: list[str] = []
    subject = desc.find(subject_tag)
    if subject is not None:
        bag = subject.find(bag_tag)
        if bag is not None:
            for li in bag.findall(li_tag):
                if li.text and not li.text.startswith(_KEYWORD_PREFIX):
                    preserved.append(li.text)
        desc.remove(subject)

    merged = preserved + keywords
    if not merged:
        return

    subject = ET.SubElement(desc, subject_tag)
    bag = ET.SubElement(subject, bag_tag)
    for keyword in merged:
        ET.SubElement(bag, li_tag).text = keyword


def _serialize(root: ET.Element) -> str:
    for prefix, uri in _NS.items():
        ET.register_namespace(prefix, uri)
    xml = ET.tostring(root, encoding="unicode")
    return (
        '<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>\n'
        f"{xml}\n"
        '<?xpacket end="w"?>\n'
    )


def merge_xmp(existing: str, verdict: ImageVerdict) -> str | None:
    """Merge our verdict into a pre-existing sidecar, preserving the user's edits.

    Returns the merged XMP, or ``None`` if the existing file cannot be parsed
    safely. Refusing to write on a parse failure is deliberate: silently
    overwriting a photographer's metadata is unacceptable, so when in doubt we
    back off and leave their file untouched.
    """
    body = re.sub(r"<\?xpacket[^?]*\?>", "", existing).strip()
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return None

    desc = _find_description(root)
    if desc is None:
        return None

    kind = verdict.kind
    reason = "" if verdict.keep else verdict.reason_text
    desc.set(f"{{{_NS['xmp']}}}Rating", str(_RATING_BY_KIND[kind]))
    desc.set(f"{{{_NS['xmp']}}}Label", _LABEL_BY_KIND[kind])
    desc.set(f"{{{_ICNS}}}verdict", kind)
    desc.set(f"{{{_ICNS}}}reason", reason)
    _merge_subject(desc, _culled_keywords(verdict))
    return _serialize(root)


def write_sidecar(verdict: ImageVerdict, sidecar: Path | None = None) -> str:
    """Write (or merge) the sidecar for one verdict.

    Returns ``"written"`` for a fresh sidecar, ``"merged"`` when an existing
    parseable sidecar was updated, or ``"skipped"`` when an existing sidecar
    could not be parsed and was left untouched.
    """
    target = sidecar or sidecar_path(verdict.path)
    if target.exists():
        try:
            existing = target.read_text(encoding="utf-8")
        except OSError:
            return "skipped"
        merged = merge_xmp(existing, verdict)
        if merged is None:
            return "skipped"
        target.write_text(merged, encoding="utf-8")
        return "merged"

    target.write_text(build_xmp(verdict), encoding="utf-8")
    return "written"
