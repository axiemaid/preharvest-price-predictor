# Pre-Harvest Price Predictor

Speculative pricing for hydroponic lettuce based on growth metrics. Reads analysis data from [seedling-tracker](../seedling-tracker/), computes per-plant prices in sats, and produces annotated images.

## How It Works

1. Reads `growth_log.csv` from seedling-tracker
2. Scores each plant using enabled metrics (currently: green pixel coverage)
3. Converts scores to sats prices (score × base price)
4. Overlays prices on raw capture images with green highlighting

### Pricing Model

- Each plant is scored **relative to its peers** — no fixed "mature" threshold
- Green pixel count is compared against the **trimmed mean** (top/bottom 10% outliers removed)
- Score of 1.0 = average plant = base price (default: 50,000 sats)
- Score capped at 2.0 to prevent outlier valuations
- Dead plants (0 green pixels) = 0 sats

## Usage

```bash
# First: make sure seedling-tracker has analyzed images
cd ../seedling-tracker && python3 analyze.py

# Price all new captures
python3 predict.py

# Price all captures (including already processed)
python3 predict.py --all

# Reprocess everything
python3 predict.py --reprocess
```

Output goes to `output/` — one `_priced.jpg` per capture.

## Adding Metrics

Metrics are modular plugins in `metrics/`. To add a new one:

1. Create `metrics/your_metric.py`
2. Subclass `BaseMetric` from `metrics/base.py`
3. Implement `score_plants(snapshot) -> {cell_id: score}`
4. Register it in `pricing.py` → `METRIC_CLASSES`
5. Enable it in `config.json`:

```json
{
  "metrics": {
    "your_metric": { "enabled": true, "weight": 0.5 }
  }
}
```

Scores from all enabled metrics are combined via weighted average.

### Example: Temperature Metric

```python
from metrics.base import BaseMetric

class TemperatureMetric(BaseMetric):
    name = "temperature"

    def score_plants(self, snapshot):
        temp = snapshot.get("temperature")  # from sensor CSV
        if temp is None:
            return {}
        # Optimal 18-24°C = 1.0, degrade outside range
        score = max(0, 1.0 - abs(temp - 21) / 15)
        # Same score for all plants (environmental metric)
        ids = [m["id"] for m in snapshot["measurements"]]
        return {cid: score for cid in ids}
```

## Config

| Key | Default | Description |
|-----|---------|-------------|
| `base_price_sats` | 50000 | Price for an average plant |
| `score_cap` | 2.0 | Max score multiplier |
| `trim_pct` | 10 | Outlier trim percentage |
| `seedling_tracker_dir` | `../seedling-tracker` | Path to tracker project |
| `metrics` | — | Enabled metrics + weights |

## Project Structure

```
├── predict.py          # CLI entry point
├── config.json         # Pricing config
├── pricing.py          # Score → sats engine
├── annotate.py         # Image overlay renderer
├── metrics/
│   ├── base.py         # BaseMetric interface
│   └── green_coverage.py  # Pixel count vs trimmed mean
├── output/             # Priced annotated images
└── README.md
```
