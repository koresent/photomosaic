# Photomosaic

Offline photomosaic generator and interactive Deep Zoom web viewer. Precomputes high-resolution tile pyramids to render gigapixel mosaics statically in the browser without server-side computation.

---

## Architecture & Mechanics

### 1. Color & Spatial Analysis
- **Perceptual Color Space:** Source photos and target cells are mapped to CIE L\*a\*b\* (D65 illuminant). Matching minimizes Euclidean distance $\Delta E$, with configurable weighting between lightness $L^*$ and chromaticity $a^*, b^*$.
- **Spatial Quadrant Decomposition:** Each cell and candidate photo is subdivided into 2×2 quadrants to preserve directional color gradients and edge contours across cell boundaries.
- **Alpha Mask Handling:** Target images with transparency (PNG/WebP) can be evaluated with `--skip-transparent`. Cells below the alpha threshold are omitted from matching, preserving cut-out silhouettes.
- **Incremental Cache:** Analysis results, extracted features, and standardized thumbnails are stored in `cache/` indexed by file hash and modification timestamp.

### 2. Assignment Algorithm
- **Proximity Penalty:** Penalizes or prevents the assignment of identical photos within a specified radius (`avoid_neighbor_radius`) to eliminate visible clusters.
- **Frequency Balancing:** Tracks global photo usage and applies progressive penalties as usage approaches `max_repeat_factor`.
- **Unique-Only Mode:** Enforces a strict one-to-one mapping (`--unique-only`) where each photo in the collection is used at most once.
- **Top-K Selection:** Selects candidates randomly from the top-K matches weighted by inverse distance to prevent repetitive deterministic patterns.
- **Target Blending:** Optional subtle overlay (`color_blend_ratio`) blends the resized target portrait into non-transparent regions to reinforce portrait recognition at low zoom while keeping individual tiles sharp when zooming in.

### 3. Deep Zoom Tiling (DZI)
- Downsamples the master mosaic into a multi-resolution image pyramid (levels 0 through $\lceil\log_2(\max(W, H))\rceil$) with standard overlap.
- Outputs XML descriptor `mosaic.dzi` and tile folders `mosaic_files/{level}/{col}_{row}.jpg`.

### 4. Web Viewer
- Powered by OpenSeadragon for pan, pinch-to-zoom, and tile-based on-demand loading.
- Browser language auto-detection (Russian / English).
- Fragment inspector: clicking any photo reveals its source filename, thumbnail preview, and grid coordinates.
- 100% static: output is self-contained and ready for GitHub Pages, Netlify, or local static hosting.

---

## Usage

### 1. Web Studio (GUI)

Single-click launcher that starts the local GUI and opens it in your default browser:

- **Windows:** Double-click `start_windows.bat`
- **macOS:** Double-click `start_mac.command`
- **Linux:** Run `./start_linux.sh` (or `python3 app.py`)

The Studio provides drag-and-drop portrait replacement, real-time parameter sliders, live generation progress, and an embedded interactive viewer that updates immediately upon completion.

### 2. Command Line Interface

```bash
# Basic generation and immediate preview
python3 generator/generate.py --serve

# Skip transparent background regions
python3 generator/generate.py --skip-transparent --serve

# Strictly unique photos (each photo used <= 1 time)
python3 generator/generate.py --skip-transparent --unique-only --cols 12 --serve

# Custom parameters
python3 generator/generate.py --cols 80 --tile-size 100 --blend 0.05 --top-k 3
```

### CLI Options

| Option | Default | Description |
|---|---|---|
| `--target` | auto-detect | Path to target portrait (JPG, PNG, WebP) |
| `--photos` | `source/photos` | Path to folder containing source photos |
| `--output` | `output` | Destination directory for the static viewer |
| `--cols` | `60` | Number of columns in the mosaic grid |
| `--rows` | auto | Number of rows (calculated to maintain aspect ratio) |
| `--tile-size` | `120` | Resolution of each tile in pixels in the master image |
| `--blend` | `0.08` | Blend ratio with original target image (0.0 to 0.3) |
| `--top-k` | `3` | Random selection among top-K best matching candidates |
| `--avoid-radius` | `2` | Radius (in cells) to avoid repeating the same photo |
| `--max-repeat` | `1.8` | Multiplier cap on repetitions relative to average |
| `--skip-transparent` | `false` | Do not fill transparent areas of target image |
| `--alpha-threshold` | `128` | Alpha cutoff threshold (0–255) |
| `--unique-only` | `false` | Ensure each source photo appears at most once |
| `--force-analyze` | `false` | Bypass cache and re-analyze all photos |
| `--skip-dzi` | `false` | Skip DZI pyramid generation (output master image only) |
| `--serve` | `false` | Launch local HTTP server after generation |
| `--port` | `8080` | Port for local server |
