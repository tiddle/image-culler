"""Phase 4: burst / near-duplicate grouping.

A post-pass over already-scored :class:`ImageVerdict`s: walk frames in capture
order, join visually-similar adjacent frames into a burst, keep the single best
frame of each burst, and mark the rest ``duplicate``. Non-destructive: duplicates
are never moved or deleted, just not copied to ``selects/``.

Only cheap signals are added here (an EXIF capture-time read; the perceptual hash
is already computed during scoring), so no new heavy ML model is needed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

from .core import _RASTER_EXTENSIONS, _RAW_EXTENSIONS
from .detect import ImageVerdict, Thresholds, hamming_distance

_MID_LUMA = 128.0  # exposure tiebreak target: closest to mid-grey wins


def capture_time(path: Path) -> float | None:
    """EXIF ``DateTimeOriginal`` as a sortable epoch float, or ``None``.

    Sub-second is folded in when the camera records it. Returns ``None`` when
    EXIF is missing or unreadable so the caller falls back to filename order.
    """
    try:
        import exifread
    except ImportError:
        return None

    try:
        with open(path, "rb") as handle:
            tags = exifread.process_file(handle, details=False)
    except Exception:  # noqa: BLE001 - unreadable EXIF -> no timestamp
        return None

    raw = tags.get("EXIF DateTimeOriginal") or tags.get("Image DateTime")
    if raw is None:
        return None
    try:
        stamp = datetime.strptime(str(raw).strip(), "%Y:%m:%d %H:%M:%S").timestamp()
    except (ValueError, OverflowError):
        return None

    subsec = tags.get("EXIF SubSecTimeOriginal")
    if subsec is not None:
        digits = str(subsec).strip()
        if digits.isdigit():
            stamp += float("0." + digits)
    return stamp


@dataclass
class _Unit:
    """One logical capture: a single file, or a RAW+JPEG pair shot together."""

    members: list[ImageVerdict]   # 1 frame, or a RAW+raster pair
    rep: ImageVerdict             # the frame whose metrics rank the unit
    capture: float | None         # EXIF capture time, if any member has one


def _representative(members: list[ImageVerdict]) -> ImageVerdict:
    """Pick the frame that stands in for a unit's quality and phash.

    Prefer the raster (developed JPEG) over the RAW: its sharpness and phash are
    computed on a finished image and compare cleanly against other JPEGs.
    """
    for member in members:
        if member.path.suffix.lower() in _RASTER_EXTENSIONS:
            return member
    return members[0]


def _logical_units(verdicts: list[ImageVerdict]) -> list[_Unit]:
    """Collapse same-stem RAW+raster pairs into one unit; everything else is solo.

    A photographer shooting RAW+JPEG produces ``IMG_001.CR2`` and ``IMG_001.JPG``
    with identical timestamps and near-identical phash. They are one capture and
    must never be deduped against each other.
    """
    by_stem: dict[str, list[ImageVerdict]] = {}
    for verdict in verdicts:
        by_stem.setdefault(verdict.path.stem.lower(), []).append(verdict)

    units: list[_Unit] = []
    for members in by_stem.values():
        exts = {m.path.suffix.lower() for m in members}
        has_raw = any(e in _RAW_EXTENSIONS for e in exts)
        has_raster = any(e in _RASTER_EXTENSIONS for e in exts)
        if len(members) > 1 and has_raw and has_raster:
            captures = [c for c in (capture_time(m.path) for m in members) if c is not None]
            units.append(
                _Unit(
                    members=members,
                    rep=_representative(members),
                    capture=min(captures) if captures else None,
                )
            )
        else:
            for member in members:
                units.append(
                    _Unit(members=[member], rep=member, capture=capture_time(member.path))
                )
    return units


def _ordered_units(units: list[_Unit]) -> list[_Unit]:
    """Capture-order sort. Uses EXIF when every unit has it, else filename order."""
    if units and all(u.capture is not None for u in units):
        return sorted(units, key=lambda u: (u.capture, u.rep.path.name.lower()))
    return sorted(units, key=lambda u: u.rep.path.name.lower())


def _same_burst(
    anchor: _Unit, prev: _Unit, curr: _Unit, thresholds: Thresholds
) -> bool:
    """Does ``curr`` still belong to the burst started by ``anchor``?

    Two signals must agree: close in time AND visually similar.

    Visual similarity is measured against the burst's *anchor* (its first frame),
    not the immediately preceding one. Comparing only to the previous frame lets a
    slowly drifting sequence chain together frame-by-frame (each step under the
    phash threshold) until an entire shoot collapses into a single group and only
    one keeper survives. Anchoring bounds how far a burst may drift from where it
    began.

    Time, by contrast, is checked against the previous frame: a burst is a run of
    frames each shot close after the last, so the gap that matters is between
    consecutive shots. When timestamps are absent we group on phash alone.
    """
    if hamming_distance(anchor.rep.phash, curr.rep.phash) >= thresholds.burst_phash_distance:
        return False
    if prev.capture is not None and curr.capture is not None:
        return abs(curr.capture - prev.capture) < thresholds.burst_time_gap
    return True


def _quality_key(unit: _Unit) -> tuple[float, float, float]:
    """Best-of-group rank key (smaller is better): sharpest, best-exposed, eyes-open."""
    v = unit.rep
    ear = -v.min_ear if math.isfinite(v.min_ear) else -math.inf
    return (-v.blur_var, abs(v.brightness - _MID_LUMA), ear)


def _assign(group: list[_Unit], group_id: int, out: dict[Path, ImageVerdict]) -> None:
    """Resolve one burst: choose a keeper, mark the rest, write into ``out``."""
    survivors = [u for u in group if u.rep.keep]

    if not survivors:
        # All-fail fallback: keep each frame's own per-frame verdict and reason;
        # do not force-keep one. Rank purely for auditability.
        for rank, unit in enumerate(sorted(group, key=_quality_key), start=1):
            for member in unit.members:
                out[member.path] = replace(member, group_id=group_id, group_rank=rank)
        return

    ranked = sorted(survivors, key=_quality_key)
    keeper = ranked[0]
    losers = [u for u in group if u is not keeper]
    order = [keeper] + sorted(losers, key=_quality_key)

    for rank, unit in enumerate(order, start=1):
        for member in unit.members:
            if unit is keeper:
                out[member.path] = replace(member, group_id=group_id, group_rank=rank)
            elif unit.rep.keep:
                # A passer that lost the burst: this is a duplicate, not a reject.
                out[member.path] = replace(
                    member, keep=False, reasons=("duplicate",),
                    group_id=group_id, group_rank=rank,
                )
            else:
                # Already failed a gate: stays a reject with its own reason.
                out[member.path] = replace(member, group_id=group_id, group_rank=rank)


def group_bursts(
    verdicts: list[ImageVerdict], thresholds: Thresholds
) -> list[ImageVerdict]:
    """Group bursts and pick a keeper per group; return verdicts in input order.

    Each returned verdict carries ``group_id`` (1-based per burst, singletons get
    their own) and ``group_rank`` (1 = keeper, 2+ = duplicates by quality). Frames
    that lost a burst become ``duplicate`` (``keep=False``); rejects keep their
    own reason. RAW+JPEG pairs are never split and share one decision.
    """
    units = _ordered_units(_logical_units(verdicts))
    if not units:
        return list(verdicts)

    groups: list[list[_Unit]] = [[units[0]]]
    for prev, curr in zip(units, units[1:]):
        anchor = groups[-1][0]
        if _same_burst(anchor, prev, curr, thresholds):
            groups[-1].append(curr)
        else:
            groups.append([curr])

    out: dict[Path, ImageVerdict] = {}
    for group_id, group in enumerate(groups, start=1):
        _assign(group, group_id, out)
    return [out[v.path] for v in verdicts]
