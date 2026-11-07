#!/usr/bin/env python3
import os
import sys
import json
import argparse
import http.server
import socketserver
import webbrowser
from pathlib import Path

# Add current directory to path for imports
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from analyze import analyze_photos
from mosaic import generate_mosaic_pipeline
from dzi import generate_dzi_pyramid


SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}


def resolve_target_path(target_input: str | Path | None, project_root: Path) -> Path | None:
    """
    Auto-detect target portrait image file:
    - Supports .jpg, .jpeg, .png, .webp (case-insensitive)
    - If target_input is an existing file, use it.
    - If target_input is a directory (e.g. target/), search for first supported image inside.
    - If target_input file does not exist, search same folder for other supported extensions.
    - Also searches project_root/source, project_root/target, and project_root.
    """
    if target_input:
        p = Path(target_input)
        if not p.is_absolute():
            p = (project_root / p).resolve()
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS:
            return p
        if p.is_dir():
            for f in sorted(p.iterdir()):
                if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS:
                    return f
        # Check same parent directory with other supported extensions
        parent = p.parent
        stem = p.stem
        if parent.exists() and parent.is_dir():
            for ext in ['.jpg', '.jpeg', '.png', '.webp']:
                candidate = parent / f"{stem}{ext}"
                if candidate.is_file():
                    return candidate
            for ext in ['.jpg', '.jpeg', '.png', '.webp']:
                candidate = parent / f"{stem}{ext.upper()}"
                if candidate.is_file():
                    return candidate

    # Search common directories in order
    candidate_folders = [
        project_root / "source",
        project_root / "target",
        project_root
    ]
    for folder in candidate_folders:
        if folder.exists() and folder.is_dir():
            for ext in ['.jpg', '.jpeg', '.png', '.webp']:
                cand = folder / f"target{ext}"
                if cand.is_file():
                    return cand
            for f in sorted(folder.iterdir()):
                if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS:
                    return f

    return None


def load_config(config_path: Path) -> dict:
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[Warning] Failed to load config from {config_path}: {e}")
    return {}


def setup_web_viewer(output_dir: Path):
    web_template_dir = SCRIPT_DIR / "web_template"
    if web_template_dir.exists():
        import shutil
        shutil.copy2(web_template_dir / "index.html", output_dir / "index.html")
        out_assets = output_dir / "assets"
        out_assets.mkdir(parents=True, exist_ok=True)
        shutil.copytree(web_template_dir / "assets", out_assets, dirs_exist_ok=True)


def serve_output(directory: Path, port: int = 8080):
    os.chdir(str(directory))
    handler = http.server.SimpleHTTPRequestHandler
    
    # Allow port reuse
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", port), handler) as httpd:
        url = f"http://localhost:{port}/index.html"
        print(f"\n[Server] Web viewer running at: {url}")
        print("[Server] Press Ctrl+C to stop the server.\n")
        try:
            webbrowser.open(url)
        except Exception:
            pass
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[Server] Stopped.")


