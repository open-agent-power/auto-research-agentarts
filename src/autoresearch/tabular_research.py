"""Medium-profile adapter for the frozen source-assessment protocol."""
import hashlib
from pathlib import Path

from . import pipeline_research_transport
from .source_assessment import SourceAssessmentCloudLoop, SourceAssessmentStudy


class TabularResearchCloudLoop(SourceAssessmentCloudLoop):
    def _code_identity(self):
        return hashlib.sha256((super()._code_identity()).encode('ascii')+Path(__file__).read_bytes()+Path(pipeline_research_transport.__file__).read_bytes()).hexdigest()

    def _specification(self,identity,observation,max_requests):
        return {**super()._specification(identity,observation,max_requests),
                'schema':'p02-tabular-research-native-v1','reasoning_effort':'medium',
                'max_output_tokens':2048,'prompt_token_evidence_cap':30720,'context_tokens':32768}
