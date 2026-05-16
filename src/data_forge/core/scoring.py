from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GateResult:
    score: int
    accepted: bool
    reasons: list[str] = field(default_factory=list)
    dimensions: dict[str, int] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "accepted": self.accepted,
            "reasons": self.reasons,
            "dimensions": self.dimensions,
            "metadata": self.metadata,
        }
