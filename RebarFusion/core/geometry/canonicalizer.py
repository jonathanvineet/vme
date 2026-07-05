"""
core/geometry/canonicalizer.py

Phase 3: Eight-stage canonicalization pipeline.

Stage 3.1  INSERT Explosion      — recursive, handles rot/scale/mirror
Stage 3.2  World Transform       — all coordinates → world space
Stage 3.3  Coordinate Canon.     — snap to EPSILON grid
Stage 3.4  Primitive Canon.      — derived fields (length, direction, arc norm)
Stage 3.5  Deduplication         — merge identical geometry, keep provenance
Stage 3.6  Bounding Boxes        — entity / block / drawing level
Stage 3.7  Fingerprints          — SHA-256 per canonical entity
Stage 3.8  Validation            — halt on critical errors
"""

from __future__ import annotations

import hashlib
import math
import uuid
from typing import Dict, List, Optional, Tuple
from uuid import UUID

import ezdxf
from ezdxf.math import Matrix44

from core.geometry.canonical import (
    BoundingBoxReport,
    CanonicalArc,
    CanonicalCircle,
    CanonicalDimension,
    CanonicalEntity,
    CanonicalHatch,
    CanonicalLine,
    CanonicalMText,
    CanonicalPolyline,
    CanonicalProvenance,
    CanonicalRepository,
    CanonicalText,
)
from core.geometry.entities import (
    ArcEntity, CircleEntity, DimensionEntity, GeometryEntity,
    HatchEntity, InsertEntity, LineEntity, MTextEntity,
    PolylineEntity, TextEntity, UnknownEntity,
)
from core.geometry.repository import DrawingRepository

EPSILON = 1e-5
MAX_BLOCK_DEPTH = 10


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _snap(v: float) -> float:
    """Round a coordinate to the EPSILON grid."""
    return round(v / EPSILON) * EPSILON


def _snap3(t: Tuple[float, float, float]) -> Tuple[float, float, float]:
    return (_snap(t[0]), _snap(t[1]), _snap(t[2]))


def _bbox(*points: Tuple[float, float, float]) -> Tuple[float, float, float, float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))


def _bbox_union(boxes: List[Tuple[float, float, float, float]]) -> Tuple[float, float, float, float]:
    if not boxes:
        return (0.0, 0.0, 0.0, 0.0)
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


def _normalize_angle(a: float) -> float:
    """Normalize angle into [0, 360)."""
    a = a % 360.0
    if a < 0:
        a += 360.0
    return a


def _sha256(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode())
    return h.hexdigest()


def _arc_midpoint(cx, cy, cz, r, start_deg, end_deg) -> Tuple[float, float, float]:
    mid_deg = (start_deg + end_deg) / 2.0
    if end_deg < start_deg:
        mid_deg = (start_deg + end_deg + 360.0) / 2.0
    mid_rad = math.radians(mid_deg)
    return (cx + r * math.cos(mid_rad), cy + r * math.sin(mid_rad), cz)


# ---------------------------------------------------------------------------
# Stage 3.1 + 3.2 — INSERT explosion with transform accumulation
# ---------------------------------------------------------------------------

