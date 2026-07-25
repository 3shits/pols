
from bisect import bisect_left
from collections import Counter, defaultdict
from datetime import date, datetime
import json
from math import radians, sin, cos, sqrt, atan2
from statistics import mean, stdev

MIN_HISTORICAL_CASES_FOR_BASELINE = 1
LOOKBACK_DAYS = 548
DISTANCE_STDEV_FLOOR_KM = 0.5
LAPLACE_SMOOTHING = 1.0

ANOMALY_WEIGHTS = {
    "temporal": 0.25,
    "spatial": 0.25,
    "pattern": 0.30,
    "location": 0.20,
}

ANOMALY_THRESHOLDS = [
    (0.80, "HIGHLY_ANOMALOUS"),
    (0.60, "SUSPICIOUS"),
    (0.30, "LOW"),
    (0.00, "NORMAL"),
]

REASON_TRIGGER_THRESHOLD = 0.6

TIME_OF_DAY_BUCKETS = [
    (5, 12, "MORNING"),
    (12, 17, "AFTERNOON"),
    (17, 21, "EVENING"),
    (21, 24, "NIGHT"),
    (0, 5, "NIGHT"),
]


def clip(value, low=0.0, high=1.0):
    return max(low, min(high, value))


def normalize(value, min_value, max_value):
    if max_value <= min_value:
        return 0.0

    return clip(
        (value - min_value) /
        (max_value - min_value)
    )


def parse_date(date_str):
    if not date_str:
        return None

    try:
        return datetime.strptime(
            str(date_str)[:10],
            "%Y-%m-%d"
        ).date()
    except (ValueError, TypeError):
        return None


def parse_hour(case):
    if case.get("hour") is not None:
        try:
            hour = int(case["hour"])

            if 0 <= hour <= 23:
                return hour

            return None

        except (TypeError, ValueError):
            return None

    timestamp = (
        case.get("crime_registered_datetime")
        or case.get("crime_registered_timestamp")
    )

    if timestamp:
        try:
            return datetime.fromisoformat(
                str(timestamp)
            ).hour

        except (ValueError, TypeError):
            return None

    return None


def is_valid_coordinates(latitude, longitude):
    if latitude is None or longitude is None:
        return False

    try:
        latitude = float(latitude)
        longitude = float(longitude)
    except (TypeError, ValueError):
        return False

    if not -90 <= latitude <= 90:
        return False

    if not -180 <= longitude <= 180:
        return False

    return True


def get_time_of_day_bucket(hour):
    if hour is None:
        return None

    for start, end, bucket in TIME_OF_DAY_BUCKETS:
        if start <= hour < end:
            return bucket

    return None


def is_valid_case_record(case):
    if not isinstance(case, dict):
        return False

    if case.get("case_id") is None:
        return False

    if case.get("district_id") is None:
        return False

    if case.get("crime_major_head_id") is None:
        return False

    if parse_date(
        case.get("crime_registered_date")
    ) is None:
        return False

    return True


def extract_time_features(case):
    case_date = parse_date(
        case["crime_registered_date"]
    )

    hour = parse_hour(case)

    return {
        "date": case_date,
        "day_of_week": case_date.weekday(),
        "month": case_date.month,
        "hour": hour,
        "time_of_day": get_time_of_day_bucket(hour),
    }


def haversine_km(
    lat1,
    lon1,
    lat2,
    lon2
):
    R = 6371.0

    phi1 = radians(lat1)
    phi2 = radians(lat2)

    dphi = radians(
        lat2 - lat1
    )

    dlambda = radians(
        lon2 - lon1
    )

    a = (
        sin(dphi / 2) ** 2
        +
        cos(phi1)
        *
        cos(phi2)
        *
        sin(dlambda / 2) ** 2
    )

    a = clip(a, 0.0, 1.0)

    return (
        2
        *
        R
        *
        atan2(
            sqrt(a),
            sqrt(1 - a)
        )
    )


