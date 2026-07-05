from abc import ABC, abstractmethod
from typing import Dict, Any, Tuple
from core.project import DrawingStatistics, DrawingCapabilities, DrawingRegistration

class DrawingReader(ABC):
    """
    Abstract base class for extracting metadata and statistics from drawing files.
    """
    @abstractmethod
    def can_read(self, path: str) -> bool:
        """Returns True if this reader can parse the file at the given path."""
        pass
        
    @abstractmethod
    def read_metadata(self, path: str) -> dict:
        """Extracts titleblock metadata, coordinate system, and units."""
        pass
        
    @abstractmethod
    def read_statistics(self, path: str) -> DrawingStatistics:
        """Computes entity counts, bounding boxes, and density without deep geometric parsing."""
        pass
        
    @abstractmethod
    def read_capabilities(self, path: str) -> DrawingCapabilities:
        """Determines what features the drawing supports."""
        pass
        
    @abstractmethod
    def read_registration(self, path: str) -> DrawingRegistration:
        """Extracts registration data (origin, rotation, etc)."""
        pass
        
    @abstractmethod
    def read_geometry(self, path: str) -> Any:
        """
        Extracts the full raw geometry for Phase 2.
        Implementation depends on the geometry engine's expected input.
        """
        pass
