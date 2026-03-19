#!/usr/bin/env python3
"""
Pre-Harvest Price Predictor
============================

Processes seedling tracker data and produces priced annotated images.

Usage:
    python3 predict.py                        # Process latest capture
    python3 predict.py --all                  # Process all captures
    python3 predict.py --image PATH           # Process specific image
    python3 predict.py --reprocess            # Redo all
"""

import argparse
import csv
import json
import os
import sys
from pathlib import Path

import cv2
import numpy as np

from pricing import price_plants
from annotate import draw_annotated

# ==================== CONFIG ====================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.json")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output")
PRICE_CSV = os.path.join(OUTPUT_DIR, "price_log.csv")
STATE_FILE = os.path.join(OUTPUT_DIR, ".state.json")


def load_config():
    with open(CONFIG_FILE) as f:
        return json.load(f)


def ensure_dirs():
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"processed": []}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def load_csv_snapshots(csv_path):
    """
    Load growth_log.csv and group rows by timestamp into snapshots.

    Returns:
        dict of {timestamp_str: {"timestamp": str, "measurements": [...]}}
    """
    snapshots = {}
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts = row["timestamp"]
            if ts not in snapshots:
                snapshots[ts] = {"timestamp": ts, "measurements": []}
            snapshots[ts]["measurements"].append({
                "id": int(row["cell_id"]),
                "row": int(row["row"]),
                "col": int(row["col"]),
                "green_pixels": int(row["green_pixels"]),
                "total_pixels": int(row["total_pixels"]),
                "coverage_pct": float(row["coverage_pct"]),
            })
    return snapshots


