---
name: Raster validation runtime
description: Runtime dependency needed for Rasterio-based dataset validation in this workspace.
---

Rasterio validation requires the Nix `expat` system library to be available so
the Python bindings can load `libexpat.so.1`.

**Why:** The Python package installation completed successfully, but importing
Rasterio failed until the shared library was installed separately.

**How to apply:** When adding or troubleshooting Rasterio validation, verify
the system library is present before diagnosing source raster files.