import time
from abc import ABC, abstractmethod
from core.context import AnalysisContext, PhaseCompletedEvent
from core.geometry.parser import CADParser
from core.geometry.normalizer import Normalizer
from core.geometry.repository import GeometryRepository

class PipelineStage(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass
        
    @abstractmethod
    def execute(self, context: AnalysisContext) -> AnalysisContext:
        pass
        
    def _emit_event(self, context: AnalysisContext, entities_count: int, duration: float, warnings: list = None):
        if warnings is None:
            warnings = []
        event = PhaseCompletedEvent(
            phase=self.name,
            entities=entities_count,
            duration=duration,
            warnings=warnings
        )
        context.events.append(event)
        context.metrics[self.name] = entities_count

class ParserStage(PipelineStage):
    @property
    def name(self) -> str:
        return "parser"
        
    def execute(self, context: AnalysisContext) -> AnalysisContext:
        start_time = time.time()
        parser = CADParser()
        entities = parser.parse_dxf(context.filepath)
        duration = time.time() - start_time
        
        # We temporarily store raw entities in context metadata for the normalizer
        context.metrics["_raw_parsed"] = entities
        self._emit_event(context, len(entities), duration)
        
        return context

class NormalizerStage(PipelineStage):
    @property
    def name(self) -> str:
        return "normalizer"
        
    def execute(self, context: AnalysisContext) -> AnalysisContext:
        start_time = time.time()
        
        raw_entities = context.metrics.get("_raw_parsed", [])
        
        # Create a new repository and normalize into it
        new_repo = GeometryRepository()
        normalizer = Normalizer(new_repo)
        normalizer.normalize(raw_entities)
        
        duration = time.time() - start_time
        
        # Evolve context with the new repository
        new_context = context.evolve(repository=new_repo)
        self._emit_event(new_context, len(new_repo.entities), duration)
        
        return new_context
