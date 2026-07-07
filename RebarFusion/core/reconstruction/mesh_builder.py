from __future__ import annotations

import uuid
from typing import Iterable, List, Tuple

from core.reconstruction.models import ReconstructionMesh
from core.reconstruction.triangulator import BarTriangulator


class MeshBuilder:
    def __init__(self, triangulator: BarTriangulator | None = None, segments: int = 12):
        self.triangulator = triangulator or BarTriangulator(segments=segments)

    def build_bar_mesh(self, bar, assembly_uuid) -> ReconstructionMesh:
        vertices, faces = self.triangulator.triangulate(bar)
        mesh_uuid = uuid.uuid5(uuid.NAMESPACE_URL, f"mesh|{assembly_uuid}|{bar.uuid}")
        return ReconstructionMesh(
            uuid=mesh_uuid,
            assembly_uuid=assembly_uuid,
            bar_uuid=bar.uuid,
            vertices=vertices,
            faces=faces,
            confidence=bar.confidence,
        )

    def build_meshes(self, assemblies) -> List[ReconstructionMesh]:
        meshes: List[ReconstructionMesh] = []
        for assembly in assemblies:
            for bar in assembly.bars:
                meshes.append(self.build_bar_mesh(bar, assembly.uuid))
        return meshes

    def write_obj(self, path: str, meshes: Iterable[ReconstructionMesh]):
        vertex_offset = 1
        with open(path, "w", encoding="utf-8") as f:
            f.write("# RebarFusion Phase 10 reconstruction mesh\n")
            for mesh in meshes:
                f.write(f"o bar_{mesh.bar_uuid}\n")
                for x, y, z in mesh.vertices:
                    f.write(f"v {x:.4f} {y:.4f} {z:.4f}\n")
                for a, b, c in mesh.faces:
                    f.write(f"f {a + vertex_offset} {b + vertex_offset} {c + vertex_offset}\n")
                vertex_offset += len(mesh.vertices)

    def write_ply(self, path: str, meshes: Iterable[ReconstructionMesh]):
        all_vertices = []
        all_faces = []
        offset = 0
        for mesh in meshes:
            all_vertices.extend(mesh.vertices)
            all_faces.extend((a + offset, b + offset, c + offset) for a, b, c in mesh.faces)
            offset += len(mesh.vertices)

        with open(path, "w", encoding="utf-8") as f:
            f.write("ply\n")
            f.write("format ascii 1.0\n")
            f.write("comment RebarFusion Phase 10 reconstruction mesh\n")
            f.write(f"element vertex {len(all_vertices)}\n")
            f.write("property float x\n")
            f.write("property float y\n")
            f.write("property float z\n")
            f.write(f"element face {len(all_faces)}\n")
            f.write("property list uchar int vertex_indices\n")
            f.write("end_header\n")
            for x, y, z in all_vertices:
                f.write(f"{x:.4f} {y:.4f} {z:.4f}\n")
            for a, b, c in all_faces:
                f.write(f"3 {a} {b} {c}\n")
