"""
core/readers/dwg_reader.py — DWG reader: ODA conversion + the existing DXFReader.

Deliberately NOT a second parser. Every read_* method converts the DWG to
DXF once (checksum-cached, see dwg_converter.py) and delegates to the
already-audited, frozen DXFReader — one canonical geometry-extraction path
for both formats, so nothing about geometry parsing needed re-auditing to
support DWG. See docs/audits/phase13/13.0_dwg_ingestion.md.
"""
from __future__ import annotations

from typing import Any

from core.readers.base import DrawingReader
from core.readers.dxf_reader import DXFReader
from core.readers.dwg_converter import convert_dwg_to_dxf, converter_available
from core.project import DrawingStatistics, DrawingCapabilities, DrawingRegistration, DrawingIdentity


class DWGReader(DrawingReader):
    def __init__(self):
        self._dxf = DXFReader()

    def can_read(self, path: str) -> bool:
        # Only claim .dwg when the converter is actually present --
        # otherwise Phase 1 falls back to its existing, honest
        # "No reader available" warning instead of failing mid-read.
        return path.lower().endswith(".dwg") and converter_available()

    def read_metadata(self, path: str) -> dict:
        return self._dxf.read_metadata(convert_dwg_to_dxf(path))

    def read_statistics(self, path: str) -> DrawingStatistics:
        return self._dxf.read_statistics(convert_dwg_to_dxf(path))

    def read_capabilities(self, path: str) -> DrawingCapabilities:
        return self._dxf.read_capabilities(convert_dwg_to_dxf(path))

    def read_registration(self, path: str) -> DrawingRegistration:
        return self._dxf.read_registration(convert_dwg_to_dxf(path))

    def read_geometry(self, path: str, identity: DrawingIdentity) -> Any:
        return self._dxf.read_geometry(convert_dwg_to_dxf(path), identity)
