"""Small, bounded contracts. Candidate requests never control evaluation data."""

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import re


class ResearchError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def fingerprint(value) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def identifier(value, name="request_id") -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", value):
        raise ResearchError("INVALID_REQUEST", f"{name} must be 1-80 ASCII identifier characters")
    return value


@dataclass(frozen=True)
class Candidate:
    degree: int = 1
    alpha: float = 0.01

    @classmethod
    def parse(cls, value):
        if not isinstance(value, dict) or set(value) != {"degree", "alpha"}:
            raise ResearchError("INVALID_REQUEST", "candidate requires only degree and alpha")
        degree, alpha = value["degree"], value["alpha"]
        if type(degree) is not int or not 1 <= degree <= 3:
            raise ResearchError("INVALID_REQUEST", "degree must be an integer from 1 to 3")
        if type(alpha) not in (int, float) or not 0 <= alpha <= 1_000_000 or not math.isfinite(alpha):
            raise ResearchError("INVALID_REQUEST", "alpha must be finite and between 0 and 1000000")
        return cls(degree, float(alpha))

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class Proposal:
    observation_sha256: str
    hypothesis: str
    expected_effect: str
    candidate: Candidate
    evidence_trial_ids: tuple

    @classmethod
    def parse(cls, value):
        fields = {"observation_sha256", "hypothesis", "expected_effect", "candidate", "evidence_trial_ids"}
        if not isinstance(value, dict) or set(value) != fields:
            raise ResearchError("INVALID_REQUEST", "proposal requires observation_sha256, hypothesis, expected_effect, candidate and evidence_trial_ids")
        digest = value["observation_sha256"]
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ResearchError("INVALID_REQUEST", "observation_sha256 must be a lowercase SHA-256")
        for key in ("hypothesis", "expected_effect"):
            if not isinstance(value[key], str) or not 1 <= len(value[key].strip()) <= 1000:
                raise ResearchError("INVALID_REQUEST", key + " must contain 1-1000 characters")
        evidence = value["evidence_trial_ids"]
        if not isinstance(evidence, list) or len(evidence) > 20:
            raise ResearchError("INVALID_REQUEST", "evidence_trial_ids must be a list of at most 20 trial identifiers")
        for item in evidence:
            identifier(item, "evidence_trial_id")
        if len(set(evidence)) != len(evidence):
            raise ResearchError("INVALID_REQUEST", "evidence_trial_ids cannot contain duplicates")
        return cls(digest, value["hypothesis"], value["expected_effect"],
                   Candidate.parse(value["candidate"]), tuple(evidence))

    def to_dict(self):
        return {"observation_sha256": self.observation_sha256, "hypothesis": self.hypothesis,
                "expected_effect": self.expected_effect, "candidate": self.candidate.to_dict(),
                "evidence_trial_ids": list(self.evidence_trial_ids)}
