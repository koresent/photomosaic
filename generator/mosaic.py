import math
import json
import random
from pathlib import Path
from PIL import Image, ImageOps
import numpy as np
from tqdm import tqdm

from color_utils import (
    rgb_to_lab,
    extract_image_features,
    center_crop_to_ratio
)


def compute_target_grid_features(
    target_img: Image.Image,
    columns: int,
    rows: int,
    use_quadrants: bool = True,
    skip_transparent: bool = False,
    alpha_threshold: int = 128
):
    """
    Subdivide target image into columns x rows grid and compute color features for each cell.
    If skip_transparent is True and cell has alpha < alpha_threshold, cell is marked as transparent.
    """
    w, h = target_img.size
    cell_w = w / columns
    cell_h = h / rows

    has_alpha = ("A" in target_img.mode) or ("transparency" in target_img.info)
    if has_alpha:
        alpha_channel = target_img.convert("RGBA").split()[-1]
    else:
        alpha_channel = None

    rgb_target = target_img.convert("RGB")

    grid_cells = []
    transparent_cells_count = 0
    print(f"[Mosaic] Analyzing target grid ({columns}x{rows} = {columns * rows} cells, skip_transparent={skip_transparent})...")

    for r in range(rows):
        y1 = int(round(r * cell_h))
        y2 = int(round((r + 1) * cell_h))
        row_cells = []

        for c in range(columns):
            x1 = int(round(c * cell_w))
            x2 = int(round((c + 1) * cell_w))

            is_transparent = False
            mean_alpha = 255.0

            if skip_transparent and alpha_channel is not None:
                alpha_crop = alpha_channel.crop((x1, y1, x2, y2))
                mean_alpha = float(np.mean(np.asarray(alpha_crop, dtype=np.float32)))
                if mean_alpha < alpha_threshold:
                    is_transparent = True
                    transparent_cells_count += 1

            if is_transparent:
                row_cells.append({
                    "col": c,
                    "row": r,
                    "box": (x1, y1, x2, y2),
                    "is_transparent": True,
                    "mean_alpha": mean_alpha,
                    "mean_lab": None,
                    "quad_lab": None,
                    "mean_rgb": None,
                    "contrast": 0.0
                })
            else:
                cell_crop = rgb_target.crop((x1, y1, x2, y2))
                mean_lab, quad_lab, mean_rgb = extract_image_features(cell_crop, use_quadrants=use_quadrants)
                arr = np.asarray(cell_crop, dtype=np.float32)
                contrast = float(np.std(arr))

                row_cells.append({
                    "col": c,
                    "row": r,
                    "box": (x1, y1, x2, y2),
                    "is_transparent": False,
                    "mean_alpha": mean_alpha,
                    "mean_lab": mean_lab,
                    "quad_lab": quad_lab,
                    "mean_rgb": mean_rgb,
                    "contrast": contrast
                })
        grid_cells.append(row_cells)

    if skip_transparent and transparent_cells_count > 0:
        print(f"[Mosaic] Detected {transparent_cells_count} transparent cells out of {columns * rows}. These will be skipped.")

    return grid_cells


