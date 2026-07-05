import argparse
import os
import json
import uuid
import time
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

def dump_snapshot(filename: str, data: list):
    os.makedirs("debug", exist_ok=True)
    filepath = os.path.join("debug", filename)
    with open(filepath, 'w') as f:
        serializable = []
        for e in data:
            if hasattr(e, '__dataclass_fields__'):
                d = asdict(e)
            else:
                d = e
            serializable.append(d)
        json.dump(serializable, f, indent=2, cls=UUIDEncoder)
    print(f"  Snapshot written to {filepath}")

def main():
    parser = argparse.ArgumentParser(description="RebarFusion Pipeline")
    parser.add_argument("directory", help="Path to project directory containing DXF/DWG/PDF files")
    parser.add_argument("--debug", action="store_true", help="Dump debug snapshots")
    args = parser.parse_args()

    project = DrawingProject()
    manifest = project.load_directory(args.directory)
    
    print("\n")
    project.report_health()
    
    if args.debug:
        os.makedirs("debug/phase01", exist_ok=True)
        manifest_path = os.path.join("debug", "phase01", "manifest.json")
        with open(manifest_path, 'w') as f:
            json.dump(asdict(manifest), f, indent=2, cls=UUIDEncoder)
        print(f"\nManifest dumped to {manifest_path}")

        # Also write the project.lock
        lock_path = "project.lock"
        with open(lock_path, 'w') as f:
            lock_data = {
                "phase": 1,
                "validated": len(manifest.drawings) > 0 and not any(d.validation_errors for d in manifest.drawings.values()),
                "engine": manifest.build_info.engine_version,
                "timestamp": manifest.build_info.timestamp
            }
            json.dump(lock_data, f, indent=2)
        print(f"Project lock dumped to {lock_path}")

if __name__ == "__main__":
    main()