def _explode_inserts(
    doc: ezdxf.document.Drawing,
    drawing_repo: DrawingRepository,
    reader_name: str,
    drawing_filename: str,
) -> List[GeometryEntity]:
    """
    Recursively explode all INSERT entities into transformed primitives.
    Returns a flat list of GeometryEntity (no InsertEntity entries).
    """
    from core.readers.dxf_reader import DXFReader

    # All top-level non-insert entities first
    flat: List[GeometryEntity] = []
    flat += drawing_repo.lines
    flat += drawing_repo.arcs
    flat += drawing_repo.circles
    flat += drawing_repo.polylines
    flat += drawing_repo.texts
    flat += drawing_repo.mtexts
    flat += drawing_repo.dimensions
    flat += drawing_repo.hatches
    flat += drawing_repo.unknowns

    # Now explode inserts
    def _process_insert(insert: InsertEntity, depth: int = 0):
        if depth > MAX_BLOCK_DEPTH:
            return  # log only, don't crash

        block_name = insert.block_name
        if block_name not in doc.blocks:
            return

        block = doc.blocks[block_name]

        # Build combined transform: translation * rotation * scale
        ins = insert.insertion_point
        rot_rad = math.radians(insert.rotation)
        sx, sy, sz = insert.scale_x, insert.scale_y, insert.scale_z

        cos_r, sin_r = math.cos(rot_rad), math.sin(rot_rad)

        def _transform_pt(x: float, y: float, z: float) -> Tuple[float, float, float]:
            # Apply scale
            x2, y2, z2 = x * sx, y * sy, z * sz
            # Apply rotation (2D)
            x3 = x2 * cos_r - y2 * sin_r
            y3 = x2 * sin_r + y2 * cos_r
            z3 = z2
            # Apply translation
            return (x3 + ins.x, y3 + ins.y, z3 + ins.z)

        def _prov(entity, handle: str) -> CanonicalProvenance:
            return CanonicalProvenance(
                source_entity_uuid=insert.id,
                source_handle=handle,
                source_block=block_name,
                source_reader=reader_name,
                source_drawing=drawing_filename,
            )

        for ent in block:
            t = ent.dxftype()
            handle = ent.dxf.handle or ''
            layer = ent.dxf.layer if ent.dxf.hasattr('layer') else insert.layer

            if t == "LINE":
                s = _transform_pt(ent.dxf.start.x, ent.dxf.start.y, ent.dxf.start.z)
                e = _transform_pt(ent.dxf.end.x, ent.dxf.end.y, ent.dxf.end.z)
                from core.geometry.entities import LineEntity, Point, Matrix44 as M44
                flat.append(LineEntity(
                    id=uuid.uuid5(insert.id, f"{block_name}:{handle}"),
                    dxf_type="LINE",
                    layer=layer,
                    color=ent.dxf.color if ent.dxf.hasattr('color') else 256,
                    linetype=ent.dxf.linetype if ent.dxf.hasattr('linetype') else 'BYLAYER',
                    handle=handle,
                    owner_handle=ent.dxf.owner if ent.dxf.hasattr('owner') else '',
                    parent_block=block_name,
                    transform=M44(),
                    bounding_box=(min(s[0],e[0]), min(s[1],e[1]), max(s[0],e[0]), max(s[1],e[1])),
                    raw_properties={},
                    start=Point(*s),
                    end=Point(*e),
                ))

            elif t == "ARC":
                c = _transform_pt(ent.dxf.center.x, ent.dxf.center.y, ent.dxf.center.z)
                r = ent.dxf.radius * sx  # assume uniform scale
                from core.geometry.entities import ArcEntity, Point, Matrix44 as M44
                flat.append(ArcEntity(
                    id=uuid.uuid5(insert.id, f"{block_name}:{handle}"),
                    dxf_type="ARC",
                    layer=layer,
                    color=ent.dxf.color if ent.dxf.hasattr('color') else 256,
                    linetype=ent.dxf.linetype if ent.dxf.hasattr('linetype') else 'BYLAYER',
                    handle=handle,
                    owner_handle=ent.dxf.owner if ent.dxf.hasattr('owner') else '',
                    parent_block=block_name,
                    transform=M44(),
                    bounding_box=(c[0]-r, c[1]-r, c[0]+r, c[1]+r),
                    raw_properties={},
                    center=Point(*c),
                    radius=r,
                    start_angle=ent.dxf.start_angle + insert.rotation,
                    end_angle=ent.dxf.end_angle + insert.rotation,
                ))

            elif t == "LWPOLYLINE":
                points = [_transform_pt(p[0], p[1], 0.0) for p in ent.get_points(format='xy')]
                from core.geometry.entities import PolylineEntity, Point, Matrix44 as M44
                flat.append(PolylineEntity(
                    id=uuid.uuid5(insert.id, f"{block_name}:{handle}"),
                    dxf_type="LWPOLYLINE",
                    layer=layer,
                    color=ent.dxf.color if ent.dxf.hasattr('color') else 256,
                    linetype=ent.dxf.linetype if ent.dxf.hasattr('linetype') else 'BYLAYER',
                    handle=handle,
                    owner_handle=ent.dxf.owner if ent.dxf.hasattr('owner') else '',
                    parent_block=block_name,
                    transform=M44(),
                    bounding_box=(0.0, 0.0, 0.0, 0.0),
                    raw_properties={},
                    vertices=[Point(*p) for p in points],
                    is_closed=ent.is_closed,
                ))

            elif t == "CIRCLE":
                c = _transform_pt(ent.dxf.center.x, ent.dxf.center.y, ent.dxf.center.z)
                r = ent.dxf.radius * sx
                from core.geometry.entities import CircleEntity, Point, Matrix44 as M44
                flat.append(CircleEntity(
                    id=uuid.uuid5(insert.id, f"{block_name}:{handle}"),
                    dxf_type="CIRCLE",
                    layer=layer,
                    color=ent.dxf.color if ent.dxf.hasattr('color') else 256,
                    linetype=ent.dxf.linetype if ent.dxf.hasattr('linetype') else 'BYLAYER',
                    handle=handle,
                    owner_handle=ent.dxf.owner if ent.dxf.hasattr('owner') else '',
                    parent_block=block_name,
                    transform=M44(),
                    bounding_box=(c[0]-r, c[1]-r, c[0]+r, c[1]+r),
                    raw_properties={},
                    center=Point(*c),
                    radius=r,
                ))

            elif t == "INSERT":
                # Nested block — recurse
                from core.geometry.entities import InsertEntity as IE, Point, Matrix44 as M44
                nested_ins_pt = _transform_pt(ent.dxf.insert.x, ent.dxf.insert.y, ent.dxf.insert.z)
                nested = IE(
                    id=uuid.uuid5(insert.id, f"{block_name}:{handle}"),
                    dxf_type="INSERT",
                    layer=layer,
                    color=ent.dxf.color if ent.dxf.hasattr('color') else 256,
                    linetype=ent.dxf.linetype if ent.dxf.hasattr('linetype') else 'BYLAYER',
                    handle=handle,
                    owner_handle=ent.dxf.owner if ent.dxf.hasattr('owner') else '',
                    parent_block=block_name,
                    transform=M44(),
                    bounding_box=(0.0, 0.0, 0.0, 0.0),
                    raw_properties={},
                    block_name=ent.dxf.name,
                    insertion_point=Point(*nested_ins_pt),
                    rotation=insert.rotation + ent.dxf.rotation,
                    scale_x=sx * (ent.dxf.xscale if ent.dxf.hasattr('xscale') else 1.0),
                    scale_y=sy * (ent.dxf.yscale if ent.dxf.hasattr('yscale') else 1.0),
                    scale_z=sz * (ent.dxf.zscale if ent.dxf.hasattr('zscale') else 1.0),
                )
                _process_insert(nested, depth + 1)
            # TEXT, MTEXT, DIMENSION, HATCH: transform insertion point only
            elif t in ("TEXT", "MTEXT"):
                ip = _transform_pt(ent.dxf.insert.x, ent.dxf.insert.y, 0.0)
                from core.geometry.entities import TextEntity, MTextEntity, Point, Matrix44 as M44
                if t == "TEXT":
                    flat.append(TextEntity(
                        id=uuid.uuid5(insert.id, f"{block_name}:{handle}"),
                        dxf_type="TEXT",
                        layer=layer,
                        color=256, linetype='BYLAYER',
                        handle=handle, owner_handle='',
                        parent_block=block_name,
                        transform=M44(), bounding_box=(0,0,0,0), raw_properties={},
                        text=ent.dxf.text,
                        insertion_point=Point(*ip),
                        height=ent.dxf.height if ent.dxf.hasattr('height') else 0.0,
                        rotation=ent.dxf.rotation if ent.dxf.hasattr('rotation') else 0.0,
                    ))
                else:
                    flat.append(MTextEntity(
                        id=uuid.uuid5(insert.id, f"{block_name}:{handle}"),
                        dxf_type="MTEXT",
                        layer=layer,
                        color=256, linetype='BYLAYER',
                        handle=handle, owner_handle='',
                        parent_block=block_name,
                        transform=M44(), bounding_box=(0,0,0,0), raw_properties={},
                        text=ent.text,
                        insertion_point=Point(*ip),
                        char_height=ent.dxf.char_height if ent.dxf.hasattr('char_height') else 0.0,
                        rotation=ent.dxf.get('rotation', 0.0),
                    ))

    for insert in drawing_repo.inserts:
        _process_insert(insert)

    return flat


