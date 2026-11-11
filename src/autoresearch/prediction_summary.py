"""Descriptive ranges from already validated saved OOF predictions."""


def summarize_oof_range(rows):
    """Describe saved values without clipping them or evaluating scientific validity."""
    if not rows:
        return None
    observed = [row["observed"] for row in rows]
    predicted = [row["predicted"] for row in rows]
    lower, upper = min(observed), max(observed)
    return {
        "n": len(rows),
        "observed_min": lower,
        "observed_max": upper,
        "predicted_min": min(predicted),
        "predicted_max": max(predicted),
        "negative_predictions": sum(value < 0 for value in predicted),
        "below_observed_min": sum(value < lower for value in predicted),
        "above_observed_max": sum(value > upper for value in predicted),
        "scientific_validation": False,
    }