def build_case_index(cases):

    parsed = []

    seen_case_ids = set()

    for case in cases:

        if not is_valid_case_record(case):
            continue

        case_id = case["case_id"]

        if case_id in seen_case_ids:
            continue

        seen_case_ids.add(case_id)

        features = extract_time_features(case)

        latitude = case.get("latitude")
        longitude = case.get("longitude")

        if not is_valid_coordinates(
            latitude,
            longitude
        ):
            latitude = None
            longitude = None

        parsed.append({
            "case_id": case_id,
            "district_id": case["district_id"],
            "crime_major_head_id": case[
                "crime_major_head_id"
            ],
            "location_id": case.get(
                "location_id"
            ),
            "latitude": latitude,
            "longitude": longitude,
            "date": features["date"],
            "day_of_week": features[
                "day_of_week"
            ],
            "time_of_day": features[
                "time_of_day"
            ],
        })

    parsed.sort(
        key=lambda record: (
            record["date"],
            record["case_id"]
        )
    )

    group_index = defaultdict(list)

    for record in parsed:

        key = (
            record["district_id"],
            record[
                "crime_major_head_id"
            ]
        )

        group_index[key].append(
            record
        )

    group_dates = {
        key: [
            record["date"]
            for record in records
        ]
        for key, records
        in group_index.items()
    }

    return (
        dict(group_index),
        group_dates
    )


def get_baseline_window(
    group_index,
    group_dates,
    key,
    as_of_date,
    lookback_days=LOOKBACK_DAYS
):

    dates = group_dates.get(
        key
    )

    records = group_index.get(
        key
    )

    if not dates:
        return []

    end_index = bisect_left(
        dates,
        as_of_date
    )

    window_start = date.fromordinal(
        as_of_date.toordinal()
        -
        lookback_days
    )

    start_index = bisect_left(
        dates,
        window_start
    )

    return records[
        start_index:end_index
    ]


def frequency_rarity_score(
    value,
    counter,
    total,
    smoothing=LAPLACE_SMOOTHING
):

    if total == 0 or not counter:
        return None

    distinct_values = max(
        len(counter),
        1
    )

    denominator = (
        total
        +
        smoothing
        *
        distinct_values
    )

    count = counter.get(
        value,
        0
    )

    probability = (
        count
        +
        smoothing
    ) / denominator

    max_probability = max(
        (
            count_value
            +
            smoothing
        ) / denominator
        for count_value
        in counter.values()
    )

    if max_probability <= 0:
        return 0.0

    return clip(
        1
        -
        (
            probability
            /
            max_probability
        )
    )


def compute_temporal_anomaly(
    features,
    baseline
):

    if (
        len(baseline)
        <
        MIN_HISTORICAL_CASES_FOR_BASELINE
    ):
        return None

    day_counter = Counter(
        record["day_of_week"]
        for record in baseline
    )

    day_score = frequency_rarity_score(
        features["day_of_week"],
        day_counter,
        len(baseline)
    )

    scores = []

    if day_score is not None:
        scores.append(
            day_score
        )

    if features[
        "time_of_day"
    ] is not None:

        time_counter = Counter(
            record["time_of_day"]
            for record in baseline
            if record[
                "time_of_day"
            ] is not None
        )

        total_with_time = sum(
            time_counter.values()
        )

        if (
            total_with_time
            >=
            MIN_HISTORICAL_CASES_FOR_BASELINE
        ):

            time_score = (
                frequency_rarity_score(
                    features[
                        "time_of_day"
                    ],
                    time_counter,
                    total_with_time
                )
            )

            if time_score is not None:
                scores.append(
                    time_score
                )

    if not scores:
        return None

    return round(
        sum(scores)
        /
        len(scores),
        3
    )


def compute_location_anomaly(
    case,
    baseline
):

    location_id = case.get(
        "location_id"
    )

    if location_id is None:
        return None

    loc_counter = Counter(
        record["location_id"]
        for record in baseline
        if record.get(
            "location_id"
        ) is not None
    )

    total_with_location = sum(
        loc_counter.values()
    )

    if (
        total_with_location
        <
        MIN_HISTORICAL_CASES_FOR_BASELINE
    ):
        return None

    score = frequency_rarity_score(
        location_id,
        loc_counter,
        total_with_location
    )

    if score is None:
        return None

    return round(
        score,
        3
    )


