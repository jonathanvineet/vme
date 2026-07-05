from __future__ import annotations

import csv
import json
import math
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import ezdxf
import matplotlib.pyplot as plt
import numpy as np
from ezdxf import bbox as ezbbox


ALLOWED_ENTITY_TYPES = {"LINE", "ARC", "LWPOLYLINE", "POLYLINE"}
IGNORED_ENTITY_TYPES = {"TEXT", "MTEXT", "HATCH", "CIRCLE"}


@dataclass
class InsertInstance:
    id: int
    block_name: str
    family_name: str
    variant_name: str
    insert: List[float]
    rotation: float
    xscale: float
    yscale: float
    zscale: float
    layer: str
    block_entity_counts: Dict[str, int] = field(default_factory=dict)
    bbox: Optional[List[float]] = None
    length: float = 0.0
    width: float = 0.0
    height: float = 0.0
    center: Optional[List[float]] = None
    orientation: str = "Unknown"
    geometry_signature: Optional[List[float]] = None
    family_id: Optional[str] = None


@dataclass
class FamilySummary:
    family_id: str
    family_name: str
    block_name: str
    block_names: List[str]
    copies: int
    avg_spacing: Optional[float]
    spacing_values: List[float]
    length: float
    width: float
    height: float
    bbox: Optional[List[float]]
    center: Optional[List[float]]
    orientation: str
    instance_ids: List[int] = field(default_factory=list)


@dataclass
class ExtractionResult:
    drawing: str
    instances: List[InsertInstance]
    families: List[FamilySummary]


