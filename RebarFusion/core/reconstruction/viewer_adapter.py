from __future__ import annotations

from dataclasses import asdict


class ReconstructionViewerAdapter:
    def to_payload(self, assemblies, meshes):
        return {
            "assemblies": [asdict(assembly) for assembly in assemblies],
            "meshes": [asdict(mesh) for mesh in meshes],
        }