# ---------------------------------------------------------------------------
# Stage 3.3 — coordinate snap applied to each entity type
# ---------------------------------------------------------------------------

def _canonicalize_line(e: LineEntity, prov: CanonicalProvenance) -> CanonicalLine:
    s = _snap3((e.start.x, e.start.y, e.start.z))
    en = _snap3((e.end.x, e.end.y, e.end.z))
    dx, dy, dz = en[0]-s[0], en[1]-s[1], en[2]-s[2]
    length = math.sqrt(dx*dx + dy*dy + dz*dz)
    direction = (dx/length, dy/length, dz/length) if length > 0 else (0.0, 0.0, 0.0)
    bb = _bbox(s, en)
    geo_hash = _sha256("LINE", e.layer, str(s), str(en))
    return CanonicalLine(
        id=e.id,
        dxf_type="LINE",
        layer=e.layer,
        color=e.color,
        linetype=e.linetype,
        geometry_hash=geo_hash,
        bounding_box=bb,
        provenance=[prov],
        start=s, end=en,
        length=length,
        direction=direction,
    )


def _canonicalize_arc(e: ArcEntity, prov: CanonicalProvenance) -> CanonicalArc:
    c = _snap3((e.center.x, e.center.y, e.center.z))
    r = _snap(e.radius)
    sa = _normalize_angle(e.start_angle)
    ea = _normalize_angle(e.end_angle)
    mid = _arc_midpoint(c[0], c[1], c[2], r, sa, ea)
    mid = _snap3(mid)
    r_pad = r + 1e-9
    bb = _bbox((c[0]-r_pad, c[1]-r_pad, 0.0), (c[0]+r_pad, c[1]+r_pad, 0.0))
    geo_hash = _sha256("ARC", e.layer, str(c), str(r), str(sa), str(ea))
    return CanonicalArc(
        id=e.id,
        dxf_type="ARC",
        layer=e.layer,
        color=e.color,
        linetype=e.linetype,
        geometry_hash=geo_hash,
        bounding_box=bb,
        provenance=[prov],
        center=c, radius=r,
        start_angle=sa, end_angle=ea,
        orientation="CCW",
        midpoint=mid,
    )