def compute_spatial_anomaly(
    case,
    baseline
):

    if not is_valid_coordinates(
        case.get("latitude"),
        case.get("longitude")
    ):
        return None

    coords = []

    for record in baseline:

        latitude = record.get(
            "latitude"
        )

        longitude = record.get(
            "longitude"
        )

        if is_valid_coordinates(
            latitude,
            longitude
        ):
            coords.append(
                (
                    float(latitude),
                    float(longitude)
                )
            )

    if (
        len(coords)
        <
        MIN_HISTORICAL_CASES_FOR_BASELINE
    ):
        return None

    centroid_lat = mean(
        latitude
        for latitude, longitude
        in coords
    )

    centroid_lon = mean(
        longitude
        for latitude, longitude
        in coords
    )

    distances = [
        haversine_km(
            latitude,
            longitude,
            centroid_lat,
            centroid_lon
        )
        for latitude, longitude
        in coords
    ]

    mean_distance = mean(
        distances
    )

    if len(distances) > 1:
        distance_spread = stdev(
            distances
        )
    else:
        distance_spread = 0.0

    distance_spread = max(
        distance_spread,
        DISTANCE_STDEV_FLOOR_KM
    )

    case_distance = haversine_km(
        float(case["latitude"]),
        float(case["longitude"]),
        centroid_lat,
        centroid_lon
    )

    z_score = max(
        (
            case_distance
            -
            mean_distance
        )
        /
        distance_spread,
        0.0
    )

    return round(
        normalize(
            z_score,
            0,
            3.0
        ),
        3
    )


def compute_pattern_anomaly(
    features,
    case,
    baseline
):

    if (
        len(baseline)
        <
        MIN_HISTORICAL_CASES_FOR_BASELINE
    ):
        return None

    day_time_counter = Counter(
        (
            record["day_of_week"],
            record["time_of_day"]
        )
        for record in baseline
    )

    day_time_key = (
        features["day_of_week"],
        features["time_of_day"]
    )

    day_time_score = (
        frequency_rarity_score(
            day_time_key,
            day_time_counter,
            len(baseline)
        )
    )

    scores = []

    if day_time_score is not None:
        scores.append(
            day_time_score
        )

    location_id = case.get(
        "location_id"
    )

    if location_id is not None:

        loc_time_counter = Counter(
            (
                record["location_id"],
                record["time_of_day"]
            )
            for record in baseline
            if record.get(
                "location_id"
            ) is not None
        )

        total_with_location = sum(
            loc_time_counter.values()
        )

        if (
            total_with_location
            >=
            MIN_HISTORICAL_CASES_FOR_BASELINE
        ):

            loc_time_key = (
                location_id,
                features[
                    "time_of_day"
                ]
            )

            loc_time_score = (
                frequency_rarity_score(
                    loc_time_key,
                    loc_time_counter,
                    total_with_location
                )
            )

            if loc_time_score is not None:
                scores.append(
                    loc_time_score
                )

    if not scores:
        return None

    return round(
        sum(scores)
        /
        len(scores),
        3
    )


def get_effective_weights(
    available_keys
):

    available_keys = set(
        available_keys
    )

    weights = {
        key: ANOMALY_WEIGHTS[key]
        for key in available_keys
        if key in ANOMALY_WEIGHTS
    }

    missing_keys = [
        key
        for key in ANOMALY_WEIGHTS
        if key not in available_keys
    ]

    if not missing_keys:
        return weights

    missing_weight_total = sum(
        ANOMALY_WEIGHTS[key]
        for key in missing_keys
    )

    present_weight_total = sum(
        weights.values()
    )

    if present_weight_total > 0:

        for key in weights:

            weights[key] += (
                missing_weight_total
                *
                (
                    weights[key]
                    /
                    present_weight_total
                )
            )

    return weights


def classify_anomaly(
    score
):

    for threshold, label in ANOMALY_THRESHOLDS:

        if score >= threshold:
            return label

    return "NORMAL"


REASON_TEXT = {
    "temporal": (
        "Crime occurred at a day/time that is uncommon "
        "for this crime type in this district"
    ),
    "spatial": (
        "Crime location is geographically farther than usual "
        "from where this crime type typically occurs"
    ),
    "location": (
        "This specific location has a historically low frequency "
        "of this crime type"
    ),
    "pattern": (
        "The combination of day, time, and location is "
        "historically rare for this crime type"
    ),
}


def generate_reasons(
    components,
    anomaly_level
):

    if anomaly_level == "NORMAL":
        return []

    reasons = [
        REASON_TEXT[key]
        for key, score
        in components.items()
        if score is not None
        and score >= REASON_TRIGGER_THRESHOLD
    ]

    if not reasons:

        reasons.append(
            "No single factor was strongly unusual on its own, "
            "but the combined score across all available factors "
            "crossed the alert threshold"
        )

    return reasons


