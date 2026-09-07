# Hyderabad Urban Flood Nowcasting System

An initial dashboard and API foundation for prototype 0–3 hour urban flood
nowcasting in Hyderabad, India.

## Run & Operate

- `pnpm --filter @workspace/api-server run dev` — run the FastAPI service
- `pnpm run typecheck` — full typecheck across all packages
- `pnpm run build` — typecheck + build all packages
- `pnpm --filter @workspace/api-spec run codegen` — regenerate API hooks and Zod schemas from the OpenAPI spec
- `pnpm --filter @workspace/hyderabad-flood-nowcasting run dev` — run the
  dashboard
- `PYTHONPATH=. python -m backend.main` — run the FastAPI app directly

## Stack

- pnpm workspaces, Node.js 24, TypeScript 5.9
- API: FastAPI + Uvicorn
- Geospatial foundation: GeoPandas, Shapely, Rasterio, PyProj
- Scientific foundation: NumPy, Pandas, Xarray, NetworkX
- Frontend: React + TypeScript + Vite + Leaflet
- API codegen: Orval (from OpenAPI spec)
- Build: Vite

## Where things live

- `backend/config.py` — dataset-root configuration and expected source paths
- `backend/rainfall/base.py` — provider-neutral rainfall input contract
- `backend/rainfall/imd_adapter.py` — IMD adapter placeholder
- `backend/main.py` — minimal FastAPI app and placeholder routes
- `backend/preprocessing/data_validator.py` — read-only source-file inspection
- `backend/preprocessing/preprocessing_pipeline.py` — reproducible GIS
  preprocessing orchestration and report
- `backend/preprocessing/dem_processor.py`, `landcover_processor.py`,
  `rainfall_processor.py`, `drainage_processor.py`,
  `waterbody_processor.py` — stage processors
- `backend/models/rainfall_interface.py` — replaceable IMD/radar rainfall
  provider contract
- `lib/api-spec/openapi.yaml` — API contract source of truth
- `artifacts/hyderabad-flood-nowcasting/src/` — dashboard implementation
- `README.md` — scope, limitations, datasets, and future stages

## Architecture decisions

- Rainfall is represented through a provider-neutral interface so live Doppler
  Weather Radar input can be added alongside IMD historical/scenario data.
- Model endpoints return an explicit not-implemented response rather than
  fabricated forecasts or depths.
- The map is a spatial context surface only; it must not be presented as
  street-level flood prediction.
- Dataset validation reads user-supplied source files in memory and never
  rewrites or reprojects them.
- ArcGIS FeatureSet JSON is accepted alongside conventional GeoJSON because
  several supplied vector files use that native format.
- GIS preprocessing keeps EPSG:4326 for web/interchange outputs and uses
  EPSG:32644 for metre-based terrain and length calculations.

## Product

Users can inspect the prototype system status, rainfall context, forecast
placeholder, flood-depth placeholder, drainage placeholder, and safe-route
placeholder from a Hyderabad dashboard. It is a foundation, not an operational
warning system.

## User preferences

- Do not proceed to flood modeling or fabricate datasets and hydraulic
  measurements until the required source data and parameters are available.

## Gotchas

- Run API codegen after every OpenAPI change.
- Data validation and preprocessing report missing source files instead of
  creating fallback datasets.
- Use `HYDERABAD_FLOOD_DATA` to point at an external source-data root when
  needed. The current workspace contains the supplied source files; roads and
  historical flood KML remain missing.

## Pointers

- See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details
