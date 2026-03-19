"""
Annotator
=========

Takes a raw capture image + seedling tracker analysis data + prices,
produces an annotated image with:
  - Green pixel overlay (highlight detected plant area)
  - Grid lines
  - Plant number (bottom-left of each cell)
  - Price in sats (upper-right of each cell)
  - Summary bar (total crop value)
"""

import cv2
import numpy as np


def draw_annotated(img, mask, cells, col_bounds, row_bounds, prices, config):
    """
    Draw the priced annotated image.

    Args:
        img: BGR image (full frame, same as analyzer input)
        mask: binary green mask (same size as img)
        cells: list of cell dicts from grid (id, row, col, x, y, w, h)
        col_bounds: list of column boundary x positions
        row_bounds: list of row boundary y positions
        prices: dict of {cell_id: price_sats}
        config: full config dict

    Returns:
        Annotated BGR image
    """
    out = img.copy()
    h, w = out.shape[:2]

    # Green overlay on detected pixels
    overlay = np.zeros_like(out)
    overlay[mask > 0] = (0, 220, 0)
    out = cv2.addWeighted(out, 0.7, overlay, 0.3, 0)

    # Grid lines
    for x in col_bounds:
        cv2.line(out, (x, 0), (x, h), (100, 100, 100), 1)
    for y in row_bounds:
        cv2.line(out, (0, y), (w, y), (100, 100, 100), 1)

    # Per-cell labels
    for cell in cells:
        cid = cell["id"]
        r, c = cell["row"], cell["col"]
        x1 = col_bounds[c]
        y1 = row_bounds[r]
        x2 = col_bounds[c + 1]
        y2 = row_bounds[r + 1]

        price = prices.get(cid, 0)

        # Plant number — bottom-left (inset from edges)
        cv2.putText(out, f"#{cid}",
                    (x1 + 6, y2 - 16),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)

        # Price — upper-right (inset from edges)
        price_str = _format_sats(price)
        text_size = cv2.getTextSize(price_str, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)[0]
        tx = x2 - text_size[0] - 6
        ty = y1 + 24

        # Color: brighter yellow for higher prices
        color = (0, 255, 255) if price > 0 else (100, 100, 100)
        cv2.putText(out, price_str,
                    (tx, ty),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

    # Summary bar — total crop value
    total_value = sum(prices.values())
    active = sum(1 for p in prices.values() if p > 0)
    summary = f"Crop value: {_format_sats(total_value)} | Active: {active}/{len(cells)}"
    cv2.rectangle(out, (0, 0), (w, 28), (0, 0, 0), -1)
    cv2.putText(out, summary, (8, 19),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)

    return out


def _format_sats(sats):
    """Format sats with comma separator."""
    if sats >= 1000:
        return f"{sats:,} sats"
    return f"{sats} sats"