def score_case(
    case,
    group_index,
    group_dates
):

    if not is_valid_case_record(
        case
    ):

        return {
            "case_id": case.get(
                "case_id"
            ),
            "analysis_status": "INVALID_CASE",
            "message": (
                "Missing case_id, district_id, "
                "crime_major_head_id, or a valid "
                "crime_registered_date."
            ),
        }

    features = extract_time_features(
        case
    )

    key = (
        case["district_id"],
        case[
            "crime_major_head_id"
        ]
    )

    baseline = get_baseline_window(
        group_index,
        group_dates,
        key,
        features["date"]
    )

    base_fields = {
        "case_id": case[
            "case_id"
        ],
        "district_id": case[
            "district_id"
        ],
        "crime_major_head_id": case[
            "crime_major_head_id"
        ],
        "baseline_case_count": len(
            baseline
        ),
    }

    if (
        len(baseline)
        <
        MIN_HISTORICAL_CASES_FOR_BASELINE
    ):

        return {
            **base_fields,
            "analysis_status": (
                "INSUFFICIENT_HISTORY"
            ),
            "message": (
                f"Fewer than "
                f"{MIN_HISTORICAL_CASES_FOR_BASELINE} "
                "historical cases were available "
                "for this district/crime combination "
                "as of this case's date."
            ),
        }

    components = {
        "temporal": (
            compute_temporal_anomaly(
                features,
                baseline
            )
        ),
        "spatial": (
            compute_spatial_anomaly(
                case,
                baseline
            )
        ),
        "location": (
            compute_location_anomaly(
                case,
                baseline
            )
        ),
        "pattern": (
            compute_pattern_anomaly(
                features,
                case,
                baseline
            )
        ),
    }

    available = {
        key: value
        for key, value
        in components.items()
        if value is not None
    }

    if not available:

        return {
            **base_fields,
            "analysis_status": (
                "NO_SIGNAL"
            ),
            "message": (
                "No component had enough supporting "
                "data to calculate an anomaly score."
            ),
        }

    weights = get_effective_weights(
        available.keys()
    )

    anomaly_score = round(
        sum(
            available[key]
            *
            weights[key]
            for key in available
        ),
        3
    )

    anomaly_level = classify_anomaly(
        anomaly_score
    )

    reasons = generate_reasons(
        available,
        anomaly_level
    )

    return {
        **base_fields,
        "anomaly_score": anomaly_score,
        "anomaly_level": anomaly_level,
        "components": {
            key: round(
                value,
                3
            )
            for key, value
            in available.items()
        },
        "weights_used": {
            key: round(
                value,
                3
            )
            for key, value
            in weights.items()
        },
        "reasons": reasons,
        "analysis_status": "SUCCESS",
    }


def build_anomaly_summary(
    report
):

    summary = {
        "total_cases_analyzed": len(
            report
        ),
        "normal_cases": 0,
        "low_anomalies": 0,
        "suspicious_cases": 0,
        "highly_anomalous_cases": 0,
        "insufficient_history": 0,
        "invalid_cases": 0,
        "no_signal": 0,
    }

    for result in report:

        status = result.get(
            "analysis_status"
        )

        if status == "INSUFFICIENT_HISTORY":
            summary[
                "insufficient_history"
            ] += 1

        elif status == "INVALID_CASE":
            summary[
                "invalid_cases"
            ] += 1

        elif status == "NO_SIGNAL":
            summary[
                "no_signal"
            ] += 1

        elif status == "SUCCESS":

            level = result.get(
                "anomaly_level"
            )

            if level == "NORMAL":
                summary[
                    "normal_cases"
                ] += 1

            elif level == "LOW":
                summary[
                    "low_anomalies"
                ] += 1

            elif level == "SUSPICIOUS":
                summary[
                    "suspicious_cases"
                ] += 1

            elif level == "HIGHLY_ANOMALOUS":
                summary[
                    "highly_anomalous_cases"
                ] += 1

    return summary


