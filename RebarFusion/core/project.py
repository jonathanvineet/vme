from __future__ import annotations
import os
import hashlib
import time
import json
import uuid
import re
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Tuple, Optional
from uuid import UUID

@dataclass(frozen=True)
class DrawingIdentity:
    uuid: UUID
    drawing_number: str      # e.g., "PW-GF-02"
    view: str                # e.g., "M1", "M2", "R"
    floor: str               # e.g., "GF"
    element: str             # e.g., "PW"
    revision: str            # e.g., "A", "B", "1", "Latest"
    confidence: float        # 0.0-1.0 (based on filename vs titleblock match)

@dataclass
class DrawingRegistration:
    origin: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: float = 0.0
    scale: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    translation: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    confidence: float = 0.0

@dataclass
class DrawingCapabilities:
    geometry: bool = False
    dimensions: bool = False
    annotations: bool = False
    blocks: bool = False
    layers: bool = False
    splines: bool = False
    schedule: bool = False
    sections: bool = False

@dataclass
class DrawingStatistics:
    entity_counts: dict = field(default_factory=dict)
    bounding_box: tuple = (0.0, 0.0, 0.0, 0.0)
    extents: tuple = (0.0, 0.0)
    entity_density: float = 0.0
    average_entity_size: float = 0.0
    dominant_layers: list = field(default_factory=list)
    dominant_blocks: list = field(default_factory=list)

@dataclass
class Drawing:
    identity: DrawingIdentity
    filepath: str
    filename: str
    extension: str
    checksum: str
    capabilities: DrawingCapabilities = field(default_factory=DrawingCapabilities)
    statistics: DrawingStatistics = field(default_factory=DrawingStatistics)
    registration: DrawingRegistration = field(default_factory=DrawingRegistration)
    coordinate_system: dict = field(default_factory=dict)
    validation_errors: list = field(default_factory=list)
    validation_warnings: list = field(default_factory=list)
    duplicate_of: Optional[str] = None

@dataclass
class BuildInfo:
    engine_version: str
    git_commit: str
    python_version: str
    timestamp: str

@dataclass
class ProjectManifest:
    project_uuid: str
    project_name: str
    coordinate_system: str
    units: str
    drawings: Dict[str, Drawing] = field(default_factory=dict)
    relationships: dict = field(default_factory=dict)
    build_info: BuildInfo = None


def _compute_checksum(filepath: str) -> str:
    sha256 = hashlib.sha256()
    try:
        with open(filepath, 'rb') as f:
            for block in iter(lambda: f.read(65536), b''):
                sha256.update(block)
        return sha256.hexdigest()
    except Exception:
        return ""

