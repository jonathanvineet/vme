"""
Shared face-recognition engine used by all gate/admin servers.

- Employee registry (employees.json): employee_id -> name
- Per-image encoding cache (.cache.pkl): avoids recomputing face
  encodings for photos that haven't changed, so startup is fast even
  with many employees.
- Cheap auto-reload: admin_server touches known_faces/.reload_version
  whenever it saves new photos; gate/admin processes poll that file's
  mtime and only rescan when it changes.
"""

import json
import os
import pickle
import threading

import face_recognition

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KNOWN_FACES_DIR = os.path.join(BASE_DIR, "known_faces")
EMPLOYEES_PATH = os.path.join(BASE_DIR, "employees.json")
CACHE_PATH = os.path.join(KNOWN_FACES_DIR, ".cache.pkl")
VERSION_PATH = os.path.join(KNOWN_FACES_DIR, ".reload_version")

os.makedirs(KNOWN_FACES_DIR, exist_ok=True)


def _load_employees():
    if not os.path.exists(EMPLOYEES_PATH):
        return {}
    with open(EMPLOYEES_PATH) as f:
        return json.load(f)


def _save_employees(employees):
    with open(EMPLOYEES_PATH, "w") as f:
        json.dump(employees, f, indent=2, sort_keys=True)


def touch_version():
    """Signal to all processes that known_faces changed and should be reloaded."""
    with open(VERSION_PATH, "a"):
        os.utime(VERSION_PATH, None)


def register_employee(employee_id, name):
    employees = _load_employees()
    employees[employee_id] = {"name": name}
    _save_employees(employees)


def list_employees():
    employees = _load_employees()
    result = []
    for empid, info in employees.items():
        folder = os.path.join(KNOWN_FACES_DIR, empid)
        photo_count = 0
        if os.path.isdir(folder):
            photo_count = len([
                f for f in os.listdir(folder)
                if f.lower().endswith((".jpg", ".jpeg", ".png"))
            ])
        result.append({
            "employee_id": empid,
            "name": info.get("name", empid),
            "photo_count": photo_count,
        })
    result.sort(key=lambda e: e["employee_id"])
    return result


class FaceEngine:
    """Holds the in-memory encodings and knows how to (re)build them cheaply."""

    def __init__(self):
        self._lock = threading.Lock()
        self.encodings = []
        self.employee_ids = []
        self.names = []
        self._last_version_mtime = None
        self.reload(force=True)

    def maybe_reload(self):
        try:
            mtime = os.path.getmtime(VERSION_PATH)
        except FileNotFoundError:
            mtime = None

        if mtime != self._last_version_mtime:
            self.reload()

    def reload(self, force=False):
        with self._lock:
            employees = _load_employees()

            cache = {}
            if os.path.exists(CACHE_PATH):
                try:
                    with open(CACHE_PATH, "rb") as f:
                        cache = pickle.load(f)
                except (pickle.PickleError, EOFError):
                    cache = {}

            new_cache = {}
            encodings, employee_ids, names = [], [], []
            migrated = False

            if os.path.isdir(KNOWN_FACES_DIR):
                for empid in sorted(os.listdir(KNOWN_FACES_DIR)):
                    folder = os.path.join(KNOWN_FACES_DIR, empid)
                    if not os.path.isdir(folder) or empid.startswith("."):
                        continue

                    # Legacy folders (created before the employee registry
                    # existed) get auto-registered using the folder name.
                    if empid not in employees:
                        employees[empid] = {"name": empid}
                        migrated = True

                    name = employees[empid]["name"]

                    for filename in os.listdir(folder):
                        if not filename.lower().endswith((".jpg", ".jpeg", ".png")):
                            continue

                        path = os.path.join(folder, filename)
                        key = os.path.relpath(path, KNOWN_FACES_DIR)
                        mtime = os.path.getmtime(path)

                        cached = cache.get(key)
                        if cached and cached["mtime"] == mtime:
                            encoding = cached["encoding"]
                        else:
                            image = face_recognition.load_image_file(path)
                            found = face_recognition.face_encodings(image)
                            if not found:
                                continue
                            encoding = found[0]

                        new_cache[key] = {"mtime": mtime, "encoding": encoding}
                        encodings.append(encoding)
                        employee_ids.append(empid)
                        names.append(name)

            with open(CACHE_PATH, "wb") as f:
                pickle.dump(new_cache, f)

            if migrated:
                _save_employees(employees)

            self.encodings = encodings
            self.employee_ids = employee_ids
            self.names = names

            try:
                self._last_version_mtime = os.path.getmtime(VERSION_PATH)
            except FileNotFoundError:
                self._last_version_mtime = None

            print(f"[face_engine] loaded {len(encodings)} face encodings "
                  f"for {len(set(employee_ids))} employees")

    def snapshot(self):
        with self._lock:
            return list(self.encodings), list(self.employee_ids), list(self.names)


ENGINE = FaceEngine()
if not os.path.exists(VERSION_PATH):
    touch_version()
    ENGINE.reload(force=True)