def match_tiles(
    grid_cells: list[list[dict]],
    photos_meta: list[dict],
    columns: int,
    rows: int,
    config: dict
):
    """
    Match each non-transparent grid cell with best photo candidate.
    Supports unique_only mode (each photo used at most once) and balanced repetition mode.
    """
    matching_cfg = config.get("matching", {})
    luminance_weight = float(matching_cfg.get("luminance_weight", 1.2))
    use_quadrants = bool(matching_cfg.get("use_quadrants", True))
    quadrant_weight = float(matching_cfg.get("quadrant_weight", 0.35))
    avoid_radius = int(matching_cfg.get("avoid_neighbor_radius", 2))
    neighbor_penalty = float(matching_cfg.get("neighbor_penalty", 30.0))
    max_repeat_factor = float(matching_cfg.get("max_repeat_factor", 1.8))
    random_top_k = int(matching_cfg.get("random_top_k", 3))
    unique_only = bool(matching_cfg.get("unique_only", False))

    num_photos = len(photos_meta)
    assignment = np.full((rows, columns), -1, dtype=np.int32)
    photo_usage_counts = np.zeros(num_photos, dtype=np.int32)

    # Separate solid cells
    solid_cells = []
    for r in range(rows):
        for c in range(columns):
            cell = grid_cells[r][c]
            if not cell.get("is_transparent", False):
                solid_cells.append(cell)

    total_solid = len(solid_cells)

    # Pre-extract photo features as numpy arrays for speed
    photo_mean_labs = np.array([p["mean_lab"] for p in photos_meta], dtype=np.float32)  # (N, 3)
    if use_quadrants:
        photo_quad_labs = np.array([
            p["quadrants_lab"] if p.get("quadrants_lab") is not None
            else [p["mean_lab"]] * 4
            for p in photos_meta
        ], dtype=np.float32)  # (N, 4, 3)
    else:
        photo_quad_labs = None

    color_weights = np.array([luminance_weight, 1.0, 1.0], dtype=np.float32)

    if unique_only:
        print(f"[Mosaic] UNIQUE-ONLY mode active: each photo will appear at most once.")
        print(f"         Photos available: {num_photos}, Solid cells to fill: {total_solid}")

        if num_photos < total_solid:
            print(f"[Mosaic] Notice: Photos count ({num_photos}) is smaller than cells ({total_solid}).")
            print(f"         The top {num_photos} highest-contrast cells will be filled; others left blank.")
            # Sort solid cells by contrast descending so key facial features get the photos
            solid_cells.sort(key=lambda item: item.get("contrast", 0.0), reverse=True)
            active_cells = solid_cells[:num_photos]
        else:
            # Sort by contrast so high-detail areas get the first pick from the photo pool
            solid_cells.sort(key=lambda item: item.get("contrast", 0.0), reverse=True)
            active_cells = solid_cells

        available_mask = np.ones(num_photos, dtype=bool)

        for cell in tqdm(active_cells, desc="Matching unique photos"):
            if not np.any(available_mask):
                break

            col, row = cell["col"], cell["row"]
            cell_mean_lab = np.array(cell["mean_lab"], dtype=np.float32)

            # Distances for all photos
            diff = (photo_mean_labs - cell_mean_lab) * color_weights
            mean_dist = np.sqrt(np.sum(diff ** 2, axis=1))

            if use_quadrants and photo_quad_labs is not None and cell.get("quad_lab") is not None:
                cell_quad_lab = np.array(cell["quad_lab"], dtype=np.float32)
                q_diff = (photo_quad_labs - cell_quad_lab[np.newaxis, :, :]) * color_weights[np.newaxis, np.newaxis, :]
                q_dist = np.mean(np.sqrt(np.sum(q_diff ** 2, axis=2)), axis=1)
                dist = (1.0 - quadrant_weight) * mean_dist + quadrant_weight * q_dist
            else:
                dist = mean_dist

            # Exclude already used photos
            dist[~available_mask] = 1e9

            # Pick best or top-K
            avail_indices = np.where(available_mask)[0]
            if len(avail_indices) == 0:
                break

            avail_scores = dist[avail_indices]
            if len(avail_indices) <= 1 or random_top_k <= 1:
                chosen_idx = int(avail_indices[np.argmin(avail_scores)])
            else:
                if len(avail_indices) <= random_top_k:
                    best_sub_indices = np.argsort(avail_scores)
                else:
                    k = random_top_k
                    best_sub_indices = np.argpartition(avail_scores, k)[:k]
                    best_sub_indices = best_sub_indices[np.argsort(avail_scores[best_sub_indices])]

                chosen_indices = avail_indices[best_sub_indices]
                scores = avail_scores[best_sub_indices]
                weights = 1.0 / (scores - np.min(scores) + 1.0)
                probs = weights / np.sum(weights)
                chosen_idx = int(random.choices(chosen_indices, weights=probs, k=1)[0])

            assignment[row, col] = chosen_idx
            photo_usage_counts[chosen_idx] += 1
            available_mask[chosen_idx] = False

        return assignment, photo_usage_counts

    avg_repeats = total_solid / max(1, num_photos)
    hard_max_repeats = int(math.ceil(avg_repeats * max_repeat_factor))

    print(f"[Mosaic] Matching {total_solid} solid cells against {num_photos} photos...")
    print(f"         (avg repeats: {avg_repeats:.1f}, hard max: {hard_max_repeats}, top-K: {random_top_k})")

    # Serpentine scan order
    cell_order = []
    for r in range(rows):
        cols_in_row = list(range(columns))
        if r % 2 == 1:
            cols_in_row.reverse()
        for c in cols_in_row:
            if not grid_cells[r][c].get("is_transparent", False):
                cell_order.append((c, r))

    for col, row in tqdm(cell_order, desc="Matching cells"):
        cell = grid_cells[row][col]
        cell_mean_lab = np.array(cell["mean_lab"], dtype=np.float32)

        diff = (photo_mean_labs - cell_mean_lab) * color_weights
        mean_dist = np.sqrt(np.sum(diff ** 2, axis=1))

        if use_quadrants and photo_quad_labs is not None and cell.get("quad_lab") is not None:
            cell_quad_lab = np.array(cell["quad_lab"], dtype=np.float32)
            q_diff = (photo_quad_labs - cell_quad_lab[np.newaxis, :, :]) * color_weights[np.newaxis, np.newaxis, :]
            q_dist = np.mean(np.sqrt(np.sum(q_diff ** 2, axis=2)), axis=1)
            base_dist = (1.0 - quadrant_weight) * mean_dist + quadrant_weight * q_dist
        else:
            base_dist = mean_dist

        penalties = np.zeros(num_photos, dtype=np.float32)

        # Proximity penalty
        if avoid_radius > 0:
            min_r = max(0, row - avoid_radius)
            max_r = min(rows, row + avoid_radius + 1)
            min_c = max(0, col - avoid_radius)
            max_c = min(columns, col + avoid_radius + 1)

            for nr in range(min_r, max_r):
                for nc in range(min_c, max_c):
                    if nr == row and nc == col:
                        continue
                    assigned_idx = assignment[nr, nc]
                    if assigned_idx >= 0:
                        chebyshev_d = max(abs(nr - row), abs(nc - col))
                        if chebyshev_d <= avoid_radius:
                            weight = (avoid_radius + 1 - chebyshev_d) / avoid_radius
                            penalties[assigned_idx] += neighbor_penalty * weight

        # Frequency penalty
        usage_ratio = photo_usage_counts / max(1.0, avg_repeats)
        usage_penalty = 15.0 * (usage_ratio ** 2)
        penalties += usage_penalty

        # Hard cap
        over_cap = photo_usage_counts >= hard_max_repeats
        penalties[over_cap] += 10000.0

        total_scores = base_dist + penalties

        # Select candidate
        k = min(random_top_k, num_photos)
        best_indices = np.argpartition(total_scores, k)[:k]
        best_indices = best_indices[np.argsort(total_scores[best_indices])]

        if k == 1 or random_top_k <= 1:
            chosen_idx = int(best_indices[0])
        else:
            scores = total_scores[best_indices]
            weights = 1.0 / (scores - np.min(scores) + 1.0)
            probs = weights / np.sum(weights)
            chosen_idx = int(random.choices(best_indices, weights=probs, k=1)[0])

        assignment[row, col] = chosen_idx
        photo_usage_counts[chosen_idx] += 1

    return assignment, photo_usage_counts