def _canonicalize_circle(e: CircleEntity, prov: CanonicalProvenance) -> CanonicalCircle:
    c = _snap3((e.center.x, e.center.y, e.center.z))
    r = _snap(e.radius)
    bb = _bbox((c[0]-r, c[1]-r, 0.0), (c[0]+r, c[1]+r, 0.0))
    geo_hash = _sha256("CIRCLE", e.layer, str(c), str(r))
    return CanonicalCircle(
        id=e.id,
        dxf_type="CIRCLE",
        layer=e.layer,
        color=e.color,
        linetype=e.linetype,
        geometry_hash=geo_hash,
        bounding_box=bb,
        provenance=[prov],
        center=c, radius=r,
        area=math.pi * r * r,
        circumference=2 * math.pi * r,
    )


def _canonicalize_polyline(e: PolylineEntity, prov: CanonicalProvenance) -> CanonicalPolyline:
    verts = [_snap3((v.x, v.y, v.z)) for v in e.vertices]
    if verts:
        xs = [v[0] for v in verts]
        ys = [v[1] for v in verts]
        bb = (min(xs), min(ys), max(xs), max(ys))
    else:
        bb = (0.0, 0.0, 0.0, 0.0)
    geo_hash = _sha256("POLYLINE", e.layer, str(verts), str(e.is_closed))
    return CanonicalPolyline(
        id=e.id,
        dxf_type="POLYLINE",
        layer=e.layer,
        color=e.color,
        linetype=e.linetype,
        geometry_hash=geo_hash,
        bounding_box=bb,
        provenance=[prov],
        vertices=verts,
        is_closed=e.is_closed,
        bulges=[0.0] * (len(verts) - 1 + (1 if e.is_closed else 0)),
    )


