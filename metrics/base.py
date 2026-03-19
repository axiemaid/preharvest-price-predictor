"""
Base class for all metrics.

To add a new metric:
1. Create a new file in metrics/ (e.g. temperature.py)
2. Subclass BaseMetric
3. Implement score_plants()
4. Add to config.json with enabled: true and a weight

score_plants() receives the full snapshot data and returns a dict
of {cell_id: float} where float is 0.0-1.0 (or up to score_cap).
"""

from abc import ABC, abstractmethod


class BaseMetric(ABC):
    """Interface for a pricing metric."""

    name: str = "base"
    weight: float = 1.0

    def __init__(self, config: dict):
        """
        Args:
            config: The metric-specific config from config.json
                    e.g. {"enabled": true, "weight": 1.0, ...}
        """
        self.weight = config.get("weight", 1.0)
        self.config = config

    @abstractmethod
    def score_plants(self, snapshot: dict) -> dict:
        """
        Score each plant from a single snapshot (one capture).

        Args:
            snapshot: dict with at least:
                - "measurements": list of per-cell dicts from seedling tracker
                  Each has: id, row, col, green_pixels, total_pixels, coverage_pct
                - "timestamp": str
                - Any additional sensor data attached by other sources

        Returns:
            dict of {cell_id (int): score (float)}
            Score is relative — 1.0 = average, >1 = above average.
        """
        pass
