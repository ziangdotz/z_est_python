import os
from PIL import Image

script_dir = os.path.dirname(os.path.abspath(__file__))
assets_dir = os.path.join(script_dir, '..', 'assets')

png_path = os.path.join(assets_dir, 'app_logo.png')
ico_path = os.path.join(assets_dir, 'app_logo.ico')

# 从高分辨率源图生成，Pillow 会自动做高质量缩放
img = Image.open(png_path).convert('RGBA')

# 确保源图至少 256x256，不足则先放大
if img.width < 256 or img.height < 256:
    img = img.resize((256, 256), Image.Resampling.LANCZOS)

img.save(
    ico_path,
    format='ICO',
    sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
           (64, 64), (128, 128), (256, 256)]
)