def _canonicalize_text(e: TextEntity, prov: CanonicalProvenance) -> CanonicalText:
    ip = _snap3((e.insertion_point.x, e.insertion_point.y, e.insertion_point.z))
    geo_hash = _sha256("TEXT", e.layer, e.text, str(ip))
    bb = (ip[0], ip[1], ip[0], ip[1])
    return CanonicalText(
        id=e.id, dxf_type="TEXT", layer=e.layer, color=e.color, linetype=e.linetype,
        geometry_hash=geo_hash, bounding_box=bb, provenance=[prov],
        text=e.text, insertion_point=ip, height=_snap(e.height), rotation=_snap(e.rotation),
    )


def _canonicalize_mtext(e: MTextEntity, prov: CanonicalProvenance) -> CanonicalMText:
    ip = _snap3((e.insertion_point.x, e.insertion_point.y, e.insertion_point.z))
    geo_hash = _sha256("MTEXT", e.layer, e.text, str(ip))
    bb = (ip[0], ip[1], ip[0], ip[1])
    return CanonicalMText(
        id=e.id, dxf_type="MTEXT", layer=e.layer, color=e.color, linetype=e.linetype,
        geometry_hash=geo_hash, bounding_box=bb, provenance=[prov],
        text=e.text, insertion_point=ip, char_height=_snap(e.char_height), rotation=_snap(e.rotation),
    )


def _canonicalize_dimension(e: DimensionEntity, prov: CanonicalProvenance) -> CanonicalDimension:
    dp = _snap3((e.defpoint.x, e.defpoint.y, e.defpoint.z))
    p1 = _snap3((e.p1.x, e.p1.y, e.p1.z))
    p2 = _snap3((e.p2.x, e.p2.y, e.p2.z))
    geo_hash = _sha256("DIMENSION", e.layer, str(dp), str(p1), str(p2))
    bb = _bbox(dp, p1, p2)
    return CanonicalDimension(
        id=e.id, dxf_type="DIMENSION", layer=e.layer, color=e.color, linetype=e.linetype,
        geometry_hash=geo_hash, bounding_box=bb, provenance=[prov],
        text=e.text, measurement=e.measurement, defpoint=dp, p1=p1, p2=p2,
    )


def _canonicalize_hatch(e: HatchEntity, prov: CanonicalProvenance) -> CanonicalHatch:
    geo_hash = _sha256("HATCH", e.layer, e.pattern_name)
    bb = e.bounding_box
    return CanonicalHatch(
        id=e.id, dxf_type="HATCH", layer=e.layer, color=e.color, linetype=e.linetype,
        geometry_hash=geo_hash, bounding_box=bb, provenance=[prov],
        pattern_name=e.pattern_name, solid=e.solid,
    )


# ---------------------------------------------------------------------------
# Stage 3.5 — Deduplication
# ---------------------------------------------------------------------------

def _deduplicate(entities: list) -> list:
    """Merge entities with identical geometry_hash. Preserve all provenance."""
    seen: Dict[str, int] = {}   # hash → index in result
    result = []
    for e in entities:
        h = e.geometry_hash
        if h in seen:
            result[seen[h]].provenance.extend(e.provenance)
        else:
            seen[h] = len(result)
            result.append(e)
    return result


# ---------------------------------------------------------------------------
# Stage 3.6 — Bounding boxes
# ---------------------------------------------------------------------------

def _compute_bboxes(repo: CanonicalRepository) -> BoundingBoxReport:
    report = BoundingBoxReport()

    all_bbs = [e.bounding_box for e in repo.all_entities() if e.bounding_box != (0.0,0.0,0.0,0.0)]
    report.drawing = _bbox_union(all_bbs)

    by_block: Dict[str, List] = {}
    for e in repo.all_entities():
        block = e.provenance[0].source_block if e.provenance else None
        key = block or "__drawing__"
        by_block.setdefault(key, []).append(e.bounding_box)

    for key, bbs in by_block.items():
        report.by_block[key] = _bbox_union([b for b in bbs if b != (0.0,0.0,0.0,0.0)])

    return report


# ---------------------------------------------------------------------------
# Stage 3.8 — Validation
# ---------------------------------------------------------------------------