def main():
    parser = argparse.ArgumentParser(
        description="Photomosaic Generator - Create interactive Deep Zoom photomosaics."
    )
    parser.add_argument("--config", "-c", type=str, default=str(SCRIPT_DIR / "config.json"),
                        help="Path to configuration JSON file")
    parser.add_argument("--target", "-t", type=str, default=None,
                        help="Path to target portrait image")
    parser.add_argument("--photos", "-p", type=str, default=None,
                        help="Path to folder containing source photos")
    parser.add_argument("--output", "-o", type=str, default=None,
                        help="Output directory for generated website & mosaic")
    parser.add_argument("--cols", type=int, default=None,
                        help="Number of columns in mosaic grid (default: from config or 60)")
    parser.add_argument("--rows", type=int, default=None,
                        help="Number of rows in mosaic grid (default: auto from aspect ratio)")
    parser.add_argument("--tile-size", type=int, default=None,
                        help="Resolution of each tile in pixels (default: 120)")
    parser.add_argument("--blend", type=float, default=None,
                        help="Subtle target blend ratio 0.0-0.3 (default: 0.08)")
    parser.add_argument("--top-k", type=int, default=None,
                        help="Random selection among top-K candidates (default: 3)")
    parser.add_argument("--avoid-radius", type=int, default=None,
                        help="Neighbor photo avoidance radius (default: 2)")
    parser.add_argument("--max-repeat", type=float, default=None,
                        help="Max repeats multiplier relative to average (default: 1.8)")
    parser.add_argument("--skip-transparent", action="store_true",
                        help="Do not fill transparent areas of target image with photos")
    parser.add_argument("--alpha-threshold", type=int, default=None,
                        help="Alpha threshold for transparency detection 0-255 (default: 128)")
    parser.add_argument("--unique-only", "--no-repeat", "--unique", dest="unique_only", action="store_true",
                        help="Ensure each photo is used at most once in the mosaic")
    parser.add_argument("--force-analyze", action="store_true",
                        help="Ignore cache and re-analyze all photos")
    parser.add_argument("--skip-dzi", action="store_true",
                        help="Skip Deep Zoom pyramid generation")
    parser.add_argument("--serve", "-s", action="store_true",
                        help="Launch local web server to preview generated viewer")
    parser.add_argument("--port", type=int, default=8080,
                        help="Port for local web server (default: 8080)")

    args = parser.parse_args()

    # Load base config
    config_path = Path(args.config)
    config = load_config(config_path)

    # Project root is parent of generator
    project_root = SCRIPT_DIR.parent

    # Resolve paths
    raw_target = args.target or config.get("target_path")
    target_path = resolve_target_path(raw_target, project_root)

    photos_dir = Path(args.photos or config.get("photos_dir", project_root / "source" / "photos"))
    if not photos_dir.is_absolute():
        photos_dir = (project_root / photos_dir).resolve()

    output_dir = Path(args.output or config.get("output_dir", project_root / "output"))
    if not output_dir.is_absolute():
        output_dir = (project_root / output_dir).resolve()

    cache_dir = Path(config.get("cache_dir", project_root / "cache"))
    if not cache_dir.is_absolute():
        cache_dir = (project_root / cache_dir).resolve()

    # Apply CLI overrides to config dict
    grid_cfg = config.setdefault("grid", {})
    matching_cfg = config.setdefault("matching", {})
    output_cfg = config.setdefault("output", {})

    if args.cols is not None:
        grid_cfg["columns"] = args.cols
    if args.rows is not None:
        grid_cfg["rows"] = args.rows
    if args.tile_size is not None:
        grid_cfg["tile_render_size"] = args.tile_size

    if args.blend is not None:
        matching_cfg["color_blend_ratio"] = args.blend
    if args.top_k is not None:
        matching_cfg["random_top_k"] = args.top_k
    if args.avoid_radius is not None:
        matching_cfg["avoid_neighbor_radius"] = args.avoid_radius
    if args.max_repeat is not None:
        matching_cfg["max_repeat_factor"] = args.max_repeat
    if args.skip_transparent:
        matching_cfg["skip_transparent"] = True
    if args.alpha_threshold is not None:
        matching_cfg["alpha_threshold"] = args.alpha_threshold
    if args.unique_only:
        matching_cfg["unique_only"] = True

    print("=" * 60)
    print("PHOTOMOSAIC GENERATOR")
    print(f"Target:  {target_path or raw_target}")
    print(f"Photos:  {photos_dir}")
    print(f"Output:  {output_dir}")
    print(f"Grid:    {grid_cfg.get('columns')} cols, {grid_cfg.get('tile_render_size')}px tiles")
    print(f"Options: skip_transparent={matching_cfg.get('skip_transparent', False)}, unique_only={matching_cfg.get('unique_only', False)}")
    print("=" * 60)

    if not target_path or not target_path.exists():
        print(f"[Error] Target image not found! Checked: {raw_target}, source/, target/ (supported: JPG, JPEG, PNG, WebP)", file=sys.stderr)
        sys.exit(1)

    if not photos_dir.exists():
        print(f"[Error] Photos directory not found: {photos_dir}", file=sys.stderr)
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)
    setup_web_viewer(output_dir)
    thumbs_output_dir = output_dir / "assets" / "thumbs"

    photos_meta = analyze_photos(
        photos_dir=photos_dir,
        cache_dir=cache_dir,
        output_thumbs_dir=thumbs_output_dir,
        thumb_size=240,
        cell_aspect_ratio=float(grid_cfg.get("cell_aspect_ratio", 1.0)),
        force_refresh=args.force_analyze
    )

    if not photos_meta:
        print("[Error] No photos could be processed.", file=sys.stderr)
        sys.exit(1)

    mosaic_img, metadata = generate_mosaic_pipeline(
        target_path=target_path,
        photos_meta=photos_meta,
        output_dir=output_dir,
        config=config
    )

    if not args.skip_dzi and output_cfg.get("generate_dzi", True):
        dzi_tile_size = int(output_cfg.get("dzi_tile_size", 256))
        dzi_overlap = int(output_cfg.get("dzi_overlap", 1))
        out_format = output_cfg.get("format", "jpg")
        quality = int(output_cfg.get("quality", 90))

        generate_dzi_pyramid(
            source_image=mosaic_img,
            output_dir=output_dir,
            basename="mosaic",
            tile_size=dzi_tile_size,
            overlap=dzi_overlap,
            image_format=out_format,
            quality=quality
        )

    print("=" * 60)
    print("GFL GENERATION COMPLETE!")
    print(f"Mosaic:     {output_dir / 'mosaic.jpg'}")
    print(f"Metadata:   {output_dir / 'metadata' / 'mosaic_info.json'}")
    print(f"Web Viewer: {output_dir / 'index.html'}")
    print("=" * 60)

    # 4. Optional Web Server
    if args.serve:
        serve_output(output_dir, port=args.port)


if __name__ == "__main__":
    main()
