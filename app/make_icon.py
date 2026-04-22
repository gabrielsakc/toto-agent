"""One-off helper: turn a source PNG into a multi-resolution .ico for the .exe."""
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).parent
# Pick a clear, recognizable pose.
SRC = ROOT / "assets_processed" / "stand_front.png"
DST = ROOT / "icon.ico"

SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

img = Image.open(SRC).convert("RGBA")
# Square-pad on a transparent canvas so the icon doesn't get squished at small sizes.
side = max(img.size)
canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
canvas.paste(img, ((side - img.width) // 2, (side - img.height) // 2))
canvas.save(DST, format="ICO", sizes=SIZES)
print(f"wrote {DST}")
