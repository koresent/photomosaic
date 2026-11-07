import numpy as np
from PIL import Image, ImageOps

D65_XYZ_REF = np.array([0.95047, 1.00000, 1.08883], dtype=np.float32)
RGB_TO_XYZ_MATRIX = np.array([
    [0.4124564, 0.3575761, 0.1804375],
    [0.2126729, 0.7151522, 0.0721750],
    [0.0193339, 0.1191920, 0.9503041]
], dtype=np.float32)

DELTA = 6.0 / 29.0
DELTA_SQ = DELTA * DELTA


def rgb_to_lab(rgb_array):
    """
    Convert RGB float/int array (0-255) to CIE L*a*b* colorspace.
    Input shape: (..., 3)
    Output shape: (..., 3) with L in [0, 100], a in [-128, 127], b in [-128, 127]
    """
    rgb = np.asarray(rgb_array, dtype=np.float32) / 255.0

    mask = rgb > 0.04045
    rgb_lin = np.where(mask, ((rgb + 0.055) / 1.055) ** 2.4, rgb / 12.92)

    xyz = np.dot(rgb_lin, RGB_TO_XYZ_MATRIX.T)
    xyz_norm = xyz / D65_XYZ_REF

    mask_xyz = xyz_norm > (DELTA ** 3)
    f = np.where(mask_xyz, np.cbrt(xyz_norm), (xyz_norm / (3.0 * DELTA_SQ)) + (4.0 / 29.0))

    L = 116.0 * f[..., 1] - 16.0
    a = 500.0 * (f[..., 0] - f[..., 1])
    b = 200.0 * (f[..., 1] - f[..., 2])

    return np.stack([L, a, b], axis=-1)


def center_crop_to_ratio(image: Image.Image, target_ratio: float = 1.0) -> Image.Image:
    """
    Crop PIL image to the target aspect ratio (width / height) centered.
    """
    w, h = image.size
    current_ratio = w / h

    if abs(current_ratio - target_ratio) < 1e-4:
        return image

    if current_ratio > target_ratio:
        # Image is wider than target: crop width
        new_w = int(round(h * target_ratio))
        offset = (w - new_w) // 2
        return image.crop((offset, 0, offset + new_w, h))
    else:
        # Image is taller than target: crop height
        new_h = int(round(w / target_ratio))
        offset = (h - new_h) // 2
        return image.crop((0, offset, w, offset + new_h))


def extract_image_features(image: Image.Image, use_quadrants: bool = True):
    """
    Extract color features from an image.
    Returns:
      mean_lab: np.ndarray of shape (3,)
      quadrants_lab: np.ndarray of shape (4, 3) or None
      mean_rgb: tuple of (r, g, b)
    """
    rgb_img = image.convert('RGB')
    arr = np.asarray(rgb_img, dtype=np.float32)

    mean_rgb = np.mean(arr, axis=(0, 1))
    mean_lab = rgb_to_lab(mean_rgb)

    quadrants_lab = None
    if use_quadrants:
        h, w, _ = arr.shape
        mid_h = h // 2
        mid_w = w // 2

        q1 = arr[:mid_h, :mid_w]
        q2 = arr[:mid_h, mid_w:]
        q3 = arr[mid_h:, :mid_w]
        q4 = arr[mid_h:, mid_w:]

        q_means_rgb = np.array([
            np.mean(q1, axis=(0, 1)),
            np.mean(q2, axis=(0, 1)),
            np.mean(q3, axis=(0, 1)),
            np.mean(q4, axis=(0, 1))
        ])
        quadrants_lab = rgb_to_lab(q_means_rgb)

    return mean_lab, quadrants_lab, tuple(int(round(x)) for x in mean_rgb)