def _validate(repo: CanonicalRepository) -> dict:
    from dataclasses import dataclass

    errors = []
    warnings = []

    for line in repo.lines:
        if line.length < 1e-9:
            warnings.append(f"Zero-length LINE id={line.id}")
        for coord in [*line.start, *line.end]:
            if math.isnan(coord) or math.isinf(coord):
                errors.append(f"NaN/Inf coordinate in LINE id={line.id}")
                break
        if not line.provenance:
            errors.append(f"Missing provenance on LINE id={line.id}")

    for arc in repo.arcs:
        if arc.radius <= 0:
            errors.append(f"Negative/zero radius in ARC id={arc.id}")
        if arc.start_angle == arc.end_angle:
            warnings.append(f"Degenerate ARC (start==end) id={arc.id}")
        if not arc.provenance:
            errors.append(f"Missing provenance on ARC id={arc.id}")

    for circle in repo.circles:
        if circle.radius <= 0:
            errors.append(f"Negative/zero radius in CIRCLE id={circle.id}")

    for poly in repo.polylines:
        if len(poly.vertices) < 2:
            warnings.append(f"Empty/single-vertex POLYLINE id={poly.id}")

    return {"critical_errors": errors, "warnings": warnings}


# ---------------------------------------------------------------------------
# Main canonicalize entry point
# ---------------------------------------------------------------------------

def canonicalize(
    drawing_repo: DrawingRepository,
    dxf_path: str,
    reader_name: str = "DXFReader",
) -> tuple[CanonicalRepository, dict]:
    """
    Runs all 8 stages and returns (CanonicalRepository, validation_report).
    """
    import ezdxf as _ezdxf

    doc = _ezdxf.readfile(dxf_path)
    drawing_filename = drawing_repo.identity.drawing_number + "_" + drawing_repo.identity.view

    canon_repo = CanonicalRepository(drawing_filename=drawing_filename)

    # --- Stage 3.1 + 3.2: Explode INSERTs → flat list of GeometryEntity ---
    flat_entities = _explode_inserts(doc, drawing_repo, reader_name, drawing_filename)

    # --- Stages 3.3 + 3.4 + 3.7: Canonicalize each entity ---
    for entity in flat_entities:
        prov = CanonicalProvenance(
            source_entity_uuid=entity.id,
            source_handle=entity.handle,
            source_block=entity.parent_block,
            source_reader=reader_name,
            source_drawing=drawing_filename,
        )

        if isinstance(entity, LineEntity):
            canon_repo.lines.append(_canonicalize_line(entity, prov))
        elif isinstance(entity, ArcEntity):
            canon_repo.arcs.append(_canonicalize_arc(entity, prov))
        elif isinstance(entity, CircleEntity):
            canon_repo.circles.append(_canonicalize_circle(entity, prov))
        elif isinstance(entity, PolylineEntity):
            canon_repo.polylines.append(_canonicalize_polyline(entity, prov))
        elif isinstance(entity, TextEntity):
            canon_repo.texts.append(_canonicalize_text(entity, prov))
        elif isinstance(entity, MTextEntity):
            canon_repo.mtexts.append(_canonicalize_mtext(entity, prov))
        elif isinstance(entity, DimensionEntity):
            canon_repo.dimensions.append(_canonicalize_dimension(entity, prov))
        elif isinstance(entity, HatchEntity):
            canon_repo.hatches.append(_canonicalize_hatch(entity, prov))
        # UnknownEntity — log only

    # --- Stage 3.5: Deduplicate ---
    canon_repo.lines      = _deduplicate(canon_repo.lines)
    canon_repo.arcs       = _deduplicate(canon_repo.arcs)
    canon_repo.circles    = _deduplicate(canon_repo.circles)
    canon_repo.polylines  = _deduplicate(canon_repo.polylines)
    canon_repo.texts      = _deduplicate(canon_repo.texts)
    canon_repo.mtexts     = _deduplicate(canon_repo.mtexts)
    canon_repo.dimensions = _deduplicate(canon_repo.dimensions)
    canon_repo.hatches    = _deduplicate(canon_repo.hatches)

    # --- Stage 3.6: Bounding boxes ---
    canon_repo.bbox_report = _compute_bboxes(canon_repo)

    # --- Stage 3.8: Validation ---
    validation = _validate(canon_repo)

    return canon_repo, validation