def get_grid_params(config):
    """
    Import grid parameters from seedling tracker's analyze.py.
    Returns (grid_rows, grid_cols, custom_col_bounds, custom_row_bounds).
    """
    tracker_dir = os.path.join(SCRIPT_DIR, config["seedling_tracker_dir"])
    tracker_dir = os.path.normpath(tracker_dir)

    # Read analyze.py and extract constants
    analyze_path = os.path.join(tracker_dir, "analyze.py")
    grid_rows = 4
    grid_cols = 6
    col_bounds = None
    row_bounds = None

    with open(analyze_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith("GRID_ROWS"):
                grid_rows = int(line.split("=")[1].strip())
            elif line.startswith("GRID_COLS"):
                grid_cols = int(line.split("=")[1].strip())
            elif line.startswith("CUSTOM_COL_BOUNDS") and "None" not in line:
                col_bounds = json.loads(line.split("=", 1)[1].strip())
            elif line.startswith("CUSTOM_ROW_BOUNDS") and "None" not in line:
                row_bounds = json.loads(line.split("=", 1)[1].strip())

    return grid_rows, grid_cols, col_bounds, row_bounds


def compute_bounds(img_h, img_w, grid_rows, grid_cols, col_bounds, row_bounds):
    """Compute actual pixel boundaries for grid."""
    if col_bounds is None:
        col_bounds = [round(c * img_w / grid_cols) for c in range(grid_cols + 1)]
    if row_bounds is None:
        row_bounds = [round(r * img_h / grid_rows) for r in range(grid_rows + 1)]
    return col_bounds, row_bounds


def get_cells(img_h, img_w, grid_rows, grid_cols, col_bounds, row_bounds, margin_pct=5):
    """Build cell list matching seedling tracker's grid."""
    cells = []
    for r in range(grid_rows):
        for c in range(grid_cols):
            cid = r * grid_cols + c + 1
            x1 = col_bounds[c]
            x2 = col_bounds[c + 1]
            y1 = row_bounds[r]
            y2 = row_bounds[r + 1]
            cw = x2 - x1
            ch = y2 - y1
            mx = int(cw * margin_pct / 100)
            my = int(ch * margin_pct / 100)
            cells.append({
                "id": cid, "row": r, "col": c,
                "x": x1 + mx, "y": y1 + my,
                "w": cw - 2 * mx, "h": ch - 2 * my,
            })
    return cells


def segment_green(img):
    """HSV green segmentation (same params as seedling tracker)."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array([25, 30, 100]), np.array([80, 255, 255]))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    return mask


def find_image_for_timestamp(ts_str, images_dir):
    """Find the raw capture image matching a timestamp."""
    # Try exact match first
    for ext in [".jpg", ".jpeg", ".png"]:
        path = os.path.join(images_dir, ts_str + ext)
        if os.path.exists(path):
            return path

    # Try without seconds
    ts_short = ts_str[:16]  # YYYY-MM-DD_HH-MM
    for f in os.listdir(images_dir):
        if f.startswith(ts_short) and f.lower().endswith((".jpg", ".jpeg", ".png")):
            return os.path.join(images_dir, f)

    return None


def process_snapshot(ts_str, snapshot, config, images_dir, grid_params):
    """Process one snapshot: price + annotate."""
    grid_rows, grid_cols, custom_cols, custom_rows = grid_params

    # Find raw image
    img_path = find_image_for_timestamp(ts_str, images_dir)
    if img_path is None:
        print(f"  {ts_str} | SKIP — no raw image found")
        return None

    img = cv2.imread(img_path)
    if img is None:
        print(f"  {ts_str} | SKIP — can't load {img_path}")
        return None

    h, w = img.shape[:2]

    # Grid
    col_bounds, row_bounds = compute_bounds(h, w, grid_rows, grid_cols, custom_cols, custom_rows)
    cells = get_cells(h, w, grid_rows, grid_cols, col_bounds, row_bounds)

    # Green mask
    mask = segment_green(img)

    # Price
    prices = price_plants(snapshot, config)

    # Annotate
    annotated = draw_annotated(img, mask, cells, col_bounds, row_bounds, prices, config)

    # Save
    out_path = os.path.join(OUTPUT_DIR, f"{ts_str}_priced.jpg")
    cv2.imwrite(out_path, annotated, [cv2.IMWRITE_JPEG_QUALITY, 90])

    # Log prices to CSV
    log_prices_csv(ts_str, prices)

    total = sum(prices.values())
    active = sum(1 for p in prices.values() if p > 0)
    print(f"  {ts_str} | {active}/{grid_rows * grid_cols} active | crop value: {total:,} sats")

    return prices


def log_prices_csv(timestamp, prices):
    """Append per-plant prices to CSV."""
    file_exists = os.path.exists(PRICE_CSV)
    with open(PRICE_CSV, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "cell_id", "price_sats"])
        for cid in sorted(prices.keys()):
            writer.writerow([timestamp, cid, prices[cid]])


def main():
    parser = argparse.ArgumentParser(description="Pre-Harvest Price Predictor")
    parser.add_argument("--all", action="store_true", help="Process all captures")
    parser.add_argument("--image", type=str, help="Process specific image timestamp")
    parser.add_argument("--reprocess", action="store_true", help="Redo all")
    args = parser.parse_args()

    config = load_config()
    ensure_dirs()

    tracker_dir = os.path.normpath(
        os.path.join(SCRIPT_DIR, config["seedling_tracker_dir"])
    )
    csv_path = os.path.join(tracker_dir, "analysis", "growth_log.csv")
    images_dir = os.path.join(tracker_dir, "images")

    if not os.path.exists(csv_path):
        print(f"ERROR: No growth data at {csv_path}")
        print("Run seedling-tracker analyze.py first.")
        sys.exit(1)

    snapshots = load_csv_snapshots(csv_path)
    grid_params = get_grid_params(config)

    state = load_state()
    if args.reprocess:
        state = {"processed": []}
        if os.path.exists(PRICE_CSV):
            os.remove(PRICE_CSV)

    if args.image:
        ts = args.image
        if ts in snapshots:
            process_snapshot(ts, snapshots[ts], config, images_dir, grid_params)
        else:
            print(f"ERROR: No data for timestamp '{ts}'")
            sys.exit(1)
    else:
        # Process new (or all with --all/--reprocess)
        to_process = sorted(snapshots.keys())
        if not args.all and not args.reprocess:
            to_process = [t for t in to_process if t not in state["processed"]]

        if not to_process:
            print("Nothing new to process. Use --all or --reprocess.")
            return

        print(f"Pricing {len(to_process)} capture(s)...\n")

        for ts in to_process:
            result = process_snapshot(ts, snapshots[ts], config, images_dir, grid_params)
            if result is not None:
                state["processed"].append(ts)

        save_state(state)
        print(f"\nDone. Output in {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
