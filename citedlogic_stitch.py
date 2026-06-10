#!/usr/bin/env python3
"""Vertically stitch overlapping phone screenshots into one tall PNG of the full
answer. The CitedLogic capture takes a series of frames while scrolling down the
answer; consecutive frames overlap, so we detect the overlap and append only the
new content — producing a single seamless "full answer" image.

Used by audit_dispatch_http (capture mode). Pure PIL + numpy; no phone needed,
so the overlap logic is unit-testable offline (see self-test at bottom).
"""
from __future__ import annotations

import numpy as np
from PIL import Image

# Width screenshots are downsampled to for the overlap search (speed). The match
# is robust at low res; we crop the full-res frame using the detected offset.
_MATCH_W = 144
_BAND = 24          # rows (downsampled) of base's bottom edge used as match template
_MAX_DIFF = 22.0    # mean abs pixel diff above which "no overlap" is assumed


def _to_match_array(img: Image.Image) -> np.ndarray:
    scale = _MATCH_W / img.width
    small = img.resize((_MATCH_W, max(1, int(img.height * scale))), Image.BILINEAR)
    return np.asarray(small.convert("RGB"), dtype=np.int16)


def _new_content_offset(base_small: np.ndarray, frame_small: np.ndarray) -> tuple[int, float]:
    """Return (offset_in_small, score): the y in the downsampled next-frame BELOW
    which content is new (not already in base). offset == frame height ⇒ no new
    content (bottom reached). Matches base's bottom BAND against the frame."""
    hb, hf = base_small.shape[0], frame_small.shape[0]
    band = min(_BAND, hb, hf // 2)
    if band < 4:
        return hf, 0.0
    base_strip = base_small[hb - band:hb]
    best_d, best_score = 0, float("inf")
    for d in range(0, hf - band):
        score = float(np.abs(frame_small[d:d + band] - base_strip).mean())
        if score < best_score:
            best_score, best_d = score, d
    # new content in the frame begins after the matched strip
    return best_d + band, best_score


def stitch_frames(frame_paths: list[str], out_path: str,
                  top_crop: int = 0, bottom_crop: int = 0) -> str | None:
    """Stitch the frames (top→bottom scroll order) into one tall PNG at out_path.
    Stops appending once a frame adds no new content (answer bottom reached).

    top_crop / bottom_crop remove the device's FIXED chrome (status+URL bar at the
    top, the input/nav bar at the bottom) from every frame before stitching — that
    chrome repeats identically in each frame and would otherwise be duplicated in
    the output and confuse overlap detection. Tune per device; 0 = no crop."""
    paths = [p for p in frame_paths if p]
    if not paths:
        return None
    imgs = []
    for p in paths:
        im = Image.open(p).convert("RGB")
        if top_crop or bottom_crop:
            im = im.crop((0, top_crop, im.width, max(top_crop + 1, im.height - bottom_crop)))
        imgs.append(im)
    base = imgs[0]
    base_small = _to_match_array(base)
    scale = base.height / base_small.shape[0]  # full-res rows per small row
    for frame in imgs[1:]:
        if frame.width != base.width:
            frame = frame.resize((base.width, int(frame.height * base.width / frame.width)))
        frame_small = _to_match_array(frame)
        off_small, score = _new_content_offset(base_small, frame_small)
        if score > _MAX_DIFF:
            # No reliable overlap (scrolled too far / page changed) — append whole
            # frame so nothing is silently dropped.
            off_full = 0
        else:
            off_full = int(round(off_small * scale))
        new_part = frame.crop((0, off_full, frame.width, frame.height))
        if new_part.height <= 2:
            break  # frame was fully contained in base → bottom reached
        combined = Image.new("RGB", (base.width, base.height + new_part.height), "white")
        combined.paste(base, (0, 0))
        combined.paste(new_part, (0, base.height))
        base = combined
        base_small = _to_match_array(base)
        scale = base.height / base_small.shape[0]
    base.save(out_path)
    return out_path


# ── offline self-test ──────────────────────────────────────────────────────
# Slice a real screenshot into overlapping frames, stitch them back, and confirm
# the result reconstructs the original height (±a few px). No phone required.
if __name__ == "__main__":
    import sys, tempfile, os

    src = sys.argv[1] if len(sys.argv) > 1 else "/tmp/cl_current_screen.png"
    orig = Image.open(src).convert("RGB")
    W, H = orig.size
    view = 900          # simulated viewport height
    step = 520          # simulated scroll step (so frames overlap by view-step)
    tmp = tempfile.mkdtemp()
    # Real frames are always full viewport height; the last scroll position clamps
    # to [H-view, H] (you can't scroll past the bottom) — no white padding.
    positions = list(range(0, max(1, H - view), step))
    if not positions or positions[-1] != H - view:
        positions.append(max(0, H - view))
    paths = []
    for y in positions:
        frame = orig.crop((0, y, W, min(y + view, H)))
        p = os.path.join(tmp, f"f{len(paths):02d}.png")
        frame.save(p)
        paths.append(p)
    out = os.path.join(tmp, "stitched.png")
    stitch_frames(paths, out)
    stitched = Image.open(out)
    print(f"source     : {W}x{H}")
    print(f"frames      : {len(paths)} (view={view}, step={step})")
    print(f"stitched    : {stitched.size[0]}x{stitched.size[1]}")
    drift = stitched.size[1] - H
    print(f"height drift: {drift}px  ->  {'OK' if abs(drift) <= 12 else 'FAIL (overlap detection off)'}")
