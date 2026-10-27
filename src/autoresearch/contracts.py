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
        if type(alpha) not in (int, float) or not math.isfinite(alpha) or not 0 <= alpha <= 1_000_000:
            raise ResearchError("INVALID_REQUEST", "alpha must be finite and between 0 and 1000000")
        return cls(degree, float(alpha))

    def to_dict(self):
        return asdict(self)
