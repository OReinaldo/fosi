"""Common contract for FOSI public-data adapters.

Adapters return normalized acquisition records while retaining provider/raw
payloads. Network access belongs to each concrete adapter; failures are
isolated so one unavailable provider cannot stop the scouting run.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

@dataclass
class AcquisitionResult:
    provider: str
    status: str
    records: list[dict[str, Any]] = field(default_factory=list)
    raw_files: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    retrieved_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class ProviderAdapter:
    provider = 'unknown'
    def collect(self, target: dict) -> AcquisitionResult:
        raise NotImplementedError