def render_photomosaic(
    target_img: Image.Image,
    assignment: np.ndarray,
    photos_meta: list[dict],
    columns: int,
    rows: int,
    tile_size: int,
    color_blend_ratio: float = 0.08
) -> Image.Image:
    """
    Assemble high-resolution mosaic image from assigned tiles.
    Unassigned / transparent cells (-1) retain the background color.
    """
    mosaic_w = columns * tile_size
    mosaic_h = rows * tile_size

    # Background color matching the viewer theme (#0b0d13)
    bg_color = (11, 13, 19)

    print(f"[Mosaic] Rendering canvas: {mosaic_w}x{mosaic_h} px ({columns}x{rows} tiles at {tile_size}px)...")
    canvas = Image.new("RGB", (mosaic_w, mosaic_h), bg_color)

    # Pre-render unique tiles
    unique_indices = np.unique(assignment)
    unique_indices = unique_indices[unique_indices >= 0]
    rendered_tiles = {}

    print(f"[Mosaic] Preparing {len(unique_indices)} unique source tiles...")
    for idx in tqdm(unique_indices, desc="Scaling tiles"):
        photo = photos_meta[idx]
        thumb_path = photo.get("thumb_path")
        full_path = photo.get("full_path")

        src_path = full_path if (full_path and tile_size > 200) else (thumb_path or full_path)
        try:
            with Image.open(src_path) as im:
                im = ImageOps.exif_transpose(im)
                cropped = center_crop_to_ratio(im, 1.0)
                tile = cropped.resize((tile_size, tile_size), Image.Resampling.LANCZOS).convert('RGB')
                rendered_tiles[idx] = tile
        except Exception:
            tile = Image.new("RGB", (tile_size, tile_size), tuple(photo.get("mean_rgb", [128, 128, 128])))
            rendered_tiles[idx] = tile

    print("[Mosaic] Pasting tiles into master canvas...")
    for r in range(rows):
        for c in range(columns):
            idx = assignment[r, c]
            if idx >= 0:
                tile = rendered_tiles.get(idx)
                if tile is not None:
                    canvas.paste(tile, (c * tile_size, r * tile_size))

    # Optional subtle blend with original target portrait
    if color_blend_ratio > 0.001:
        print(f"[Mosaic] Applying subtle target blend (ratio={color_blend_ratio:.2f})...")
        target_resized = target_img.resize((mosaic_w, mosaic_h), Image.Resampling.BILINEAR)

        if "A" in target_resized.mode:
            r_ch, g_ch, b_ch, a_ch = target_resized.split()
            rgb_target = Image.merge("RGB", (r_ch, g_ch, b_ch))
            blended = Image.blend(canvas, rgb_target, min(0.3, color_blend_ratio))
            canvas.paste(blended, (0, 0), mask=a_ch)
        else:
            target_rgb = target_resized.convert("RGB")
            canvas = Image.blend(canvas, target_rgb, min(0.3, color_blend_ratio))

    return canvas


