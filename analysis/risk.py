from collections import defaultdict
from math import isnan

from scipy.stats import linregress

from trend import (
    build_weekly_series,
    get_mean,
    get_stdev,
    find_rolling_spikes
)


MIN_WEEKS_FOR_TREND = 6
MIN_WEEKS_FOR_RECENT_TREND = 4

RECENT_LOOKBACK_WEEKS = 8
FORECAST_WEEKS_AHEAD = 4

SPIKE_WINDOW = 8
SPIKE_Z_THRESHOLD = 2.0

TREND_P_SIGNIFICANCE = 0.05

DEFAULT_WEIGHTS = {
    "trend": 0.30,
    "recent_trend": 0.15,
    "volatility": 0.15,
    "volume": 0.15,
    "spike": 0.15,
    "unresolved": 0.10
}


def clip(value, low=0.0, high=1.0):
    return max(low, min(high, value))


def normalize(value, min_value, max_value):
    if max_value <= min_value:
        return 0.0

    return clip(
        (value - min_value) /
        (max_value - min_value)
    )


def calculate_linear_trend(weekly_counts):
    n = len(weekly_counts)

    if n < 2:
        return {
            "status": "INSUFFICIENT_DATA",
            "slope": 0.0, "intercept": 0.0, "r_value": 0.0, "p_value": 1.0, "significant": False
        }

    week_index = list(range(n))
    regression = linregress(week_index, weekly_counts)

    slope = float(regression.slope)
    intercept = float(regression.intercept)
    r_value = float(regression.rvalue)
    p_value = float(regression.pvalue)

    if isnan(slope) or isnan(intercept) or isnan(r_value) or isnan(p_value):
        return {
            "status": "INVALID_DATA",
            "slope": 0.0, "intercept": 0.0, "r_value": 0.0, "p_value": 1.0, "significant": False
        }

    return {
        "status": "OK",
        "slope": slope,
        "intercept": intercept,
        "r_value": r_value,
        "p_value": p_value,
        "significant": p_value < TREND_P_SIGNIFICANCE
    }


def compute_trend_metrics(weekly_counts):
    if len(weekly_counts) < MIN_WEEKS_FOR_TREND:
        return {
            "status": "INSUFFICIENT_DATA",
            "slope": 0.0, "intercept": 0.0, "r_value": 0.0, "p_value": 1.0, "significant": False
        }
    return calculate_linear_trend(weekly_counts)


def compute_recent_trend_metrics(weekly_counts):
    if len(weekly_counts) < MIN_WEEKS_FOR_RECENT_TREND:
        return {
            "status": "INSUFFICIENT_DATA",
            "slope": 0.0, "intercept": 0.0, "r_value": 0.0, "p_value": 1.0, "significant": False
        }

    recent_counts = weekly_counts[-RECENT_LOOKBACK_WEEKS:]

    if len(recent_counts) < MIN_WEEKS_FOR_RECENT_TREND:
        return {
            "status": "INSUFFICIENT_DATA",
            "slope": 0.0, "intercept": 0.0, "r_value": 0.0, "p_value": 1.0, "significant": False
        }

    return calculate_linear_trend(recent_counts)


def compute_trend_score(trend_metrics):
    if trend_metrics["status"] != "OK":
        return 0.0
    slope = trend_metrics["slope"]
    if slope <= 0:
        return 0.0
    strength = clip(abs(trend_metrics["r_value"]))
    if not trend_metrics["significant"]:
        strength *= 0.5
    return round(strength, 3)


def compute_recent_trend_score(recent_trend_metrics):
    if recent_trend_metrics["status"] != "OK":
        return 0.0
    slope = recent_trend_metrics["slope"]
    if slope <= 0:
        return 0.0
    strength = clip(abs(recent_trend_metrics["r_value"]))
    if not recent_trend_metrics["significant"]:
        strength *= 0.5
    return round(strength, 3)


def forecast_future_count(trend_metrics, weekly_counts, weeks_ahead=FORECAST_WEEKS_AHEAD):
    if trend_metrics["status"] != "OK":
        return None
    if not weekly_counts:
        return None
    last_index = len(weekly_counts) - 1
    future_index = last_index + weeks_ahead
    forecast = trend_metrics["slope"] * future_index + trend_metrics["intercept"]
    return round(max(forecast, 0), 2)


def compute_volatility_score(weekly_counts):
    if not weekly_counts:
        return 0.0
    mean_value = get_mean(weekly_counts)
    if mean_value <= 0:
        return 0.0
    stdev_value = get_stdev(weekly_counts)
    coefficient_of_variation = stdev_value / mean_value
    return round(normalize(coefficient_of_variation, 0, 2.0), 3)


