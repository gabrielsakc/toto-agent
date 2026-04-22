"""
Extract sprite frames from Veo-generated MP4s.

Pipeline per video:
  1. Decode every Nth frame with OpenCV.
  2. Remove pure-white background + ground shadow via connected-components
     labeling (same algorithm as prep_assets.py).
  3. Compute the union bounding box across all kept frames of this clip
     so every frame crops to the SAME rectangle — this keeps the dog
     locked in place when we flip between frames at runtime.
  4. Save as 000.png, 001.png, ... in assets_processed/seq_<name>/.

Run: python extract_frames.py
"""
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageFilter
from scipy.ndimage import label, binary_dilation

VIDEOS_DIR = Path("D:/toto/videos")
OUT_DIR = Path(__file__).parent / "assets_processed"

# Each video -> (output subdir, stride). stride=2 at 24fps source = 12fps sprite.
SEQUENCES = {
    "run_loop.mp4.mp4":     ("seq_run",    2),
    "bark_loop.mp4.mp4":    ("seq_bark",   2),
    "wake_up.mp4.mp4":      ("seq_wake",   3),
    "yawn.jpeg.mp4":        ("seq_yawn",   3),
    "sleep_breath.mp4.mp4": ("seq_breath", 3),
}

LIGHT_CORE = 200      # "pure bg" core pixel (must be this bright)
LIGHT_EXTEND = 140    # gradient tail pixel (still low-chroma grey/white)
DARK_CORE = 40
DARK_EXTEND = 110
LOW_CHROMA = 22
EDGE_FEATHER_PX = 1
MAX_DIM = 400   # resize so max(w, h) == MAX_DIM. None to keep full size.

# Veo sometimes stamps a small "Veo" logo in the bottom-right corner during
# fade-in / watermarked clips. We blindly zero-alpha that region so it's
# never baked into any sprite frame.
VEO_WATERMARK_BR = (120, 60)  # width, height — clipped from the bottom-right


def _cc_remove(rgba: np.ndarray, extend_mask: np.ndarray,
               core_mask: np.ndarray) -> np.ndarray:
    """Drop any connected component of `extend_mask` that (a) touches the
    image border AND (b) contains at least one pixel in `core_mask`.

    Two-threshold approach: `extend_mask` is a permissive mask that catches
    gradient shadow tails. `core_mask` is the strict "real background" mask.
    We only remove extend components that contain a real-bg core — so gradient
    shadows get eaten (they are contiguous with the pure-white bg), but any
    fur region that happens to be grey-ish is preserved (no core inside it)."""
    labels, _ = label(extend_mask)
    border = np.concatenate([
        labels[0, :], labels[-1, :], labels[:, 0], labels[:, -1],
    ])
    border_labels = np.unique(border)
    border_labels = border_labels[border_labels != 0]
    # Which of those labels contain a core pixel somewhere?
    core_labels = np.unique(labels[core_mask])
    core_labels = core_labels[core_labels != 0]
    good = np.intersect1d(border_labels, core_labels, assume_unique=False)
    bg_mask = np.isin(labels, good)
    bg_mask = binary_dilation(bg_mask, iterations=1)
    rgba[bg_mask, 3] = 0
    return rgba


def _corner_is_light(rgba: np.ndarray) -> bool:
    """Heuristic: check the four corner pixels. If their average brightness is
    high, treat the clip's background as LIGHT; otherwise as DARK."""
    c = np.array([
        rgba[0, 0, :3], rgba[0, -1, :3],
        rgba[-1, 0, :3], rgba[-1, -1, :3],
    ], dtype=np.int16)
    return c.mean() >= 128


