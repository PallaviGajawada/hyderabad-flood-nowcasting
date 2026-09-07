"""Placeholder adapter for IMD rainfall NetCDF input."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .base import RainfallInput, RainfallSource


class IMDRainfallAdapter(RainfallSource):
    """Future adapter for historical/scenario IMD rainfall NetCDF data.

    This class intentionally does not open or interpret the file yet. It
    provides the boundary needed to add a Doppler Weather Radar adapter later
    without coupling the forecast model to IMD-specific details.
    """

    def __init__(self, dataset_path: Path):
        self.dataset_path = dataset_path

    @property
    def source_name(self) -> str:
        return "imd-netcdf"

    def load(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> RainfallInput:
        raise NotImplementedError(
            "IMD rainfall loading is not implemented in the initial foundation."
        )