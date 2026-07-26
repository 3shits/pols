from collections import defaultdict
from statistics import mean, stdev
from datetime import date


def get_mean(values):
    if not values:
        return 0.0
    return mean(values)


def get_stdev(values):
    if len(values) < 2:
        return 0.0
    return stdev(values)


def build_weekly_series(cases):
    """
    Groups cases by (district_id, unit_id, crime_major_head_id) and by ISO
    week, returning:
        {(district_id, unit_id, crime_head_id): [{"week": ..., "count": ...}, ...]}
    sorted chronologically.

    NOTE: group key now includes unit_id (police station) -- this is the
    change your real trend.py needs too, see the note at the end of the
    chat response.
    """
    grouped = defaultdict(lambda: defaultdict(int))

    for case in cases:
        district_id = case.get("district_id")
        unit_id = case.get("unit_id")
        crime_head_id = case.get("crime_major_head_id")
        date_str = case.get("crime_registered_date")
        if district_id is None or unit_id is None or crime_head_id is None or date_str is None:
            continue

        y, m, d = date_str.split("-")
        d_obj = date(int(y), min(int(m), 12), min(int(d), 28))
        iso_year, iso_week, _ = d_obj.isocalendar()
        week_key = f"{iso_year}-W{iso_week:02d}"

        key = (district_id, unit_id, crime_head_id)
        grouped[key][week_key] += 1

    result = {}
    for key, week_counts in grouped.items():
        weeks_sorted = sorted(week_counts.keys())
        result[key] = [{"week": w, "count": week_counts[w]} for w in weeks_sorted]

    return result


def find_rolling_spikes(cases, window=8, z_threshold=2.0):
    """
    Simple z-score based spike detector over each (district, unit, crime)
    group's weekly series. Each spike now carries unit_id so risk.py can
    match spikes back to the right police-station group.
    """
    weekly_series = build_weekly_series(cases)
    spikes = []

    for (district_id, unit_id, crime_head_id), weekly_data in weekly_series.items():
        counts = [item["count"] for item in weekly_data]

        for i in range(len(counts)):
            window_slice = counts[max(0, i - window):i]
            if len(window_slice) < 3:
                continue

            m = get_mean(window_slice)
            s = get_stdev(window_slice)
            if s == 0:
                continue

            z = (counts[i] - m) / s

            if z >= z_threshold * 1.5:
                severity = "HIGH"
            elif z >= z_threshold:
                severity = "MEDIUM"
            else:
                severity = "NORMAL"

            if severity != "NORMAL":
                spikes.append({
                    "district_id": district_id,
                    "unit_id": unit_id,
                    "crime_major_head_id": crime_head_id,
                    "week": weekly_data[i]["week"],
                    "z_score": round(z, 2),
                    "severity": severity,
                })

    return spikes