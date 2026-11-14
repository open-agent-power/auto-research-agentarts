"""Explicit experience schema routing; each family keeps its own validator."""
from . import cpu_project_experience as cpu
from . import project_experience as ridge
from . import staged_project_experience as staged
from .contracts import ResearchError
from .research_recipe import parse_json

MAX_BUNDLE_BYTES = ridge.MAX_BUNDLE_BYTES


def _family(bundle):
    if type(bundle) is not dict:
        raise ResearchError("INVALID_PROJECT_EXPERIENCE", "Require a supported experience object.")
    if bundle.get("schema_version") == "project-experience-bundle-v1":
        return ridge
    if bundle.get("schema_version") == cpu.SCHEMA:
        return cpu
    if bundle.get("schema_version") == staged.SCHEMA:
        return staged
    raise ResearchError("INVALID_PROJECT_EXPERIENCE", "Unsupported experience bundle schema.")


def validate_bundle(bundle):
    return _family(bundle).validate_bundle(bundle)


def parse_bundle(raw):
    return validate_bundle(parse_json(raw, maximum=MAX_BUNDLE_BYTES, code="INVALID_PROJECT_EXPERIENCE"))


def summary(bundle):
    return _family(bundle).summary(bundle)
