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
- `backend/preprocessing/data_validator.py` — read-only vector, raster, and
  NetCDF validation.
- `backend/preprocessing/preprocessing_pipeline.py` — reproducible GIS
  preprocessing orchestration.
- `backend/models/runoff_model.py` — transparent rainfall-to-runoff prototype
  model and raster outputs.
- `backend/runoff_coefficients.json` — configurable, explicitly assumed
  WorldCover runoff coefficients.
- `data/` — organized source-data categories; only user-provided datasets are
  placed here.
- `outputs/preprocessed/` — clipped/model-ready rasters, GeoJSON layers,
  standardized rainfall, class lookup, and preprocessing report.
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
- Dashboard sections exist for Current Status, Rainfall, Data Status, Flood
  Forecast, Flood Depth, Drainage Network, and Safe Route.
- Hyderabad map foundation is present; it is a context map, not a flood-depth
  layer.
- `GET /api/data-status` checks every configured dataset and writes the
  read-only result to `outputs/data_validation_report.json`.
- `GET /api/preprocessing-status` returns the latest GIS preprocessing report.
- `GET /api/roads-status` returns the readiness and metadata for the real
  OSMnx/Overpass GHMC drive network.
- `GET /api/runoff-status` returns rainfall provider, model-grid alignment,
  coefficient configuration, and output readiness.
- `GET /api/runoff-summary` returns real runoff statistics only after a
  successful model run.
- GIS preprocessing uses EPSG:4326 for web/interchange GeoJSON and EPSG:32644
  for metre-based terrain and length calculations. Reprojection is documented
  in the preprocessing report.
- Hydraulic calculation, 2D simulation, forecast model, risk score, and safe
  routing remain unimplemented.

## Expected datasets

The configured `HYDERABAD_FLOOD_DATA` root expects:

```text
drainage/ghmc_nalas/ghmc_nalas.json
flood/ghmc_inundation/ghmc_inundation_areas.json
drainage/tanks/hyderabad_tanks.json
drainage/streams/hyderabad_stream_network.json
roads/osm/hyderabad_roads.gpkg
terrain/dem/hyderabad_dem_30m.tif
landcover/esaworldcover/hyderabad_landcover_10m.tif
rainfall/imd_gauge/imd_rainfall_2024.nc
flood/historical_floods/hyderabad_flooding_locations.kml
boundaries/ghmc/ghmc_boundary.json
```

The supplied vector JSON files are ArcGIS FeatureSet JSON and are parsed
in-memory without rewriting the originals. Set `HYDERABAD_FLOOD_DATA` to point
at the data root.

## Current validation result

The validation pass ran against the supplied files on September 7, 2026:

- 10 configured datasets
- 8 found and readable
- 8 valid
- 2 missing: the roads GeoPackage and historical flood KML
- 0 replacement or sample files created

The full machine-readable result is in
`outputs/data_validation_report.json`. The uploaded IMD file contains a
366-step `RAINFALL` variable in millimetres over
`TIME × LATITUDE × LONGITUDE = 366 × 129 × 135`, with coordinates spanning
6.5–38.5°N and 66.5–100°E.

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

## Step 3 preprocessing outputs

The reproducible preprocessing run creates:

```text
outputs/preprocessed/
├── dem/
│   ├── dem_ghmc.tif
│   ├── slope_ghmc.tif
│   └── slope_percent_ghmc.tif
├── landcover/
│   ├── landcover_ghmc.tif
│   └── worldcover_classes.json
├── rainfall/
│   └── imd_rainfall_ghmc.nc
├── drainage/
│   ├── ghmc_nalas.geojson
│   └── streams.geojson
├── waterbodies/
│   └── hyderabad_tanks.geojson
└── preprocessing_report.json
```

The stream output is intentionally empty after clipping because the supplied
stream extent does not intersect the supplied GHMC boundary. Historical flood
locations remain a future input. No hydraulic parameters, flood predictions,
or safe-route outputs are generated.

## Road-network preprocessing

The original large OSM GeoPackage is not required. The road-only processor
queries OpenStreetMap through OSMnx and Overpass using the supplied GHMC
boundary in EPSG:4326 and `network_type="drive"`. OSMnx handles Overpass
subdivision when a query geometry exceeds its configured maximum area.

Road outputs are written to:

```text
outputs/preprocessed/roads/
├── hyderabad_roads.geojson
├── hyderabad_drive.graphml
└── road_network_metadata.json
```

The metadata records the retrieval method and timestamp, CRS, boundary
bounding box, node and edge counts, network type, preserved OSM tags, and any
Overpass errors. Missing OSM attributes remain absent/null; no road
attributes are fabricated.

## Rainfall-to-Runoff Prototype Model

The model is a transparent research demonstration, not an engineering-grade
hydraulic flood model:

```text
IMD historical/scenario rainfall
        ↓
WorldCover class → configurable prototype runoff coefficient
        ↓
runoff_depth_mm = rainfall_depth_mm × runoff_coefficient
        ↓
runoff_volume_m3 = runoff_depth_mm / 1000 × cell_area_m2
```

The current rainfall provider is `IMDRainfallProvider`, reading the processed
NetCDF without modifying it. The rainfall grid is approximately 0.25° and is
not a Doppler Weather Radar nowcast. A future radar provider can implement the
same `RainfallProvider` interface.

The output grid follows the processed DEM in EPSG:32644 at approximately
30 m resolution. Land cover and rainfall are resampled to that grid with
nearest-neighbor resampling, which is recorded in
`outputs/model/runoff/runoff_metadata.json`. Cells outside the actual
processed rainfall coverage, DEM nodata cells, land-cover nodata cells, and
unconfigured classes remain nodata.

All coefficients in `backend/runoff_coefficients.json` are labeled
`prototype_assumption`. They are not supplied GHMC measurements and must be
replaced or calibrated before operational use. Water-body classes are handled
separately and receive zero direct runoff in this screening calculation.

This stage does not simulate drainage capacity, pipe flow, backflow, hydraulic
routing, or street-level flood depth.

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