from core.context import AnalysisContext
from core.pipeline import PipelineStage, ParserStage, NormalizerStage
from core.geometry.spatial import SpatialIndexStage
from core.topology.canonical import CanonicalNodesStage
from core.topology.graph import TopologyStage
from core.recognition.shape import ShapeRecognitionStage

class GeometryEngine:
    def __init__(self):
        # Register the pipeline sequence in order
        self.stages = [
            ParserStage(),
            NormalizerStage(),
            SpatialIndexStage(),
            CanonicalNodesStage(),
            TopologyStage(),
            ShapeRecognitionStage(),
            # Future stages will be registered here:
            # EvidenceStage(),
            # AnnotationStage(),
            # ScheduleStage()
        ]

    def load(self, filepath: str) -> AnalysisContext:
        """Initialize the context from a file path."""
        return AnalysisContext(filepath=filepath)

    def process(self, context: AnalysisContext, until: str = None) -> AnalysisContext:
        """
        Run the pipeline on the context.
        If 'until' is provided, the pipeline stops AFTER the stage with that name.
        """
        for stage in self.stages:
            context = stage.execute(context)
            if until and stage.name == until:
                break
        return context

    # Additional convenience wrappers as defined in the stable API
    def detect_rebars(self, context: AnalysisContext):
        # E.g. runs process(context, until="evidence")
        pass
        
    def generate_schedule(self, context: AnalysisContext):
        # E.g. runs process(context, until="schedule")
        pass
