"""Replaceable rainfall provider interface for downstream model stages."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any

import xarray as xr

from ..config import PREPROCESSED_ROOT
from ..rainfall.base import RainfallInput, RainfallSource


class RainfallProvider(RainfallSource, ABC):
    """Provider contract shared by historical IMD and future radar inputs."""

    @abstractmethod
    def load_dataset(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> xr.Dataset:
        """Load a standardized rainfall dataset for a time window."""

    def load(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> RainfallInput:
        return RainfallInput(
            source=self.source_name,
            valid_at=None,
            payload=self.load_dataset(start=start, end=end),
        )


class IMDRainfallProvider(RainfallProvider):
    """Historical IMD rainfall provider, not a radar nowcast provider."""

    def __init__(
        self,
        path: Path = PREPROCESSED_ROOT / "rainfall" / "imd_rainfall_ghmc.nc",
    ) -> None:
        self.path = path

    @property
    def source_name(self) -> str:
        return "IMD historical rainfall"

    def load_dataset(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> xr.Dataset:
        with xr.open_dataset(self.path) as dataset:
            loaded = dataset.load()
        if start is not None or end is not None:
            loaded = loaded.sel(
                TIME=slice(
                    start.isoformat() if start is not None else None,
                    end.isoformat() if end is not None else None,
                )
            )
        loaded.attrs["provider"] = self.source_name
        return loaded