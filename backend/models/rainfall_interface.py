"""Replaceable rainfall provider interface for downstream model stages."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import xarray as xr

from ..config import PROCESSED_RAINFALL_NETCDF
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

    @abstractmethod
    def get_rainfall(
        self,
        *,
        timestamp: datetime | str | None = None,
        start: datetime | str | None = None,
        end: datetime | str | None = None,
    ) -> xr.DataArray:
        """Return rainfall depth in millimeters for a time or time window."""


class IMDRainfallProvider(RainfallProvider):
    """Historical IMD rainfall provider, not a radar nowcast provider."""

    def __init__(
        self,
        path: Path = PROCESSED_RAINFALL_NETCDF,
    ) -> None:
        self.path = path

    @property
    def source_name(self) -> str:
        return "IMD historical rainfall"

    @property
    def rainfall_path(self) -> Path:
        return self.path

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

    def get_rainfall(
        self,
        *,
        timestamp: datetime | str | None = None,
        start: datetime | str | None = None,
        end: datetime | str | None = None,
    ) -> xr.DataArray:
        dataset = self.load_dataset(start=None, end=None)
        rainfall = dataset["rainfall_mm"]
        if timestamp is not None:
            selected = rainfall.sel(TIME=np.datetime64(timestamp))
        elif start is not None or end is not None:
            selected = rainfall.sel(
                TIME=slice(
                    np.datetime64(start) if start is not None else None,
                    np.datetime64(end) if end is not None else None,
                )
            )
        else:
            selected = rainfall
        selected.attrs.update(
            {
                "units": rainfall.attrs.get("units", "mm"),
                "provider": self.source_name,
            }
        )
        return selected

    def available_time_range(self) -> tuple[np.datetime64, np.datetime64]:
        dataset = self.load_dataset()
        values = dataset["TIME"].values
        return np.datetime64(values[0]), np.datetime64(values[-1])