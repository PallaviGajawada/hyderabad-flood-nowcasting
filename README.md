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
- `backend/models/surface_water_model.py` — deterministic D8-style
  surface-water routing, accumulation, and interaction outputs.
- `backend/models/drainage_model.py` — mapped nala interaction and
  dimensionless prototype drainage-capacity index.
- `backend/models/flood_depth_model.py` — prototype drainage removal,
  equivalent-depth, risk-class, and road-risk aggregation.
- `backend/runoff_coefficients.json` — configurable, explicitly assumed
  WorldCover runoff coefficients.
- `backend/surface_water_assumptions.json` — configurable prototype routing
  and drainage-interaction assumptions.
- `backend/drainage_assumptions.json` and
  `backend/flood_depth_assumptions.json` — explicitly labeled Step 6
  prototype assumptions.
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
- `/forecast` and `/forecast-status` return the deterministic seven-horizon
  forecast readiness and `/forecast-summary` returns the real generated
  statistics.
- `/safe-route` compares a normal shortest route with the existing
  flood-penalized route for a selected horizon.
- `/map-layers?forecast_minutes=<horizon>` returns cached lightweight GeoJSON
  for the flood grid, roads, road flood risk, nalas, water bodies, and GHMC
  boundary.
- The Step 8 dashboard provides horizon controls, independently toggleable map
  layers, a risk legend, clickable road details, model information, and route
  comparison overlays.
- `GET /api/data-status` checks every configured dataset and writes the
  read-only result to `outputs/data_validation_report.json`.
- `GET /api/preprocessing-status` returns the latest GIS preprocessing report.
- `GET /api/roads-status` returns the readiness and metadata for the real
  OSMnx/Overpass GHMC drive network.
- `GET /api/runoff-status` returns rainfall provider, model-grid alignment,
  coefficient configuration, and output readiness.
- `GET /api/runoff-summary` returns real runoff statistics only after a
  successful model run.
- `GET /api/surface-water-status` returns terrain-routing readiness, output
  availability, grid information, and limitations.
- `GET /api/surface-water-summary` returns real accumulated surface-water
  statistics only after a successful routing run.
- `GET /api/drainage-status` and `GET /api/drainage-summary` return mapped
  nala interaction and dimensionless capacity-index status/statistics.
- `GET /api/flood-depth-status` and `GET /api/flood-depth-summary` return raw
  equivalent depth, display depth, risk classes, drainage removal, and
  conservation statistics only after successful execution.
- `GET /api/road-flood-risk` returns the generated road-risk artifact summary
  and output path.
- GIS preprocessing uses EPSG:4326 for web/interchange GeoJSON and EPSG:32644
  for metre-based terrain and length calculations. Reprojection is documented
  in the preprocessing report.
- Step 7 and Step 8 are transparent prototype forecast, routing, and web GIS
  layers. They do not provide real-time radar nowcasting, engineering-grade
  hydraulic simulation, emergency navigation, or an operational warning.

## Step 7 — Deterministic forecast and flood-aware routing

Step 7 preserves all earlier model outputs. It uses
`outputs/model/flood_depth/display_depth_cm.tif` as the T+0 baseline and writes
seven aligned scenario rasters under `outputs/model/forecast/`:

```text
tplus_000 · tplus_030 · tplus_060 · tplus_090
tplus_120 · tplus_150 · tplus_180
```

The scenario factors are configurable in `backend/forecast_assumptions.json`.
The current rainfall provider is historical 2024 IMD daily gridded rainfall,
not a live Doppler Weather Radar nowcast. Routing uses the existing processed
OSM drive graph and cached road flood-risk attributes; its result is a
screening comparison, not a guarantee of safe passage.

## Step 8 — Demo-ready web GIS dashboard

The dashboard at `/` is built on the existing React + Vite + Leaflet stack. Its
demo flow is:

1. Select T+0 through T+180 in the left control panel.
2. Toggle flood depth/risk, roads, nalas, water bodies, and the GHMC boundary.
3. Click a road to inspect horizon-scaled depth and risk details.
4. Compare the selected horizon's depth, affected cells, and risk classes.
5. Enter coordinates, choose a horizon, and draw normal and flood-aware routes.

The browser receives a simplified 80×60 forecast grid and at most 3,000 road
features from `/api/map-layers`. Original scientific GeoTIFFs, the full road
GeoJSON, and the 138,851-node / 360,839-edge routing graph remain server-side.

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

## Prototype Surface-Water Routing Model

The surface-water stage is a deterministic terrain-based screening model:

```text
runoff
  → DEM terrain routing
  → D8 flow direction
  → flow accumulation
  → retained surface-water volume
  → equivalent water depth
```