def remove_bg_auto(rgba: np.ndarray) -> np.ndarray:
    r, g, b = rgba[..., 0], rgba[..., 1], rgba[..., 2]
    mn = np.minimum(np.minimum(r, g), b).astype(np.int16)
    mx = np.maximum(np.maximum(r, g), b).astype(np.int16)
    chroma = mx - mn
    if _corner_is_light(rgba):
        core = (mn >= LIGHT_CORE) & (chroma <= LOW_CHROMA)
        extend = (mn >= LIGHT_EXTEND) & (chroma <= LOW_CHROMA)
    else:
        core = (mx <= DARK_CORE) & (chroma <= LOW_CHROMA)
        extend = (mx <= DARK_EXTEND) & (chroma <= LOW_CHROMA)
    return _cc_remove(rgba, extend, core)


def mask_watermark(rgba: np.ndarray) -> np.ndarray:
    w_w, w_h = VEO_WATERMARK_BR
    rgba[-w_h:, -w_w:, 3] = 0
    return rgba


def bbox_from_alpha(rgba: np.ndarray):
    a = rgba[..., 3]
    rows = np.any(a > 0, axis=1)
    cols = np.any(a > 0, axis=0)
    if not rows.any():
        return None
    y0, y1 = np.where(rows)[0][[0, -1]]
    x0, x1 = np.where(cols)[0][[0, -1]]
    return int(x0), int(y0), int(x1) + 1, int(y1) + 1


def feather(rgba: np.ndarray) -> Image.Image:
    img = Image.fromarray(rgba, "RGBA")
    if EDGE_FEATHER_PX > 0:
        alpha = img.split()[-1].filter(ImageFilter.GaussianBlur(EDGE_FEATHER_PX))
        img.putalpha(alpha)
    return img


def extract(video_path: Path, out_dir: Path, stride: int):
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print(f"  ERROR: cannot open {video_path.name}")
        return
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    out_fps = src_fps / stride

    out_dir.mkdir(parents=True, exist_ok=True)
    for p in out_dir.glob("*.png"):
        p.unlink()

    # Pass 1: decode, remove bg, remember frame + bbox.
    kept = []
    frame_i = 0
    while True:
        ok, bgr = cap.read()
        if not ok:
            break
        if frame_i % stride == 0:
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            alpha = np.full((rgb.shape[0], rgb.shape[1], 1), 255, dtype=np.uint8)
            rgba = np.concatenate([rgb, alpha], axis=2)
            rgba = mask_watermark(rgba)
            rgba = remove_bg_auto(rgba)
            bb = bbox_from_alpha(rgba)
            if bb is not None:
                kept.append((rgba, bb))
        frame_i += 1
    cap.release()

    if not kept:
        print("  no usable frames")
        return

    x0 = min(b[0] for _, b in kept)
    y0 = min(b[1] for _, b in kept)
    x1 = max(b[2] for _, b in kept)
    y1 = max(b[3] for _, b in kept)
    w, h = x1 - x0, y1 - y0
    print(f"  {len(kept)} frames  out_fps={out_fps:.1f}  bbox={w}x{h}")

    # Pass 2: crop to union bbox + optional resize + save.
    total_bytes = 0
    for i, (rgba, _) in enumerate(kept):
        cropped = rgba[y0:y1, x0:x1]
        img = feather(cropped)
        if MAX_DIM is not None and max(img.size) > MAX_DIM:
            scale = MAX_DIM / max(img.size)
            new_size = (int(round(img.width * scale)), int(round(img.height * scale)))
            img = img.resize(new_size, Image.LANCZOS)
        out_path = out_dir / f"{i:03d}.png"
        img.save(out_path, "PNG", optimize=True)
        total_bytes += out_path.stat().st_size
    print(f"  saved {len(kept)} PNGs {img.size[0]}x{img.size[1]}, "
          f"total {total_bytes/1024/1024:.1f} MB")


if __name__ == "__main__":
    for video_name, (subdir, stride) in SEQUENCES.items():
        src = VIDEOS_DIR / video_name
        if not src.exists():
            print(f"SKIP: {video_name} not found")
            continue
        print(f"\n== {video_name} -> {subdir}/")
        extract(src, OUT_DIR / subdir, stride)
    print("\nDone.")
