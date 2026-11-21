"""Генерирует packaging/thermodrop.ico — капля, залитая палитрой jet.

Запуск: python packaging/make_icon.py
"""

from pathlib import Path

import numpy as np
from matplotlib import colormaps
from PIL import Image, ImageDraw, ImageFilter

SIZE = 512


def drop_mask(size: int) -> Image.Image:
    """Силуэт капли: круг снизу и сходящийся кверху «носик»."""
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    cx, cy, r = size / 2, size * 0.62, size * 0.33
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)
    tip = (cx, size * 0.06)
    d.polygon([tip, (cx - r * 0.93, cy - r * 0.38), (cx + r * 0.93, cy - r * 0.38)], fill=255)
    return mask.filter(ImageFilter.GaussianBlur(1.5))


def main() -> None:
    yy, xx = np.mgrid[0:SIZE, 0:SIZE] / SIZE
    # Холодное ядро (синее) в центре капли, к краям — теплее (красное).
    dist = np.sqrt((xx - 0.5) ** 2 + ((yy - 0.62) * 1.0) ** 2) / 0.36
    rgba = (colormaps["jet"](np.clip(dist, 0, 1)) * 255).astype(np.uint8)
    fill = Image.fromarray(rgba, "RGBA")

    mask = drop_mask(SIZE)
    icon = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    icon.paste(fill, (0, 0), mask)

    outline = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    edge = mask.filter(ImageFilter.MaxFilter(13))
    outline.paste((40, 40, 60, 255), (0, 0), edge)
    outline.alpha_composite(icon)

    # Блик.
    d = ImageDraw.Draw(outline)
    d.ellipse([SIZE * 0.33, SIZE * 0.47, SIZE * 0.43, SIZE * 0.60], fill=(255, 255, 255, 150))

    out = Path(__file__).with_name("thermodrop.ico")
    outline.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    outline.resize((256, 256), Image.LANCZOS).save(out.with_suffix(".png"))
    print("Иконка сохранена:", out)


if __name__ == "__main__":
    main()