class RebarExtractor:
    def __init__(self, drawing_path: str, output_dir: str = "output"):
        self.drawing_path = Path(drawing_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def run(self) -> ExtractionResult:
        doc = ezdxf.readfile(str(self.drawing_path))
        msp = doc.modelspace()

        inserts = self._collect_inserts(doc, msp)
        families = self._summarize_families(inserts)

        result = ExtractionResult(
            drawing=str(self.drawing_path),
            instances=inserts,
            families=families,
        )

        self.export_family_debug(result)
        self.export_csv(result)
        self.export_json(result)
        self.export_preview(result)

        try:
            from debug_overlay import DebugOverlay

            DebugOverlay().draw(self._families_for_overlay(result), str(self.output_dir / "families.png"))
        except Exception as exc:
            print(f"Debug overlay failed: {exc}")

        return result

    def _collect_inserts(self, doc, msp) -> List[InsertInstance]:
        instances: List[InsertInstance] = []
        instance_id = 1

        for entity in msp:
            if entity.dxftype() != "INSERT":
                continue
            if entity.dxf.layer != "S-RBAR":
                continue

            block_name = entity.dxf.name
            base_part_id, variant_name = self._split_block_name(block_name)
            family_name = base_part_id
            rotation = float(getattr(entity.dxf, "rotation", 0.0) or 0.0)
            xscale = float(getattr(entity.dxf, "xscale", 1.0) or 1.0)
            yscale = float(getattr(entity.dxf, "yscale", 1.0) or 1.0)
            zscale = float(getattr(entity.dxf, "zscale", 1.0) or 1.0)
            insert_pt = self._vec3_to_list(entity.dxf.insert)

            block = doc.blocks.get(block_name)
            block_entity_counts: Dict[str, int] = {}
            if block is not None:
                for block_entity in block:
                    block_entity_counts[block_entity.dxftype()] = block_entity_counts.get(block_entity.dxftype(), 0) + 1

            virtual_entities = list(entity.virtual_entities())
            transformed_bbox = self._bbox_to_list(self._safe_extents(virtual_entities))
            total_length = self._measure_entities(virtual_entities)
            bbox_dims = self._bbox_dims(transformed_bbox)
            center = self._bbox_center(transformed_bbox)
            orientation = self._orientation_from_dims(*bbox_dims)
            geometry_signature = [
                round(total_length, 1),
                round(bbox_dims[0], 1),
                round(bbox_dims[1], 1),
                round(self._rotation_normalize(rotation), 1),
            ]

            instances.append(
                InsertInstance(
                    id=instance_id,
                    block_name=block_name,
                    family_name=family_name,
                    variant_name=variant_name,
                    insert=insert_pt,
                    rotation=rotation,
                    xscale=xscale,
                    yscale=yscale,
                    zscale=zscale,
                    layer=entity.dxf.layer,
                    block_entity_counts=block_entity_counts,
                    bbox=transformed_bbox,
                    length=round(total_length, 2),
                    width=round(bbox_dims[0], 2),
                    height=round(bbox_dims[1], 2),
                    center=center,
                    orientation=orientation,
                    geometry_signature=geometry_signature,
                )
            )
            instance_id += 1

        return instances

    def _summarize_families(self, instances: List[InsertInstance]) -> List[FamilySummary]:
        grouped: Dict[Tuple[str, Tuple[float, ...]], List[InsertInstance]] = {}
        for instance in instances:
            signature = tuple(instance.geometry_signature or [])
            key = (instance.family_name, signature)
            grouped.setdefault(key, []).append(instance)

        summaries: List[FamilySummary] = []
        for family_index, ((family_name, signature), family_instances) in enumerate(
            sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0][0], item[0][1]))
        , start=1):
            spacing_values = self._compute_spacing(family_instances)
            lengths = [instance.length for instance in family_instances]
            widths = [instance.width for instance in family_instances]
            heights = [instance.height for instance in family_instances]
            exact_block_names = sorted({instance.block_name for instance in family_instances})
            family_id = f"F{family_index}"

            union_bbox = self._union_bbox([instance.bbox for instance in family_instances if instance.bbox])
            center = self._bbox_center(union_bbox)
            orientation = self._major_orientation(family_instances)

            for instance in family_instances:
                instance.family_id = family_id

            summaries.append(
                FamilySummary(
                    family_id=family_id,
                    family_name=family_name,
                    block_name=family_instances[0].block_name,
                    block_names=exact_block_names,
                    copies=len(family_instances),
                    avg_spacing=round(float(np.mean(spacing_values)), 2) if spacing_values else None,
                    spacing_values=[round(value, 2) for value in spacing_values],
                    length=round(float(np.mean(lengths)), 2) if lengths else 0.0,
                    width=round(float(np.mean(widths)), 2) if widths else 0.0,
                    height=round(float(np.mean(heights)), 2) if heights else 0.0,
                    bbox=union_bbox,
                    center=center,
                    orientation=orientation,
                    instance_ids=[instance.id for instance in family_instances],
                )
            )

        return summaries

    def export_family_debug(self, result: ExtractionResult) -> None:
        csv_path = self.output_dir / "family_debug.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow([
                "family_id",
                "insert_id",
                "block_name",
                "base_part_id",
                "variant_name",
                "length",
                "width",
                "height",
                "rotation",
                "insert_x",
                "insert_y",
                "bbox",
                "geometry_signature",
            ])
            for instance in result.instances:
                writer.writerow([
                    instance.family_id,
                    instance.id,
                    instance.block_name,
                    instance.family_name,
                    instance.variant_name,
                    instance.length,
                    instance.width,
                    instance.height,
                    instance.rotation,
                    instance.insert[0],
                    instance.insert[1],
                    instance.bbox,
                    instance.geometry_signature,
                ])

    def _compute_spacing(self, instances: List[InsertInstance]) -> List[float]:
        if len(instances) < 2:
            return []

        points = np.array([[instance.insert[0], instance.insert[1]] for instance in instances], dtype=float)
        if len(points) < 2:
            return []

        centered = points - points.mean(axis=0, keepdims=True)
        cov = np.cov(centered.T)
        eigenvalues, eigenvectors = np.linalg.eigh(cov)
        axis = eigenvectors[:, np.argmax(eigenvalues)]

        projections = points @ axis
        projections = np.unique(np.round(projections, 6))
        projections.sort()
        diffs = np.diff(projections)
        return [float(value) for value in diffs if value > 1e-6]

    def export_csv(self, result: ExtractionResult) -> None:
        csv_path = self.output_dir / "rebars.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow([
                "family_name",
                "block_name",
                "copies",
                "avg_spacing",
                "length",
                "width",
                "height",
                "orientation",
                "bbox",
                "center",
                "instance_ids",
            ])
            for family in result.families:
                writer.writerow([
                    family.family_name,
                    family.block_name,
                    family.copies,
                    family.avg_spacing,
                    family.length,
                    family.width,
                    family.height,
                    family.orientation,
                    family.bbox,
                    family.center,
                    family.instance_ids,
                ])

    def export_json(self, result: ExtractionResult) -> None:
        json_path = self.output_dir / "rebars.json"
        payload = {
            "drawing": result.drawing,
            "instance_count": len(result.instances),
            "family_count": len(result.families),
            "instances": [asdict(instance) for instance in result.instances],
            "families": [asdict(family) for family in result.families],
        }
        with open(json_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)

    def export_preview(self, result: ExtractionResult) -> None:
        if not result.instances:
            return

        preview_path = self.output_dir / "rebars.png"
        fig, ax = plt.subplots(figsize=(16, 12), dpi=120)

        all_boxes = [instance.bbox for instance in result.instances if instance.bbox]
        union_bbox = self._union_bbox(all_boxes)
        if union_bbox is None:
            return

        minx, miny, maxx, maxy = union_bbox
        pad_x = max((maxx - minx) * 0.05, 10.0)
        pad_y = max((maxy - miny) * 0.05, 10.0)

        ax.set_xlim(minx - pad_x, maxx + pad_x)
        ax.set_ylim(miny - pad_y, maxy + pad_y)
        ax.set_aspect("equal")
        ax.invert_yaxis()
        ax.axis("off")

        colors = plt.cm.tab20(np.linspace(0, 1, max(1, len(result.families))))
        family_colors = {
            family.family_name: colors[index % len(colors)]
            for index, family in enumerate(result.families)
        }

        for instance in result.instances:
            bbox = instance.bbox
            if not bbox:
                continue
            minx, miny, maxx, maxy = bbox
            xs = [minx, maxx, maxx, minx, minx]
            ys = [miny, miny, maxy, maxy, miny]
            color = family_colors.get(instance.family_name, (0.2, 0.4, 0.8, 1.0))
            ax.plot(xs, ys, color=color, linewidth=1.5)
            if instance.center:
                ax.text(
                    instance.center[0],
                    instance.center[1],
                    instance.family_name,
                    fontsize=6,
                    color=color,
                    ha="center",
                    va="center",
                )

        fig.tight_layout(pad=0)
        fig.savefig(preview_path, bbox_inches="tight", pad_inches=0.05)
        plt.close(fig)

    def _measure_entities(self, entities) -> float:
        total = 0.0
        for entity in entities:
            typ = entity.dxftype()
            if typ == "LINE":
                start = entity.dxf.start
                end = entity.dxf.end
                total += math.dist((start.x, start.y), (end.x, end.y))
            elif typ == "ARC":
                total += self._arc_length(entity)
            elif typ in {"POLYLINE", "LWPOLYLINE"}:
                points = self._polyline_points(entity)
                total += self._path_length(points)
        return total

    def _polyline_points(self, entity) -> List[Tuple[float, float]]:
        if entity.dxftype() == "LWPOLYLINE":
            return [(float(x), float(y)) for x, y, *_ in entity.get_points()]
        if entity.dxftype() == "POLYLINE":
            points = []
            for vertex in entity.vertices:
                points.append((float(vertex.dxf.location.x), float(vertex.dxf.location.y)))
            return points
        if hasattr(entity, "flattening"):
            return [(float(point.x), float(point.y)) for point in entity.flattening(0.5)]
        return []

    def _arc_length(self, entity) -> float:
        start_angle = float(entity.dxf.start_angle)
        end_angle = float(entity.dxf.end_angle)
        radius = float(entity.dxf.radius)
        delta = end_angle - start_angle
        if delta < 0:
            delta += 360.0
        return math.radians(delta) * radius

    def _path_length(self, points: Sequence[Tuple[float, float]]) -> float:
        if len(points) < 2:
            return 0.0
        total = 0.0
        for start, end in zip(points[:-1], points[1:]):
            total += math.dist(start, end)
        return total

    def _safe_extents(self, entities):
        try:
            return ezbbox.extents(entities)
        except Exception:
            return None

    def _bbox_to_list(self, bbox) -> Optional[List[float]]:
        if bbox is None:
            return None
        min_pt, max_pt = bbox
        return [float(min_pt.x), float(min_pt.y), float(max_pt.x), float(max_pt.y)]

    def _bbox_dims(self, bbox: Optional[List[float]]) -> Tuple[float, float]:
        if not bbox:
            return 0.0, 0.0
        minx, miny, maxx, maxy = bbox
        return abs(maxx - minx), abs(maxy - miny)

    def _bbox_center(self, bbox: Optional[List[float]]) -> Optional[List[float]]:
        if not bbox:
            return None
        minx, miny, maxx, maxy = bbox
        return [round((minx + maxx) / 2.0, 3), round((miny + maxy) / 2.0, 3)]

    def _orientation_from_dims(self, width: float, height: float) -> str:
        if width == 0.0 and height == 0.0:
            return "Unknown"
        if width >= height * 1.2:
            return "Horizontal"
        if height >= width * 1.2:
            return "Vertical"
        return "Diagonal"

    def _major_orientation(self, family_instances: List[InsertInstance]) -> str:
        orientations = [instance.orientation for instance in family_instances]
        counts = {orientation: orientations.count(orientation) for orientation in set(orientations)}
        return max(counts, key=counts.get)

    def _union_bbox(self, bboxes: Iterable[Optional[List[float]]]) -> Optional[List[float]]:
        filtered = [bbox for bbox in bboxes if bbox]
        if not filtered:
            return None
        minx = min(bbox[0] for bbox in filtered)
        miny = min(bbox[1] for bbox in filtered)
        maxx = max(bbox[2] for bbox in filtered)
        maxy = max(bbox[3] for bbox in filtered)
        return [round(minx, 3), round(miny, 3), round(maxx, 3), round(maxy, 3)]

    def _vec3_to_list(self, value) -> List[float]:
        return [float(value.x), float(value.y), float(getattr(value, "z", 0.0))]

    def _family_name(self, block_name: str) -> str:
        match = re.search(r"Rebar Bar - Part\s+([0-9]+)", block_name)
        if match:
            return match.group(1)
        return block_name

    def _split_block_name(self, block_name: str) -> Tuple[str, str]:
        match = re.search(r"Rebar Bar - Part\s+([0-9]+)-(.+)$", block_name)
        if match:
            return match.group(1), match.group(2)
        base = self._family_name(block_name)
        return base, block_name

    def _families_for_overlay(self, result: ExtractionResult) -> List[Dict[str, object]]:
        overlay_families: Dict[str, Dict[str, object]] = {}
        for summary in result.families:
            overlay_families[summary.family_id] = {
                "family": summary.family_id,
                "count": summary.copies,
                "bars": [],
            }

        for instance in result.instances:
            if instance.family_id is None:
                continue
            overlay_families[instance.family_id]["bars"].append(
                {
                    "bbox": instance.bbox,
                    "insert": instance.insert,
                    "family_id": instance.family_id,
                    "id": instance.id,
                    "direction": instance.orientation,
                }
            )

        return list(overlay_families.values())

    def _rotation_normalize(self, rotation: float) -> float:
        return rotation % 180.0
