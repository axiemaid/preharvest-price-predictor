"""
Pricing Engine
==============

Loads enabled metrics, scores each plant, computes weighted
average score, and converts to sats price.

price = score * base_price_sats
score = weighted average of all metric scores, capped at score_cap
"""

from metrics.green_coverage import GreenCoverageMetric

# Registry of available metrics — add new ones here
METRIC_CLASSES = {
    "green_coverage": GreenCoverageMetric,
}


def load_metrics(config: dict) -> list:
    """Load enabled metrics from config."""
    metrics = []
    for name, metric_cfg in config.get("metrics", {}).items():
        if not metric_cfg.get("enabled", False):
            continue
        cls = METRIC_CLASSES.get(name)
        if cls is None:
            print(f"  WARNING: unknown metric '{name}', skipping")
            continue
        metrics.append(cls(metric_cfg))
    return metrics


def price_plants(snapshot: dict, config: dict) -> dict:
    """
    Compute per-plant prices for a single snapshot.

    Args:
        snapshot: dict with "measurements" list from seedling tracker
        config: full config.json contents

    Returns:
        dict of {cell_id: price_sats (int)}
    """
    base_price = config.get("base_price_sats", 50000)
    score_cap = config.get("score_cap", 2.0)

    metrics = load_metrics(config)
    if not metrics:
        return {}

    # Collect scores from each metric
    all_scores = {}  # {cell_id: [(score, weight), ...]}
    for metric in metrics:
        scores = metric.score_plants(snapshot)
        for cid, score in scores.items():
            if cid not in all_scores:
                all_scores[cid] = []
            all_scores[cid].append((score, metric.weight))

    # Weighted average per plant, capped
    prices = {}
    for cid, score_list in all_scores.items():
        total_weight = sum(w for _, w in score_list)
        if total_weight <= 0:
            prices[cid] = 0
            continue

        weighted_score = sum(s * w for s, w in score_list) / total_weight
        weighted_score = min(weighted_score, score_cap)
        prices[cid] = int(weighted_score * base_price)

    return prices