class DrawingProject:
    def __init__(self, name: str = "Unnamed Project"):
        self.project_uuid = str(uuid.uuid4())
        self.project_name = name
        self.drawings: Dict[str, Drawing] = {}
        self.manifest: Optional[ProjectManifest] = None
        
        # Reader registry. DWGReader is not a second parser -- it converts
        # via ODA File Converter (tools/oda/) and delegates to DXFReader,
        # and its can_read() returns False when the converter binary is
        # absent, so environments without it degrade to the previous
        # "No reader available" behavior instead of erroring.
        from core.readers.dxf_reader import DXFReader
        from core.readers.dwg_reader import DWGReader
        self.readers = [DXFReader(), DWGReader()]
        
    def _get_reader(self, filepath: str):
        for r in self.readers:
            if r.can_read(filepath):
                return r
        return None

    def load_directory(self, directory: str) -> ProjectManifest:
        """
        Phase 1: Ingests all drawings, validates, extracts metadata, 
        identifies duplicates, and generates the ProjectManifest.
        """
        from core.identity_parser import parse_identity
        
        print(f"Scanning directory: {directory}")
        
        checksum_map = {}
        
        for root, _, files in os.walk(directory):
            for file in files:
                ext = file.split('.')[-1].lower()
                if ext not in ('dxf', 'dwg', 'pdf'):
                    continue
                    
                filepath = os.path.join(root, file)
                checksum = _compute_checksum(filepath)
                
                duplicate_of = None
                if checksum in checksum_map:
                    duplicate_of = checksum_map[checksum]
                else:
                    checksum_map[checksum] = file
                
                identity = parse_identity(file)
                
                drawing = Drawing(
                    identity=identity,
                    filepath=filepath,
                    filename=file,
                    extension=ext,
                    checksum=checksum,
                    duplicate_of=duplicate_of
                )
                
                # If it's not a duplicate, try to read metadata
                if not duplicate_of:
                    reader = self._get_reader(filepath)
                    if reader:
                        try:
                            drawing.metadata = reader.read_metadata(filepath)
                            drawing.statistics = reader.read_statistics(filepath)
                            drawing.capabilities = reader.read_capabilities(filepath)
                            drawing.registration = reader.read_registration(filepath)
                            drawing.coordinate_system = {"units": drawing.metadata.get("units", "unknown")}
                        except Exception as e:
                            drawing.validation_errors.append(f"Failed to read file: {e}")
                    else:
                        drawing.validation_warnings.append(f"No reader available for extension: {ext}")
                        
                self.drawings[file] = drawing
                
        relationships = self._build_relationship_graph()
        
        self.manifest = ProjectManifest(
            project_uuid=self.project_uuid,
            project_name=self.project_name,
            coordinate_system="World",  # to be determined holistically
            units="mm",                 # to be normalized
            drawings=self.drawings,
            relationships=relationships,
            build_info=BuildInfo(
                engine_version="0.1.0",
                git_commit="unknown",
                python_version="3.14",
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            )
        )
        
        return self.manifest
        
    def _build_relationship_graph(self) -> dict:
        """
        Builds Project -> Floor -> Element -> Drawing Set -> Drawing
        """
        graph = {}
        for d in self.drawings.values():
            floor = d.identity.floor
            element = d.identity.element
            drawing_set = d.identity.drawing_number
            
            if floor not in graph:
                graph[floor] = {}
            if element not in graph[floor]:
                graph[floor][element] = {}
            if drawing_set not in graph[floor][element]:
                graph[floor][element][drawing_set] = []
                
            graph[floor][element][drawing_set].append(d.filename)
            
        return graph
        
    def report_health(self):
        """Generates the Phase 1 Project Health Report."""
        if not self.manifest:
            print("Project not loaded.")
            return
            
        total = len(self.drawings)
        dxf = sum(1 for d in self.drawings.values() if d.extension == 'dxf')
        dwg = sum(1 for d in self.drawings.values() if d.extension == 'dwg')
        pdf = sum(1 for d in self.drawings.values() if d.extension == 'pdf')
        
        duplicates = sum(1 for d in self.drawings.values() if d.duplicate_of)
        unreadable = sum(1 for d in self.drawings.values() if d.validation_errors)
        unknown = sum(1 for d in self.drawings.values() if not d.duplicate_of and d.identity.floor == 'Unknown')
        
        floors = set(d.identity.floor for d in self.drawings.values() if d.identity.floor != "Unknown")
        floors_str = ", ".join(floors) if floors else "None"
        
        elements = set(d.identity.drawing_number for d in self.drawings.values() if d.identity.drawing_number != "Unknown")
        elements_str = ", ".join(sorted(list(elements))) if elements else "None"
        
        units = set(d.coordinate_system.get("units") for d in self.drawings.values() if d.coordinate_system)
        units_str = ", ".join(units) if units else "unknown"
        
        coord_systems = 1 if units else 0
        
        print("=========================================================")
        print("PROJECT SUMMARY")
        print("=========================================================")
        print(f"\nProject")
        print(f"{self.project_name}")
        print(f"\nDrawings")
        print(f"{total}")
        print(f"\nDXF")
        print(f"{dxf}")
        print(f"\nDWG")
        print(f"{dwg}")
        print(f"\nPDF")
        print(f"{pdf}")
        print(f"\nDuplicate Files")
        print(f"{duplicates}")
        print(f"\nUnreadable")
        print(f"{unreadable}")
        print(f"\nUnknown")
        print(f"{unknown}")
        print(f"\nFloors")
        print(f"{floors_str}")
        print(f"\nElements")
        print(f"{elements_str}")
        print(f"\nCoordinate Systems")
        print(f"{coord_systems}")
        print(f"\nUnits")
        print(f"{units_str}")
        print(f"\nReady")
        print(f"{'YES' if unreadable == 0 else 'NO'}")
        print("\n=========================================================")
