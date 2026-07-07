import hashlib
import json
from abc import ABC, abstractmethod
from typing import List, Dict
from uuid import UUID

from core.topology.graph import ConnectedComponent, ConnectivityGraph
from core.recognition.models import RecognitionResult, Evidence

class Recognizer(ABC):
    @abstractmethod
    def recognize(self, component: ConnectedComponent, graph: ConnectivityGraph) -> RecognitionResult:
        pass

class RecognizerRegistry:
    def __init__(self):
        self._recognizers: List[Recognizer] = []
        
    def register(self, recognizer: Recognizer):
        self._recognizers.append(recognizer)
        
    def evaluate(self, component: ConnectedComponent, graph: ConnectivityGraph) -> RecognitionResult:
        best_result = None
        best_confidence = -1.0
        
        for recognizer in self._recognizers:
            result = recognizer.recognize(component, graph)
            if result.confidence > best_confidence:
                best_confidence = result.confidence
                best_result = result
                
        # Fallback if everything is 0 or all recognizers skipped it
        if best_result is None or best_result.confidence <= 0.0:
            best_result = RecognitionResult(
                component_uuid=component.id,
                label='unknown',
                confidence=0.0,
                recognizer='UnknownRecognizer',
                evidence=[Evidence('fallback', False, 'No recognizer matched with positive confidence')],
                measurements={}
            )
            
        # compute fingerprint based on label and measurements
        data = {
            'label': best_result.label,
            'measurements': best_result.measurements
        }
        hasher = hashlib.sha256()
        hasher.update(json.dumps(data, sort_keys=True).encode('utf-8'))
        best_result.fingerprint = hasher.hexdigest()
        
        return best_result

class RecognitionCache:
    def __init__(self):
        self.results: Dict[UUID, RecognitionResult] = {}
        
    def get(self, comp_id: UUID) -> RecognitionResult:
        return self.results.get(comp_id)
        
    def set(self, comp_id: UUID, result: RecognitionResult):
        self.results[comp_id] = result
