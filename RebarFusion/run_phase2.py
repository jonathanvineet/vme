import argparse
import os
import json
import uuid
import sys
from dataclasses import asdict
from core.project import DrawingProject
from core.geometry.repository import ProjectRepository

class UUIDEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, uuid.UUID):
            return str(obj)
        if hasattr(obj, 'as_tuple'):
            return obj.as_tuple()
        if hasattr(obj, '__dataclass_fields__'):
            return {k: getattr(obj, k) for k in obj.__dataclass_fields__}
        
        # Fallback for ezdxf Vec3 or other complex properties
        try:
            return super().default(obj)
        except TypeError:
            return str(obj)

def run_phase2(directory: str):
    # Phase 1
    project = DrawingProject()
    manifest = project.load_directory(directory)
    
    # Check health gate
    corrupt = sum(1 for d in manifest.drawings.values() if d.validation_errors)
    if corrupt > 0:
        print("\n[ERROR] Phase 1 Health Check Failed. Corrupt drawings detected.")
        sys.exit(1)
        
    print("\nPhase 1 Passed. Proceeding to Phase 2: Geometry Translation...")
    
    # Phase 2
    project_repo = ProjectRepository()
    
    for filename, drawing in manifest.drawings.items():
        if drawing.duplicate_of:
            continue
            
        if not drawing.capabilities.geometry:
            print(f"Skipping {filename}: No geometry capability detected (likely unsupported format).")
            continue
            
        print(f"Translating {filename}...")
        
        reader = project._get_reader(drawing.filepath)
        if not reader:
            print(f"  [ERROR] No reader for {filename}")
            continue
            
        repo = reader.read_geometry(drawing.filepath, drawing.identity)
        project_repo.add_drawing(repo)
        
        report = repo.generate_translation_report()
        
        # Save output per drawing
        out_dir = os.path.join(directory, "ProjectRepository", f"DrawingRepository_{drawing.identity.drawing_number}_{drawing.identity.view}")
        os.makedirs(out_dir, exist_ok=True)
        
        # Dump report
        report_path = os.path.join(out_dir, "translation_report.json")
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)
            
        # Dump geometry
        geom_path = os.path.join(out_dir, "geometry.json")
        with open(geom_path, "w") as f:
            serializable = {
                "lines": [asdict(e) for e in repo.lines],
                "arcs": [asdict(e) for e in repo.arcs],
                "polylines": [asdict(e) for e in repo.polylines],
                "inserts": [asdict(e) for e in repo.inserts],
                "texts": [asdict(e) for e in repo.texts],
                "mtexts": [asdict(e) for e in repo.mtexts],
                "dimensions": [asdict(e) for e in repo.dimensions],
                "hatches": [asdict(e) for e in repo.hatches],
                "circles": [asdict(e) for e in repo.circles],
                "unknowns": [asdict(e) for e in repo.unknowns]
            }
            json.dump(serializable, f, indent=2, cls=UUIDEncoder)
            
        from viewer.gallery import generate_gallery
        generate_gallery(repo, out_dir, max_samples=3)
        
        print(f"  Translated {sum(report.values())} entities -> {out_dir}")
        print("  Translation Report:")
        for k, v in report.items():
            if v > 0:
                print(f"    {k:<10}: {v}")
                
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory")
    args = parser.parse_args()
    run_phase2(args.directory)
