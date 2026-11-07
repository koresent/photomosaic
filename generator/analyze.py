import os
import json
import logging
from pathlib import Path
from PIL import Image, ImageOps
from tqdm import tqdm

from color_utils import (
    center_crop_to_ratio,
    extract_image_features
)

SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}
logger = logging.getLogger(__name__)


def find_image_files(directory: str | Path):
    """
    Recursively find all supported image files in directory.
    """
    directory = Path(directory)
    if not directory.exists():
        raise FileNotFoundError(f"Photos directory not found: {directory}")

    image_files = []
    for root, _, files in os.walk(directory):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in SUPPORTED_EXTENSIONS:
                image_files.append(Path(root) / f)
    image_files.sort()
    return image_files


def load_cache(cache_file: Path) -> dict:
    if cache_file.exists():
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load cache {cache_file}: {e}")
    return {}


def save_cache(cache_file: Path, data: dict):
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def analyze_photos(
    photos_dir: str | Path,
    cache_dir: str | Path,
    output_thumbs_dir: str | Path | None = None,
    thumb_size: int = 240,
    cell_aspect_ratio: float = 1.0,
    force_refresh: bool = False
):
    """
    Scan photos, validate, generate thumbnails, compute color features,
    and cache results.
    """
    photos_path = Path(photos_dir).resolve()
    cache_path = Path(cache_dir).resolve()
    cache_file = cache_path / "photos_cache.json"
    cache_thumbs_dir = cache_path / "thumbs"
    cache_thumbs_dir.mkdir(parents=True, exist_ok=True)

    if output_thumbs_dir:
        output_thumbs_path = Path(output_thumbs_dir).resolve()
        output_thumbs_path.mkdir(parents=True, exist_ok=True)
    else:
        output_thumbs_path = None

    image_files = find_image_files(photos_path)
    if not image_files:
        raise ValueError(f"No valid image files found in {photos_path}")

    cached_data = {} if force_refresh else load_cache(cache_file)
    results = []
    corrupted_count = 0
    updated_cache = {}

    print(f"[Analyze] Scanning {len(image_files)} photos from {photos_path.name}...")

    for img_path in tqdm(image_files, desc="Analyzing photos"):
        str_path = str(img_path)
        stat = img_path.stat()
        file_mtime = stat.st_mtime
        file_size = stat.st_size
        file_key = str(img_path.relative_to(photos_path))
        thumb_name = f"{img_path.stem}_{img_path.stat().st_ino % 1000000:06d}.jpg"
        cached_thumb = cache_thumbs_dir / thumb_name

        cached_item = cached_data.get(file_key)
        if (
            cached_item
            and cached_item.get("mtime") == file_mtime
            and cached_item.get("size") == file_size
            and cached_thumb.exists()
        ):
            item_data = dict(cached_item)
            item_data["full_path"] = str_path
            item_data["thumb_path"] = str(cached_thumb)
            results.append(item_data)
            updated_cache[file_key] = cached_item

            if output_thumbs_path:
                out_thumb = output_thumbs_path / thumb_name
                if not out_thumb.exists():
                    try:
                        with open(cached_thumb, 'rb') as src, open(out_thumb, 'wb') as dst:
                            dst.write(src.read())
                    except Exception:
                        pass
            continue

        try:
            with Image.open(img_path) as img:
                img.verify()

            # PIL verify() invalidates image pointer, so re-open for processing
            with Image.open(img_path) as img:
                img = ImageOps.exif_transpose(img)
                orig_w, orig_h = img.size
                cropped = center_crop_to_ratio(img, cell_aspect_ratio)
                thumb = cropped.resize((thumb_size, int(round(thumb_size / cell_aspect_ratio))), Image.Resampling.LANCZOS)
                thumb_rgb = thumb.convert('RGB')
                thumb_rgb.save(cached_thumb, "JPEG", quality=90)

                if output_thumbs_path:
                    out_thumb = output_thumbs_path / thumb_name
                    thumb_rgb.save(out_thumb, "JPEG", quality=90)

                mean_lab, quad_lab, mean_rgb = extract_image_features(thumb_rgb, use_quadrants=True)

            photo_meta = {
                "key": file_key,
                "filename": img_path.name,
                "mtime": file_mtime,
                "size": file_size,
                "original_dimensions": [orig_w, orig_h],
                "mean_rgb": list(mean_rgb),
                "mean_lab": [float(x) for x in mean_lab],
                "quadrants_lab": [[float(x) for x in q] for q in quad_lab] if quad_lab is not None else None,
                "thumb_filename": thumb_name
            }

            updated_cache[file_key] = photo_meta

            photo_meta_runtime = dict(photo_meta)
            photo_meta_runtime["full_path"] = str_path
            photo_meta_runtime["thumb_path"] = str(cached_thumb)
            results.append(photo_meta_runtime)

        except Exception as err:
            logger.warning(f"Corrupted or invalid image: {img_path} ({err})")
            corrupted_count += 1

    save_cache(cache_file, updated_cache)
    print(f"[Analyze] Finished: {len(results)} valid photos analyzed, {corrupted_count} skipped/corrupted.")
    return results