def generate_mosaic_pipeline(
    target_path: str | Path,
    photos_meta: list[dict],
    output_dir: str | Path,
    config: dict
):
    """
    Full pipeline to generate mosaic image, save metadata, and return result image.
    """
    target_path = Path(target_path).resolve()
    output_path = Path(output_dir).resolve()
    metadata_dir = output_path / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)

    grid_cfg = config.get("grid", {})
    output_cfg = config.get("output", {})
    matching_cfg = config.get("matching", {})

    columns = int(grid_cfg.get("columns", 60))
    configured_rows = grid_cfg.get("rows")
    cell_aspect_ratio = float(grid_cfg.get("cell_aspect_ratio", 1.0))
    tile_size = int(grid_cfg.get("tile_render_size", 120))
    blend_ratio = float(matching_cfg.get("color_blend_ratio", 0.08))
    skip_transparent = bool(matching_cfg.get("skip_transparent", False))
    alpha_threshold = int(matching_cfg.get("alpha_threshold", 128))
    unique_only = bool(matching_cfg.get("unique_only", False))

    with Image.open(target_path) as img:
        img = ImageOps.exif_transpose(img)
        target_img = img.copy()
        orig_w, orig_h = target_img.size

    # Auto-calculate rows if not specified
    if configured_rows is None:
        target_ratio = orig_w / orig_h
        rows = int(round(columns / (target_ratio * cell_aspect_ratio)))
    else:
        rows = int(configured_rows)

    # Compute target cell features
    use_quadrants = bool(matching_cfg.get("use_quadrants", True))
    grid_cells = compute_target_grid_features(
        target_img=target_img,
        columns=columns,
        rows=rows,
        use_quadrants=use_quadrants,
        skip_transparent=skip_transparent,
        alpha_threshold=alpha_threshold
    )

    # Match tiles
    assignment, usage_counts = match_tiles(grid_cells, photos_meta, columns, rows, config)

    # Render master canvas
    mosaic_img = render_photomosaic(
        target_img=target_img,
        assignment=assignment,
        photos_meta=photos_meta,
        columns=columns,
        rows=rows,
        tile_size=tile_size,
        color_blend_ratio=blend_ratio
    )

    # Save high-res mosaic image
    out_format = output_cfg.get("format", "jpg").lower()
    quality = int(output_cfg.get("quality", 92))
    mosaic_file = output_path / f"mosaic.{out_format}"

    print(f"[Mosaic] Saving master image to {mosaic_file}...")
    if out_format in ("jpg", "jpeg"):
        mosaic_img.save(mosaic_file, "JPEG", quality=quality)
    elif out_format == "webp":
        mosaic_img.save(mosaic_file, "WEBP", quality=quality)
    elif out_format == "png":
        mosaic_img.save(mosaic_file, "PNG")

    # Generate metadata JSON & JS bundle
    cells_metadata = []
    filled_count = 0
    empty_count = 0

    for r in range(rows):
        for c in range(columns):
            p_idx = int(assignment[r, c])
            if p_idx >= 0:
                photo = photos_meta[p_idx]
                cells_metadata.append({
                    "c": c,
                    "r": r,
                    "photo": photo["filename"],
                    "thumb": photo.get("thumb_filename", ""),
                    "key": photo["key"]
                })
                filled_count += 1
            else:
                cells_metadata.append({
                    "c": c,
                    "r": r,
                    "empty": True
                })
                empty_count += 1

    unique_count = int(np.count_nonzero(usage_counts > 0))
    metadata = {
        "grid": {
            "columns": columns,
            "rows": rows,
            "total_cells": columns * rows,
            "tile_size": tile_size,
            "cell_aspect_ratio": cell_aspect_ratio
        },
        "image": {
            "width": mosaic_img.width,
            "height": mosaic_img.height,
            "file": mosaic_file.name
        },
        "dzi": {
            "tileSize": int(output_cfg.get("dzi_tile_size", 256)),
            "overlap": int(output_cfg.get("dzi_overlap", 1)),
            "format": out_format
        },
        "stats": {
            "total_photos_available": len(photos_meta),
            "unique_photos_used": unique_count,
            "filled_cells": filled_count,
            "empty_cells": empty_count,
            "max_repeats": int(np.max(usage_counts)) if len(usage_counts) > 0 else 0,
            "min_repeats": int(np.min(usage_counts[usage_counts > 0])) if unique_count > 0 else 0,
            "avg_repeats": float(np.mean(usage_counts[usage_counts > 0])) if unique_count > 0 else 0.0,
            "unique_only": unique_only,
            "skip_transparent": skip_transparent
        },
        "cells": cells_metadata
    }

    meta_file = metadata_dir / "mosaic_info.json"
    with open(meta_file, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    meta_js_file = metadata_dir / "mosaic_info.js"
    with open(meta_js_file, 'w', encoding='utf-8') as f:
        f.write("window.MOSAIC_DATA = ")
        json.dump(metadata, f, ensure_ascii=False)
        f.write(";\n")

    print(f"[Mosaic] Metadata saved to {meta_file} and {meta_js_file}")

    return mosaic_img, metadata
