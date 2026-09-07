"""Provider-neutral rainfall input contract.

Both historical/scenario rainfall and future live radar nowcasts should
implement this interface. The model must not depend directly on IMD files.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class RainfallInput:
    """A normalized rainfall snapshot passed to downstream model stages."""

    source: str
    valid_at: datetime | None
    payload: Any = None


class RainfallSource(ABC):
    """Interface for historical, scenario, and live rainfall providers."""

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Return a stable provider name for metadata and audit logs."""

    @abstractmethod
    def load(self, *, start: datetime | None = None, end: datetime | None = None) -> RainfallInput:
        """Return normalized rainfall input for a requested time window."""