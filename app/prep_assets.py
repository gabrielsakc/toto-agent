"""
One-time preprocessing for desktop-pet assets.

Strategy: flood-fill from the four corners to remove only the studio-white
background that is connected to the image edge. This preserves the dog's
white fur (chest, paws, muzzle) which the old color-key approach destroyed.

Run: python prep_assets.py
"""
from pathlib import Path
import numpy as np
from PIL import Image, ImageFilter
from scipy.ndimage import label, binary_dilation

ASSETS = Path(__file__).parent / "assets"
OUT = Path(__file__).parent / "assets_processed"
OUT.mkdir(exist_ok=True)

SOURCES = [
    # Idle / sleep
    ("sleep_side.png",   "sleep_side.png"),
    ("sleep_front.png",  "sleep_front.png"),
    ("sleep_deep.jpeg",  "sleep_deep.png"),
    # Wake-up transition
    ("wake_headup.jpeg", "wake_headup.png"),
    ("sit_front.jpeg",   "sit_front.png"),
    # Stand / alert variants
    ("stand_front.png",  "stand_front.png"),
    ("stand_alert.jpeg", "stand_alert.png"),
    ("head_tilt.jpeg",   "head_tilt.png"),
    # Bark
    ("bark.jpeg",        "bark.png"),
    ("bark_wide.jpeg",   "bark_wide.png"),
    # Post-run / polish
    ("yawn.jpeg",        "yawn.png"),
    ("shake.jpeg",       "shake.png"),
    ("tail_wag.jpeg",    "tail_wag.png"),
    # Run cycle (side profile facing LEFT, except run_03 and run_06)
    ("run_01.jpeg",      "run_01.png"),
    ("run_02.jpeg",      "run_02.png"),
    ("run_03.jpeg",      "run_03.png"),  # faces RIGHT (airborne extension)
    ("run_04.jpeg",      "run_04.png"),  # trot/landing, faces LEFT
    ("run_05.jpeg",      "run_05.png"),  # push-off, faces LEFT
    ("run_06.jpeg",      "run_06.png"),  # compression (rear view, optional)
    ("run_07.jpeg",      "run_07.png"),  # full extension, faces LEFT
    ("walk_step.jpeg",   "walk_step.png"),
]

LIGHT_THRESHOLD = 195  # min(R,G,B) above this is "light" (bg candidate)
LOW_CHROMA = 20         # max-min below this is "grey-ish" (shadow-like)
EDGE_FEATHER_PX = 1

def remove_bg_connected_components(rgb: Image.Image) -> Image.Image:
    """Remove background + ground-shadow by labeling connected components of
    light pixels and dropping any component that touches the image border.

    This beats a corner flood-fill because shadows fade smoothly from white
    toward grey — they form one connected light region with the pure-white
    backdrop, so they get removed in the same pass.
    """
    rgba = np.array(rgb.convert("RGBA"))
    r, g, b = rgba[..., 0], rgba[..., 1], rgba[..., 2]
    mn = np.minimum(np.minimum(r, g), b).astype(np.int16)
    mx = np.maximum(np.maximum(r, g), b).astype(np.int16)
    chroma = mx - mn
    light_mask = (mn >= LIGHT_THRESHOLD) & (chroma <= LOW_CHROMA)

    labels, _ = label(light_mask)
    border = np.concatenate([
        labels[0, :], labels[-1, :], labels[:, 0], labels[:, -1]
    ])
    bg_labels = np.unique(border)
    bg_labels = bg_labels[bg_labels != 0]
    bg_mask = np.isin(labels, bg_labels)

    # Grow the mask by 1 px to kill single-pixel halos left by anti-aliasing.
    bg_mask = binary_dilation(bg_mask, iterations=1)

    rgba[bg_mask, 3] = 0
    img = Image.fromarray(rgba, "RGBA")
    if EDGE_FEATHER_PX > 0:
        alpha = img.split()[-1].filter(ImageFilter.GaussianBlur(EDGE_FEATHER_PX))
        img.putalpha(alpha)
    return img


# keep old name as an alias so the calling code doesn't need to change
flood_fill_bg_to_alpha = remove_bg_connected_components

def trim(img: Image.Image) -> Image.Image:
    bbox = img.getbbox()
    return img.crop(bbox) if bbox else img

def process(src_name: str, dst_name: str):
    src = ASSETS / src_name
    if not src.exists():
        print(f"  skip: {src_name}")
        return
    img = Image.open(src)
    img = flood_fill_bg_to_alpha(img)
    img = trim(img)
    out = OUT / dst_name
    img.save(out, "PNG", optimize=True)
    print(f"  {src_name} -> {dst_name}  ({img.size[0]}x{img.size[1]})")

if __name__ == "__main__":
    print("Processing assets (flood-fill bg removal)...")
    for src, dst in SOURCES:
        process(src, dst)
    print(f"\nDone. Output: {OUT}")