def compute_recent_spike_score(spikes_for_group, recent_weeks):
    if not recent_weeks:
        return 0.0
    recent_week_set = set(recent_weeks)
    severity_weight = {"HIGH": 1.0, "MEDIUM": 0.6, "NORMAL": 0.0, "UNKNOWN": 0.0}
    relevant_spikes = [s for s in spikes_for_group if s["week"] in recent_week_set]
    if not relevant_spikes:
        return 0.0
    total_weight = 0.0
    for spike in relevant_spikes:
        severity = spike.get("severity", "UNKNOWN")
        total_weight += severity_weight.get(severity, 0.0)
    score = total_weight / len(recent_week_set)
    return round(clip(score), 3)


def compute_volume_score(recent_total, all_group_recent_totals):
    if not all_group_recent_totals:
        return 0.0
    maximum = max(all_group_recent_totals)
    if maximum <= 0:
        return 0.0
    return round(normalize(recent_total, 0, maximum), 3)


def compute_unresolved_ratio(cases_in_group, unresolved_status_ids):
    if not unresolved_status_ids:
        return None
    if not cases_in_group:
        return None
    total = len(cases_in_group)
    unresolved_count = sum(1 for c in cases_in_group if c.get("case_status_id") in unresolved_status_ids)
    return round(unresolved_count / total, 3)


def get_effective_weights(unresolved_ratio):
    weights = dict(DEFAULT_WEIGHTS)
    if unresolved_ratio is None:
        unresolved_weight = weights.pop("unresolved")
        remaining_total = sum(weights.values())
        if remaining_total > 0:
            for key in weights:
                weights[key] += unresolved_weight * (weights[key] / remaining_total)
    return weights


def classify_risk_level(score):
    if score >= 75:
        return "CRITICAL"
    if score >= 50:
        return "HIGH"
    if score >= 25:
        return "MEDIUM"
    return "LOW"


def calculate_data_confidence(weekly_count, trend_status, recent_trend_status):
    if weekly_count < MIN_WEEKS_FOR_TREND:
        return {"level": "LOW", "score": 0.25}
    if trend_status == "OK" and recent_trend_status == "OK":
        if weekly_count >= 12:
            return {"level": "HIGH", "score": 1.0}
        return {"level": "MEDIUM", "score": 0.75}
    return {"level": "MEDIUM", "score": 0.5}