The model uses the existing DEM as its modeling grid and validates CRS,
dimensions, transform, resolution, extent, and nodata alignment against the
runoff rasters. It routes water only through valid DEM/runoff cells using the
steepest strictly lower D8 neighbor. Flats and pits become sinks; routing
never deliberately leaves the valid GHMC/model grid.

Processed nala geometries are rasterized onto the DEM grid. Nala cells use
the configurable values in `backend/surface_water_assumptions.json` for
prototype capture/removal only. These are explicitly labeled assumptions and
are not measured GHMC/HMWSSB drainage capacities. The model reports the
removed volume and checks conservation:

```text
input runoff volume
  ≈ retained surface-water volume
  + prototype drainage-removed volume
```

Processed tank/water-body polygons are rasterized as retention sinks. No tank
levels, spillway capacities, storage curves, or operating rules are invented.

Outputs are written to:

```text
outputs/model/surface_water/
├── surface_water_depth_mm.tif
├── surface_water_depth_cm.tif
├── surface_water_volume_m3.tif
├── flow_direction.tif
├── flow_accumulation.tif
├── nala_interaction.tif
└── surface_water_metadata.json
```

The depth layers represent **prototype terrain-based surface-water
accumulation**, not measured flood depth. This is not a full 2D
shallow-water hydrodynamic solver and does not implement safe routing,
hydraulic pipe flow, backflow, or the final 0–3 hour forecast. Current
rainfall remains the historical/scenario IMD input rather than radar
nowcasting.

## Step 6 — Prototype Drainage Network and Flood-Depth Screening

This is a research/prototype screening model and is not an engineering
hydraulic simulation or operational flood warning system.

The mapped nala/drainage network is used as a spatial proxy for drainage
interaction. Missing hydraulic attributes are represented using explicitly
labeled prototype assumptions. No pipe diameter, channel depth, invert
elevation, Manning roughness, measured flow, pump operation, manhole level,
blockage observation, or real-time sewer condition is fabricated.

### Drainage interaction

`backend/models/drainage_model.py` rasterizes the existing processed nala
GeoJSON to the exact DEM grid. Interaction values are:

```text
0     no mapped nala influence
1     mapped nala intersects the cell
2     within the configured prototype influence radius
-9999 nodata
```

The drainage capacity index is dimensionless. It combines a proximity factor
and a slope factor, then applies the configured prototype effectiveness:

```text
capacity_index =
  prototype_effectiveness
  × (proximity_weight × proximity_factor
     + slope_weight × slope_factor)
```

This is not a hydraulic capacity.

### Drainage removal and flood depth

Step 6 consumes the Step 5 surface-water volume raster:

```text
prototype_drainage_removed_volume =
  min(
    surface_water_volume
    × capacity_index
    × surface_volume_removal_fraction
    × prototype_drainage_effectiveness,
    maximum_prototype_removal_m3_per_cell
  )

remaining_surface_water_volume =
  surface_water_volume - prototype_drainage_removed_volume

raw_equivalent_depth_cm =
  remaining_surface_water_volume / cell_area_m2 × 100
```

Drainage removal can be disabled through
`backend/drainage_assumptions.json`; the model still runs and reports zero
removal. Water-body cells are excluded from prototype drainage removal.
Conservation is checked as:

```text
input surface-water volume
  ≈ prototype drainage removal
  + remaining surface-water volume
```

The raw equivalent depth preserves the actual calculation, including extreme
terrain-sink values. The display depth is a separate screening layer:

```text
display_depth_cm = min(raw_equivalent_depth_cm, display_depth_cap_cm)
```

The display cap is a visualization/screening decision and is **not** physical
inundation capping.

Prototype risk classes use display depth:

```text
0 = no/very low
1 = low       (0–<5 cm)
2 = moderate  (5–<15 cm)
3 = high      (15–<30 cm)
4 = severe    (≥30 cm)
```

These are prototype screening thresholds, not official emergency thresholds.

### Step 6 outputs

```text
outputs/model/drainage/
├── drainage_interaction.tif
├── drainage_capacity_index.tif
└── drainage_metadata.json

outputs/model/flood_depth/
├── raw_equivalent_depth_mm.tif
├── raw_equivalent_depth_cm.tif
├── display_depth_cm.tif
├── flood_risk_class.tif
├── drainage_removed_volume_m3.tif
├── remaining_surface_water_volume_m3.tif
├── road_flood_risk.geojson
└── flood_depth_metadata.json
```

Road risk is sampled from the existing processed OSM road GeoJSON; roads are
not downloaded again. Each road edge receives prototype maximum depth, mean
depth, affected-sample percentage, and maximum risk class. These statistics
are not measured street-level flood depths and are not safe-route
recommendations.

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