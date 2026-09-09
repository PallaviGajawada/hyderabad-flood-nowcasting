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
- `backend/preprocessing/road_processor.py` — road-only OSMnx/Overpass
  download and export
- `backend/preprocessing/dem_processor.py`, `landcover_processor.py`,
  `rainfall_processor.py`, `drainage_processor.py`,
  `waterbody_processor.py` — stage processors
- `backend/models/rainfall_interface.py` — replaceable IMD/radar rainfall
  provider contract
- `backend/models/runoff_model.py` — rainfall-to-runoff prototype raster model
- `backend/models/surface_water_model.py` — deterministic terrain-based
  surface-water routing and accumulation
- `backend/models/drainage_model.py` — mapped nala spatial interaction and
  dimensionless drainage capacity index
- `backend/models/flood_depth_model.py` — prototype drainage removal,
  equivalent depth, screening risk, and road-risk aggregation
- `backend/runoff_coefficients.json` — explicitly labeled prototype
  coefficient assumptions
- `backend/surface_water_assumptions.json` — explicitly labeled prototype
  routing/drainage assumptions
- `backend/drainage_assumptions.json` and
  `backend/flood_depth_assumptions.json` — explicitly labeled Step 6
  prototype assumptions
- `lib/api-spec/openapi.yaml` — API contract source of truth
- `artifacts/hyderabad-flood-nowcasting/src/` — dashboard implementation
- `README.md` — scope, limitations, datasets, and future stages

## Architecture decisions

- Rainfall is represented through a provider-neutral interface so live Doppler
  Weather Radar input can be added alongside IMD historical/scenario data.
- Forecast and routing endpoints return deterministic prototype estimates based
  on the existing Step 6/7 outputs; they do not fabricate radar observations.
- The Step 8 map is a simplified spatial visualization surface and must not be
  presented as street-level flood prediction.
- Dataset validation reads user-supplied source files in memory and never
  rewrites or reprojects them.
- ArcGIS FeatureSet JSON is accepted alongside conventional GeoJSON because
  several supplied vector files use that native format.
- GIS preprocessing keeps EPSG:4326 for web/interchange outputs and uses
  EPSG:32644 for metre-based terrain and length calculations.

## Product

Users can inspect the prototype system status, rainfall context, seven
forecast horizons, interactive GIS layers, road details, and normal-versus-
flood-aware route comparisons from a Hyderabad dashboard. It is a foundation,
not an operational warning or navigation system.

## User preferences

- Do not proceed to flood modeling or fabricate datasets and hydraulic
  measurements until the required source data and parameters are available.

## Gotchas

- Run API codegen after every OpenAPI change.
- Data validation and preprocessing report missing source files instead of
  creating fallback datasets.
- The runoff prototype must keep rainfall/land-cover/DEM alignment explicit,
  preserve nodata, and never present prototype coefficients as measured
  hydraulic data.
- Surface-water outputs must report volume conservation, keep tank/nala
  assumptions configurable, and label equivalent depth as prototype
  accumulated surface water rather than observed flood depth.
- Step 6 must preserve separate raw and display depth layers. Display caps and
  risk thresholds are visualization/screening assumptions, not physical
  inundation limits or official emergency thresholds. Road risk is not safe
  routing.
- The large source roads GeoPackage is intentionally not required; the
  road-only processor obtains the real drive network from OSMnx/Overpass using
  the supplied GHMC boundary.
- Use `HYDERABAD_FLOOD_DATA` to point at an external source-data root when
  needed. The current workspace contains the supplied source files; roads and
  historical flood KML remain missing.

## Pointers

- See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details