def build_risk_report(cases, unresolved_status_ids=None, weeks_ahead=FORECAST_WEEKS_AHEAD):
    """
    Grouping is now (district_id, unit_id, crime_major_head_id) -- police
    station is a first-class part of the group key, not just district +
    crime type. A station with 2 theft cases and a neighboring station with
    45 theft cases in the same district are now two separate rows, never
    combined into one district-level number.

    NOTE: this relies on trend.py's build_weekly_series() and
    find_rolling_spikes() already grouping/tagging by unit_id too -- if you
    swap in your real trend.py, make sure its group key and each spike dict
    include unit_id (see the chat note for the exact two changes needed).
    """
    weekly_series = build_weekly_series(cases)

    if not weekly_series:
        return []

    all_spikes = find_rolling_spikes(cases, window=SPIKE_WINDOW, z_threshold=SPIKE_Z_THRESHOLD)

    spikes_by_group = defaultdict(list)
    for spike in all_spikes:
        key = (spike["district_id"], spike["unit_id"], spike["crime_major_head_id"])
        spikes_by_group[key].append(spike)

    cases_by_group = defaultdict(list)
    for case in cases:
        key = (case.get("district_id"), case.get("unit_id"), case.get("crime_major_head_id"))
        cases_by_group[key].append(case)

    recent_totals_by_group = {}
    for group_key, weekly_data in weekly_series.items():
        recent_window = weekly_data[-RECENT_LOOKBACK_WEEKS:]
        recent_totals_by_group[group_key] = sum(item["count"] for item in recent_window)

    all_recent_totals = list(recent_totals_by_group.values())

    report = []

    for group_key, weekly_data in weekly_series.items():
        district_id, unit_id, crime_major_head_id = group_key

        group_cases = cases_by_group.get(group_key, [])
        case_count = len(group_cases)

        weekly_counts = [item["count"] for item in weekly_data]
        recent_weeks = [item["week"] for item in weekly_data[-RECENT_LOOKBACK_WEEKS:]]

        trend_metrics = compute_trend_metrics(weekly_counts)
        recent_trend_metrics = compute_recent_trend_metrics(weekly_counts)
        forecast = forecast_future_count(trend_metrics, weekly_counts, weeks_ahead)

        unresolved_ratio = compute_unresolved_ratio(group_cases, unresolved_status_ids)

        components = {
            "trend": compute_trend_score(trend_metrics),
            "recent_trend": compute_recent_trend_score(recent_trend_metrics),
            "volatility": compute_volatility_score(weekly_counts),
            "volume": compute_volume_score(recent_totals_by_group[group_key], all_recent_totals),
            "spike": compute_recent_spike_score(spikes_by_group.get(group_key, []), recent_weeks)
        }

        if unresolved_ratio is not None:
            components["unresolved"] = unresolved_ratio

        weights = get_effective_weights(unresolved_ratio)

        risk_score = round(sum(components[key] * weights[key] for key in components) * 100, 2)

        confidence = calculate_data_confidence(
            len(weekly_counts), trend_metrics["status"], recent_trend_metrics["status"]
        )

        recent_spikes = [s for s in spikes_by_group.get(group_key, []) if s["week"] in set(recent_weeks)]
        high_spikes = sum(1 for s in recent_spikes if s.get("severity") == "HIGH")
        medium_spikes = sum(1 for s in recent_spikes if s.get("severity") == "MEDIUM")

        report.append({
    "district_id": district_id,
    "unit_id": unit_id,
    "crime_major_head_id": crime_major_head_id,
    "case_count": case_count,
    "data_status": trend_metrics["status"],

    # Final risk result
    "risk_score": risk_score,
    "risk_level": classify_risk_level(risk_score),

    # Data reliability
    "confidence_level": confidence["level"],
    "confidence_score": confidence["score"],

    # Factors contributing to the risk
    "risk_factors": {
        k: round(v, 3)
        for k, v in components.items()
    },

    # Trend information
    "trend_slope": round(
        trend_metrics.get("slope", 0.0), 3
    ),
    "trend_r_value": round(
        trend_metrics.get("r_value", 0.0), 3
    ),
    "trend_p_value": round(
        trend_metrics.get("p_value", 1.0), 6
    ),
    "trend_significant": trend_metrics.get(
        "significant", False
    ),

    # Recent trend information
    "recent_trend_slope": round(
        recent_trend_metrics.get("slope", 0.0), 3
    ),
    "recent_trend_r_value": round(
        recent_trend_metrics.get("r_value", 0.0), 3
    ),
    "recent_trend_significant": recent_trend_metrics.get(
        "significant", False
    ),

    # Crime volume
    "recent_case_total": recent_totals_by_group[group_key],

    # Crime spikes
    "high_spikes_recent": high_spikes,
    "medium_spikes_recent": medium_spikes,
    "total_recent_spikes": len(recent_spikes),

    # Forecast
    "forecast_next_period_count": forecast
})

    return sorted(report, key=lambda row: -row["risk_score"])


# if __name__ == "__main__":
#     import json
#     import random

#     random.seed(7)
#     cases = []
#     case_id = 1

#     # Station 101, District 1, Crime 1: clearly increasing over 20 weeks
#     for week in range(20):
#         count = 2 + week // 2 + random.randint(0, 1)
#         for _ in range(count):
#             day_offset = week * 7 + random.randint(0, 6)
#             date = f"2026-{1 + day_offset // 30:02d}-{1 + day_offset % 28:02d}"
#             cases.append({
#                 "case_id": case_id, "district_id": 1, "unit_id": 101, "crime_major_head_id": 1,
#                 "crime_registered_date": date, "case_status_id": random.choice([1, 1, 2])
#             })
#             case_id += 1

#     # Station 102, same district, same crime type: flat/low volume
#     for week in range(20):
#         for _ in range(1):
#             day_offset = week * 7 + random.randint(0, 6)
#             date = f"2026-{1 + day_offset // 30:02d}-{1 + day_offset % 28:02d}"
#             cases.append({
#                 "case_id": case_id, "district_id": 1, "unit_id": 102, "crime_major_head_id": 1,
#                 "crime_registered_date": date, "case_status_id": random.choice([1, 2])
#             })
#             case_id += 1

#     # Station 103, different district, same crime type: high, mostly unresolved
#     for week in range(20):
#         for _ in range(3):
#             day_offset = week * 7 + random.randint(0, 6)
#             date = f"2026-{1 + day_offset // 30:02d}-{1 + day_offset % 28:02d}"
#             cases.append({
#                 "case_id": case_id, "district_id": 2, "unit_id": 103, "crime_major_head_id": 1,
#                 "crime_registered_date": date, "case_status_id": 2
#             })
#             case_id += 1

#     report = build_risk_report(cases, unresolved_status_ids={1}, weeks_ahead=4)
#     print(json.dumps(report, indent=2))