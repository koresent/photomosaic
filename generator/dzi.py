import math
from pathlib import Path
from PIL import Image
from tqdm import tqdm


def get_max_level(width: int, height: int) -> int:
    return int(math.ceil(math.log2(max(width, height))))


def get_level_dimensions(width: int, height: int, level: int, max_level: int) -> tuple[int, int]:
    scale = 0.5 ** (max_level - level)
    w = max(1, int(math.ceil(width * scale)))
    h = max(1, int(math.ceil(height * scale)))
    return w, h


def create_dzi_descriptor(
    output_xml_path: Path,
    width: int,
    height: int,
    tile_size: int = 256,
    overlap: int = 1,
    image_format: str = "jpg"
):
    output_xml_path.parent.mkdir(parents=True, exist_ok=True)
    xml_content = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<Image xmlns="http://schemas.microsoft.com/deepzoom/2008"\n'
        f'       Format="{image_format}"\n'
        f'       Overlap="{overlap}"\n'
        f'       TileSize="{tile_size}">\n'
        f'  <Size Width="{width}" Height="{height}"/>\n'
        '</Image>\n'
    )
    with open(output_xml_path, 'w', encoding='utf-8') as f:
        f.write(xml_content)


def generate_dzi_pyramid(
    source_image: Image.Image | str | Path,
    output_dir: Path,
    basename: str = "mosaic",
    tile_size: int = 256,
    overlap: int = 1,
    image_format: str = "jpg",
    quality: int = 88
):
    """
    Generate Deep Zoom Image (DZI) XML and pyramid tiles directory.
    Output:
      output_dir / f"{basename}.dzi"
      output_dir / f"{basename}_files" / {level} / {col}_{row}.jpg
    """
    if isinstance(source_image, (str, Path)):
        img = Image.open(source_image).convert('RGB')
    else:
        img = source_image.convert('RGB')

    width, height = img.size
    max_level = get_max_level(width, height)

    dzi_path = output_dir / f"{basename}.dzi"
    files_dir = output_dir / f"{basename}_files"
    files_dir.mkdir(parents=True, exist_ok=True)

    create_dzi_descriptor(dzi_path, width, height, tile_size, overlap, image_format)

    print(f"[DZI] Generating pyramid ({width}x{height}, max level {max_level}, tile {tile_size}px)...")

    # Generate levels from max_level down to 0
    # Current image starts at max_level
    current_img = img

    for level in range(max_level, -1, -1):
        target_w, target_h = get_level_dimensions(width, height, level, max_level)

        if current_img.size != (target_w, target_h):
            current_img = current_img.resize((target_w, target_h), Image.Resampling.BILINEAR)

        level_dir = files_dir / str(level)
        level_dir.mkdir(parents=True, exist_ok=True)

        cols = int(math.ceil(target_w / tile_size))
        rows = int(math.ceil(target_h / tile_size))

        for col in range(cols):
            x1 = 0 if col == 0 else col * tile_size - overlap
            x2 = min(target_w, (col + 1) * tile_size + overlap)

            for row in range(rows):
                y1 = 0 if row == 0 else row * tile_size - overlap
                y2 = min(target_h, (row + 1) * tile_size + overlap)

                tile = current_img.crop((x1, y1, x2, y2))
                tile_filename = f"{col}_{row}.{image_format}"
                tile_path = level_dir / tile_filename
                
                # Save tile
                if image_format in ("jpg", "jpeg"):
                    tile.save(tile_path, "JPEG", quality=quality)
                elif image_format == "webp":
                    tile.save(tile_path, "WEBP", quality=quality)
                elif image_format == "png":
                    tile.save(tile_path, "PNG", optimize=True)

    print(f"[DZI] Pyramid successfully generated at {files_dir} and {dzi_path}")
    return dzi_path, files_dir
