---
name: Processed GeoJSON geometry
description: Geometry handling required when rasterizing generated project GeoJSON outputs
---

Generated GeoJSON outputs can be read as raw geometry mappings by the shared ArcGIS-aware reader instead of Shapely objects. Rasterization and spatial operations should prefer an OGR-backed GeoPandas read for generated GeoJSON, with explicit mapping-to-Shapely normalization as a fallback.

**Why:** The surface-water routing stage encountered a GeoJSON mapping/geometry mismatch when rasterizing the already-processed nala and water-body layers.

**How to apply:** Before calling rasterio rasterize, intersection, or reprojection on generated GeoJSON, verify the geometry column contains Shapely objects and normalize mappings if necessary.