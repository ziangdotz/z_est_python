"""Convert app_logo.png to multi-resolution app_logo.ico."""

from __future__ import annotations

import os

from PIL import Image


def convert_png_to_ico(png_path: str, ico_path: str) -> None:
    """Convert a PNG image to a multi-resolution ICO file.

    Ensures the source image is at least 256x256 before saving.
    """
    img = Image.open(png_path).convert("RGBA")

    if img.width < 256 or img.height < 256:
        img = img.resize((256, 256), Image.Resampling.LANCZOS)

    img.save(
        ico_path,
        format="ICO",
        sizes=[
            (16, 16), (24, 24), (32, 32), (48, 48),
            (64, 64), (128, 128), (256, 256),
        ],
    )


if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    assets_dir = os.path.join(script_dir, "..", "assets")

    png_path = os.path.join(assets_dir, "app_logo.png")
    ico_path = os.path.join(assets_dir, "app_logo.ico")

    convert_png_to_ico(png_path, ico_path)
