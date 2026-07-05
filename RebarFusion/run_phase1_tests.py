import argparse
import os
import json
import uuid
import time
import shutil
from dataclasses import asdict
from core.project import DrawingProject

class UUIDEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, uuid.UUID):
            return str(obj)
        if hasattr(obj, 'as_tuple'):
            return obj.as_tuple()
        if hasattr(obj, '__dataclass_fields__'):
            return {k: getattr(obj, k) for k in obj.__dataclass_fields__}
        return super().default(obj)

def run_tests():
    # Setup test_project directory
    os.makedirs("test_project", exist_ok=True)
    
    # Copy from ../DRAWINGS to test_project
    files_to_copy = [
        "PW-GF-02(M1).dwg", "PW-GF-02(M2).dwg", "PW-GF-02(R).dwg",
        "PW-GF-09(M1).dwg", "PW-GF-09(M2).dwg", "PW-GF-09(R).dwg",
        "SS-GF-01(M).dxf", "SS-GF-01(R).dwg",
        "PW-GF-09(M1) .pdf", "PW-GF-09(M2) .pdf", "PW-GF-09(R) .pdf"
    ]
    
    for f in files_to_copy:
        src = os.path.join("../DRAWINGS", f)
        dst = os.path.join("test_project", f.replace(" .pdf", ".pdf"))
        if os.path.exists(src):
            shutil.copy2(src, dst)
            
    # Test 2: Duplicate detection
    shutil.copy2("test_project/PW-GF-02(M1).dwg", "test_project/PW-GF-02(M1)-copy.dwg")
    
    # Test 3: Rename
    shutil.copy2("test_project/PW-GF-02(M1).dwg", "test_project/banana.dwg")
    
    # Test 4: Missing drawing
    # Simulate missing drawing by omitting SS-GF-01(M).dwg since it's not in the copied list, 
    # but the relationships should show holes if it expects a set.
    
    project = DrawingProject("Test Project")
    manifest = project.load_directory("test_project")
    
    print("\n")
    project.report_health()
    
    # Dump outputs
    os.makedirs("debug/phase01", exist_ok=True)
    
    with open("debug/phase01/manifest.json", "w") as f:
        json.dump(asdict(manifest), f, indent=2, cls=UUIDEncoder)
        
    stats_data = {fname: asdict(d.statistics) for fname, d in manifest.drawings.items()}
    with open("debug/phase01/statistics.json", "w") as f:
        json.dump(stats_data, f, indent=2, cls=UUIDEncoder)
        
    val_data = {
        fname: {
            "errors": d.validation_errors, 
            "warnings": d.validation_warnings
        } for fname, d in manifest.drawings.items()
    }
    with open("debug/phase01/validation.json", "w") as f:
        json.dump(val_data, f, indent=2, cls=UUIDEncoder)
        
    with open("debug/phase01/project_graph.json", "w") as f:
        json.dump(manifest.relationships, f, indent=2, cls=UUIDEncoder)
        
    dup_data = {fname: d.duplicate_of for fname, d in manifest.drawings.items() if d.duplicate_of}
    with open("debug/phase01/duplicates.json", "w") as f:
        json.dump(dup_data, f, indent=2, cls=UUIDEncoder)
        
    meta_data = {fname: d.metadata for fname, d in manifest.drawings.items() if hasattr(d, 'metadata')}
    with open("debug/phase01/metadata.json", "w") as f:
        json.dump(meta_data, f, indent=2, cls=UUIDEncoder)
        
    reg_data = {fname: asdict(d.registration) for fname, d in manifest.drawings.items()}
    with open("debug/phase01/registration.json", "w") as f:
        json.dump(reg_data, f, indent=2, cls=UUIDEncoder)
        
    print("\nPhase 1 outputs generated in debug/phase01/")

if __name__ == "__main__":
    run_tests()
