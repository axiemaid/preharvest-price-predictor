"""
Green Coverage Metric
=====================

Scores each plant by its green pixel count relative to the
trimmed mean of all plants. Uses raw pixel count (not percentage)
since grid cells can be different sizes after calibration.

Score = plant_pixels / trimmed_mean
  - 1.0 = average plant
  - >1.0 = above average (premium)
  - <1.0 = below average (discount)
  - 0.0 = dead/empty
"""

import numpy as np
from .base import BaseMetric


class GreenCoverageMetric(BaseMetric):
    name = "green_coverage"

    def score_plants(self, snapshot: dict) -> dict:
        measurements = snapshot.get("measurements", [])
        if not measurements:
            return {}

        trim_pct = self.config.get("trim_pct", 10)

        # Raw green pixel counts
        counts = {m["id"]: m["green_pixels"] for m in measurements}
        values = list(counts.values())

        # Trimmed mean — remove top/bottom N% to ignore outliers
        trimmed_mean = self._trimmed_mean(values, trim_pct)

        if trimmed_mean <= 0:
            # All plants are dead or too few data points
            return {cid: 0.0 for cid in counts}

        scores = {}
        for cid, px in counts.items():
            scores[cid] = px / trimmed_mean if px > 0 else 0.0

        return scores

    @staticmethod
    def _trimmed_mean(values, trim_pct):
        """Mean after removing top/bottom trim_pct% of values."""
        if not values:
            return 0.0

        arr = sorted(values)
        n = len(arr)
        trim_count = max(1, int(n * trim_pct / 100))

        trimmed = arr[trim_count:-trim_count] if trim_count < n // 2 else arr
        return float(np.mean(trimmed)) if trimmed else 0.0
