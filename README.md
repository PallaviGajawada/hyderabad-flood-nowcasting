# Hyderabad Urban Flood Nowcasting System

An initial foundation for a prototype that will eventually estimate urban
flood risk and approximate flood depth over a 0–3 hour horizon for Hyderabad,
India. This repository intentionally stops before flood simulation and does
not fabricate rainfall, hydraulic measurements, or model outputs.

## Architecture

- `backend/` — Python 3.11+ FastAPI foundation, configuration, provider-neutral
  rainfall interface, and future GIS/model module boundaries.
- `artifacts/hyderabad-flood-nowcasting/` — React + TypeScript + Vite dashboard
  shell with a Leaflet map area and typed API calls.
- `lib/api-spec/openapi.yaml` — source of truth for the API contract.
- `artifacts/api-server/` — the managed API service entrypoint, configured to
  run `backend.main` through the project workflow.
- `data/` — expected source-data categories; no source datasets are included.
- `outputs/` — future flood-map, forecast, and route output directories.
- `tests/` — initial backend contract smoke tests.

The rainfall boundary is implemented through `RainfallSource`. The
`IMDRainfallAdapter` is a placeholder for historical/scenario NetCDF input;
future Doppler Weather Radar nowcast input can implement the same interface
without coupling the model to IMD-specific files.

## Current implementation status

- FastAPI app is available at `/` and `/api/`.
- `/health` and `/api/health` return a simple health response.
- `/forecast`, `/flood-depth`, and `/safe-route` return
  `Model not implemented yet.`
- Dashboard sections exist for Current Status, Rainfall, Flood Forecast, Flood
  Depth, Drainage Network, and Safe Route.
- Hyderabad map foundation is present; it is a context map, not a flood-depth
  layer.
- No GIS preprocessing, rainfall-to-runoff estimation, drainage graph,
  hydraulic calculation, 2D simulation, forecast model, risk score, or safe
  routing has been implemented.

## Expected datasets

The configured `HYDERABAD_FLOOD_DATA` root expects:

```text
drainage/ghmc_nalas/ghmc_nalas.json
flood/ghmc_inundation/ghmc_inundation_areas.txt
drainage/tanks/hyderabad_tanks.txt
drainage/streams/hyderabad_stream_network.txt
roads/osm/hyderabad_roads.gpkg
terrain/dem/hyderabad_dem_30m.tif
landcover/esaworldcover/hyderabad_landcover_10m.tif
rainfall/imd_gauge/imd_rainfall_2024.nc
flood/historical_floods/hyderabad_flooding_locations.kml
boundaries/ghmc/ghmc_boundary.geojson
```

Set `HYDERABAD_FLOOD_DATA` to point at the data root. The foundation only
describes these paths; it does not require them to start the API.

## Known data limitations

- IMD rainfall is expected to be approximately 0.25° resolution while the DEM
  is expected to be approximately 30 m resolution.
- These inputs cannot support claims of true street-level prediction accuracy.
- Future results must be described as prototype/model estimates, not
  engineering-grade hydraulic predictions.
- Pipe diameter, invert elevation, pipe depth, Manning roughness, manhole
  locations, hydraulic capacity, and other missing parameters must be sourced
  and validated later; they must not be invented.

## Future development stages

1. Validate source datasets and coordinate reference systems.
2. Add GIS preprocessing for boundaries, terrain, land cover, roads, drainage,
   tanks, and historical flood observations.
3. Add rainfall adapters for IMD historical/scenario data and live radar
   nowcasts.
4. Build rainfall-to-runoff and drainage-network representations with explicit
   uncertainty.
5. Add hydraulic capacity and 2D surface-flood modeling only when required
   parameters are available.
6. Produce 0–3 hour prototype forecasts and calibrated risk estimates.
7. Add flood-depth, road-risk, and flood-safe route visualizations with clear
   confidence and limitation metadata.

## Run

Frontend dashboard:

```bash
pnpm --filter @workspace/hyderabad-flood-nowcasting run dev
```

Managed API workflow:

```bash
pnpm --filter @workspace/api-server run dev
```

The API workflow supplies `PORT`; the Python service also defaults to port
8000 when run directly:

```bash
PYTHONPATH=. python -m backend.main
```

Regenerate typed API clients after changing the contract:

```bash
pnpm --filter @workspace/api-spec run codegen
```