def build_anomaly_report(
    cases,
    case_ids=None
):

    group_index, group_dates = (
        build_case_index(
            cases
        )
    )

    if case_ids is not None:

        case_id_set = set(
            case_ids
        )

        target_cases = [
            case
            for case in cases
            if case.get(
                "case_id"
            )
            in case_id_set
        ]

    else:

        target_cases = cases

    report = [
        score_case(
            case,
            group_index,
            group_dates
        )
        for case in target_cases
    ]

    report.sort(
        key=lambda row: -(
            row.get(
                "anomaly_score"
            )
            if row.get(
                "anomaly_score"
            )
            is not None
            else -1
        )
    )

    summary = build_anomaly_summary(
        report
    )

    return {
        "summary": summary,
        "results": report
    }

sample_cases = [
    {
        "case_id": 1,
        "district_id": 1,
        "crime_major_head_id": 1,
        "crime_registered_date": "2026-01-10",
        "latitude": 12.9716,
        "longitude": 77.5946,
        "case_status_id": 1
    },
    {
        "case_id": 2,
        "district_id": 1,
        "crime_major_head_id": 1,
        "crime_registered_date": "2026-01-15",
        "latitude": 12.9750,
        "longitude": 77.6000,
        "case_status_id": 2
    },
    {
        "case_id": 3,
        "district_id": 1,
        "crime_major_head_id": 2,
        "crime_registered_date": "2026-01-20",
        "latitude": 12.9800,
        "longitude": 77.6100,
        "case_status_id": 1
    },
    {
        "case_id": 4,
        "district_id": 2,
        "crime_major_head_id": 1,
        "crime_registered_date": "2026-02-05",
        "latitude": 15.3173,
        "longitude": 75.7139,
        "case_status_id": 2
    },
    {
        "case_id": 5,
        "district_id": 2,
        "crime_major_head_id": 2,
        "crime_registered_date": "2026-02-10",
        "latitude": 15.3200,
        "longitude": 75.7200,
        "case_status_id": 1
    },
    {
        "case_id": 6,
        "district_id": 2,
        "crime_major_head_id": 1,
        "crime_registered_date": "2026-02-18",
        "latitude": 15.3250,
        "longitude": 75.7250,
        "case_status_id": 2
    },
    {
        "case_id": 7,
        "district_id": 3,
        "crime_major_head_id": 1,
        "crime_registered_date": "2026-03-01",
        "latitude": 12.2958,
        "longitude": 76.6394,
        "case_status_id": 1
    },
    {
        "case_id": 8,
        "district_id": 3,
        "crime_major_head_id": 3,
        "crime_registered_date": "2026-03-05",
        "latitude": 12.3000,
        "longitude": 76.6450,
        "case_status_id": 2
    },
    {
        "case_id": 9,
        "district_id": 3,
        "crime_major_head_id": 1,
        "crime_registered_date": "2026-03-12",
        "latitude": 12.3050,
        "longitude": 76.6500,
        "case_status_id": 1
    },
    {
        "case_id": 10,
        "district_id": 4,
        "crime_major_head_id": 2,
        "crime_registered_date": "2026-03-20",
        "latitude": 13.3409,
        "longitude": 74.7421,
        "case_status_id": 1
    },
    {
        "case_id": 11,
        "district_id": 4,
        "crime_major_head_id": 2,
        "crime_registered_date": "2026-03-25",
        "latitude": 13.3450,
        "longitude": 74.7500,
        "case_status_id": 2
    },
    {
        "case_id": 12,
        "district_id": 5,
        "crime_major_head_id": 3,
        "crime_registered_date": "2026-04-02",
        "latitude": 14.4673,
        "longitude": 75.9218,
        "case_status_id": 1
    },
    {
        "case_id": 13,
        "district_id": 5,
        "crime_major_head_id": 3,
        "crime_registered_date": "2026-04-08",
        "latitude": 14.4700,
        "longitude": 75.9250,
        "case_status_id": 2
    },
    {
        "case_id": 14,
        "district_id": 1,
        "crime_major_head_id": 1,
        "crime_registered_date": "2026-04-15",
        "latitude": 12.9716,
        "longitude": 77.5946,
        "case_status_id": 1
    },
    {
        "case_id": 15,
        "district_id": 1,
        "crime_major_head_id": 1,
        "crime_registered_date": "2026-04-20",
        "latitude": 12.9750,
        "longitude": 77.6000,
        "case_status_id": 1
    }
]
result = build_anomaly_report(sample_cases)

print(json.dumps(result, indent=4))