from bisect import bisect_left
from collections import Counter, defaultdict
from datetime import date, datetime
from math import radians, sin, cos, sqrt, atan2
from statistics import mean, stdev


# ============================================================
# CONFIGURATION
# ============================================================

MIN_HISTORICAL_CASES_FOR_BASELINE = 15

LOOKBACK_DAYS = 548

# These thresholds convert numerical anomaly scores
# into TRUE / FALSE.
#
# Score >= 0.60 means unusual.
TIME_ANOMALY_THRESHOLD = 0.60
LOCATION_ANOMALY_THRESHOLD = 0.60

DISTANCE_STDEV_FLOOR_KM = 0.5

LAPLACE_SMOOTHING = 1.0


# ============================================================
# BASIC HELPER FUNCTIONS
# ============================================================

def clip(value, low=0.0, high=1.0):
    return max(low, min(high, value))


def normalize(value, min_value, max_value):

    if max_value <= min_value:
        return 0.0

    return clip(
        (value - min_value)
        /
        (max_value - min_value)
    )


# ============================================================
# DATE PARSING
# ============================================================

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


# ============================================================
# TIME PARSING
# ============================================================

def parse_hour(case):

    # Option 1:
    # Direct hour field
    if case.get("hour") is not None:

        try:

            hour = int(
                case["hour"]
            )

            if 0 <= hour <= 23:
                return hour

            return None

        except (TypeError, ValueError):

            return None

    # Option 2:
    # Datetime or timestamp field
    timestamp = (
        case.get(
            "crime_registered_datetime"
        )
        or
        case.get(
            "crime_registered_timestamp"
        )
    )

    if timestamp:

        try:

            return datetime.fromisoformat(
                str(timestamp)
            ).hour

        except (ValueError, TypeError):

            return None

    return None


# ============================================================
# LOCATION VALIDATION
# ============================================================

def is_valid_coordinates(
    latitude,
    longitude
):

    if (
        latitude is None
        or
        longitude is None
    ):

        return False

    try:

        latitude = float(
            latitude
        )

        longitude = float(
            longitude
        )

    except (
        TypeError,
        ValueError
    ):

        return False

    if not (
        -90 <= latitude <= 90
    ):

        return False

    if not (
        -180 <= longitude <= 180
    ):

        return False

    return True


# ============================================================
# TIME OF DAY
# ============================================================

def get_time_of_day_bucket(hour):

    if hour is None:
        return None

    if 5 <= hour < 12:
        return "MORNING"

    if 12 <= hour < 17:
        return "AFTERNOON"

    if 17 <= hour < 21:
        return "EVENING"

    if 21 <= hour <= 23:
        return "NIGHT"

    if 0 <= hour < 5:
        return "NIGHT"

    return None


# ============================================================
# CASE VALIDATION
# ============================================================

def is_valid_case_record(case):

    if not isinstance(
        case,
        dict
    ):

        return False

    if case.get(
        "case_id"
    ) is None:

        return False

    if case.get(
        "district_id"
    ) is None:

        return False

    if case.get(
        "crime_major_head_id"
    ) is None:

        return False

    if parse_date(
        case.get(
            "crime_registered_date"
        )
    ) is None:

        return False

    return True


# ============================================================
# EXTRACT TIME FEATURES
# ============================================================

def extract_time_features(case):

    case_date = parse_date(
        case[
            "crime_registered_date"
        ]
    )

    hour = parse_hour(
        case
    )

    return {

        "date": case_date,

        "day_of_week":
            case_date.weekday(),

        "month":
            case_date.month,

        "hour":
            hour,

        "time_of_day":
            get_time_of_day_bucket(
                hour
            ),
    }


# ============================================================
# HAVERSINE DISTANCE
# ============================================================

def haversine_km(
    lat1,
    lon1,
    lat2,
    lon2
):

    R = 6371.0

    phi1 = radians(
        lat1
    )

    phi2 = radians(
        lat2
    )

    dphi = radians(
        lat2 - lat1
    )

    dlambda = radians(
        lon2 - lon1
    )

    a = (
        sin(
            dphi / 2
        ) ** 2
        +
        cos(phi1)
        *
        cos(phi2)
        *
        sin(
            dlambda / 2
        ) ** 2
    )

    a = clip(
        a,
        0.0,
        1.0
    )

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


# ============================================================
# BUILD CASE INDEX
# ============================================================

def build_case_index(cases):

    parsed = []

    seen_case_ids = set()

    for case in cases:

        if not is_valid_case_record(
            case
        ):

            continue

        case_id = case[
            "case_id"
        ]

        # Avoid duplicate case IDs
        if case_id in seen_case_ids:
            continue

        seen_case_ids.add(
            case_id
        )

        features = extract_time_features(
            case
        )

        latitude = case.get(
            "latitude"
        )

        longitude = case.get(
            "longitude"
        )

        if not is_valid_coordinates(
            latitude,
            longitude
        ):

            latitude = None
            longitude = None

        parsed.append({

            "case_id":
                case_id,

            "district_id":
                case[
                    "district_id"
                ],

            "crime_major_head_id":
                case[
                    "crime_major_head_id"
                ],

            "location_id":
                case.get(
                    "location_id"
                ),

            "latitude":
                latitude,

            "longitude":
                longitude,

            "date":
                features[
                    "date"
                ],

            "day_of_week":
                features[
                    "day_of_week"
                ],

            "time_of_day":
                features[
                    "time_of_day"
                ],
        })

    # Sort by date
    parsed.sort(
        key=lambda record: (
            record[
                "date"
            ],

            record[
                "case_id"
            ]
        )
    )

    # Group by district + crime
    group_index = defaultdict(
        list
    )

    for record in parsed:

        key = (
            record[
                "district_id"
            ],

            record[
                "crime_major_head_id"
            ]
        )

        group_index[
            key
        ].append(
            record
        )

    # Store dates separately
    group_dates = {

        key: [

            record[
                "date"
            ]

            for record in records

        ]

        for key, records

        in group_index.items()
    }

    return (
        dict(
            group_index
        ),

        group_dates
    )


# ============================================================
# GET HISTORICAL BASELINE
# ============================================================

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

    # Only cases BEFORE current case
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


# ============================================================
# FREQUENCY RARITY SCORE
# ============================================================

def frequency_rarity_score(
    value,
    counter,
    total,
    smoothing=LAPLACE_SMOOTHING
):

    if (
        total == 0
        or
        not counter
    ):

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


# ============================================================
# TIME ANOMALY SCORE
# ============================================================

def compute_temporal_anomaly(
    features,
    baseline
):

    if len(
        baseline
    ) < MIN_HISTORICAL_CASES_FOR_BASELINE:

        return None

    scores = []

    # --------------------------------------------------------
    # Day of week
    # --------------------------------------------------------

    day_counter = Counter(

        record[
            "day_of_week"
        ]

        for record

        in baseline

    )

    day_score = frequency_rarity_score(

        features[
            "day_of_week"
        ],

        day_counter,

        len(
            baseline
        )

    )

    if day_score is not None:

        scores.append(
            day_score
        )

    # --------------------------------------------------------
    # Time of day
    # --------------------------------------------------------

    if features[
        "time_of_day"
    ] is not None:

        time_counter = Counter(

            record[
                "time_of_day"
            ]

            for record

            in baseline

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

        sum(
            scores
        )
        /
        len(
            scores
        ),

        3

    )


# ============================================================
# LOCATION ANOMALY SCORE
# ============================================================

def compute_location_anomaly(
    case,
    baseline
):

    # --------------------------------------------------------
    # First check location_id
    # --------------------------------------------------------

    location_id = case.get(
        "location_id"
    )

    if location_id is not None:

        loc_counter = Counter(

            record[
                "location_id"
            ]

            for record

            in baseline

            if record.get(
                "location_id"
            ) is not None

        )

        total_with_location = sum(

            loc_counter.values()

        )

        if (
            total_with_location
            >=
            MIN_HISTORICAL_CASES_FOR_BASELINE
        ):

            score = (

                frequency_rarity_score(

                    location_id,

                    loc_counter,

                    total_with_location

                )

            )

            if score is not None:

                return round(
                    score,
                    3
                )

    # --------------------------------------------------------
    # If location_id unavailable,
    # use latitude/longitude
    # --------------------------------------------------------

    if not is_valid_coordinates(

        case.get(
            "latitude"
        ),

        case.get(
            "longitude"
        )

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

                    float(
                        latitude
                    ),

                    float(
                        longitude
                    )

                )

            )

    if (

        len(coords)

        <

        MIN_HISTORICAL_CASES_FOR_BASELINE

    ):

        return None

    # --------------------------------------------------------
    # Calculate geographic centroid
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # Distance of historical cases from centroid
    # --------------------------------------------------------

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

    if len(
        distances
    ) > 1:

        distance_spread = stdev(
            distances
        )

    else:

        distance_spread = 0.0

    distance_spread = max(

        distance_spread,

        DISTANCE_STDEV_FLOOR_KM

    )

    # --------------------------------------------------------
    # Distance of current case
    # --------------------------------------------------------

    case_distance = haversine_km(

        float(
            case[
                "latitude"
            ]
        ),

        float(
            case[
                "longitude"
            ]
        ),

        centroid_lat,

        centroid_lon

    )

    # --------------------------------------------------------
    # Calculate Z-score
    # --------------------------------------------------------

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


# ============================================================
# 4-WAY ANOMALY CLASSIFICATION
# ============================================================

def classify_location_time_anomaly(

    location_unusual,

    time_unusual

):

    # --------------------------------------------------------
    # FALSE + FALSE
    # --------------------------------------------------------

    if (

        not location_unusual

        and

        not time_unusual

    ):

        return {

            "location_unusual":
                False,

            "time_unusual":
                False,

            "anomaly_type":
                "NORMAL_PATTERN",

            "anomaly_level":
                "NORMAL",

            "reason":
                "Usual location and usual time"
        }

    # --------------------------------------------------------
    # TRUE + FALSE
    # --------------------------------------------------------

    elif (

        location_unusual

        and

        not time_unusual

    ):

        return {

            "location_unusual":
                True,

            "time_unusual":
                False,

            "anomaly_type":
                "LOCATION_ANOMALY",

            "anomaly_level":
                "MEDIUM",

            "reason":
                "Unusual location but usual time"
        }

    # --------------------------------------------------------
    # FALSE + TRUE
    # --------------------------------------------------------

    elif (

        not location_unusual

        and

        time_unusual

    ):

        return {

            "location_unusual":
                False,

            "time_unusual":
                True,

            "anomaly_type":
                "TIME_ANOMALY",

            "anomaly_level":
                "MEDIUM",

            "reason":
                "Usual location but unusual time"
        }

    # --------------------------------------------------------
    # TRUE + TRUE
    # --------------------------------------------------------

    else:

        return {

            "location_unusual":
                True,

            "time_unusual":
                True,

            "anomaly_type":
                "LOCATION_AND_TIME_ANOMALY",

            "anomaly_level":
                "HIGH",

            "reason":
                "Unusual location and unusual time"
        }


# ============================================================
# SCORE ONE CASE
# ============================================================

def score_case(

    case,

    group_index,

    group_dates

):

    # --------------------------------------------------------
    # Validate case
    # --------------------------------------------------------

    if not is_valid_case_record(
        case
    ):

        return {

            "case_id":
                case.get(
                    "case_id"
                ),

            "analysis_status":
                "INVALID_CASE",

            "location_unusual":
                None,

            "time_unusual":
                None,

            "anomaly_type":
                "INVALID_CASE",

            "anomaly_level":
                "UNKNOWN",

            "reason":
                (
                    "Missing required case information"
                )
        }

    # --------------------------------------------------------
    # Extract features
    # --------------------------------------------------------

    features = extract_time_features(
        case
    )

    key = (

        case[
            "district_id"
        ],

        case[
            "crime_major_head_id"
        ]

    )

    # --------------------------------------------------------
    # Get historical baseline
    # --------------------------------------------------------

    baseline = get_baseline_window(

        group_index,

        group_dates,

        key,

        features[
            "date"
        ]

    )

    base_fields = {

        "case_id":
            case[
                "case_id"
            ],

        "district_id":
            case[
                "district_id"
            ],

        "crime_major_head_id":
            case[
                "crime_major_head_id"
            ],

        "baseline_case_count":
            len(
                baseline
            )

    }

    # --------------------------------------------------------
    # Check minimum history
    # --------------------------------------------------------

    if (

        len(
            baseline
        )

        <

        MIN_HISTORICAL_CASES_FOR_BASELINE

    ):

        return {

            **base_fields,

            "analysis_status":
                "INSUFFICIENT_HISTORY",

            "location_unusual":
                None,

            "time_unusual":
                None,

            "anomaly_type":
                "INSUFFICIENT_HISTORY",

            "anomaly_level":
                "UNKNOWN",

            "reason":
                (
                    "Not enough historical data "
                    "to determine normal location "
                    "and time."
                )

        }

    # ========================================================
    # TIME ANALYSIS
    # ========================================================

    time_score = compute_temporal_anomaly(

        features,

        baseline

    )

    # ========================================================
    # LOCATION ANALYSIS
    # ========================================================

    location_score = compute_location_anomaly(

        case,

        baseline

    )

    # ========================================================
    # Convert scores to TRUE / FALSE
    # ========================================================

    if time_score is None:

        time_unusual = None

    else:

        time_unusual = (

            time_score
            >=
            TIME_ANOMALY_THRESHOLD

        )

    if location_score is None:

        location_unusual = None

    else:

        location_unusual = (

            location_score
            >=
            LOCATION_ANOMALY_THRESHOLD

        )

    # ========================================================
    # Missing data
    # ========================================================

    if (

        location_unusual is None

        or

        time_unusual is None

    ):

        return {

            **base_fields,

            "analysis_status":
                "PARTIAL_DATA",

            "location_unusual":
                location_unusual,

            "time_unusual":
                time_unusual,

            "location_score":
                location_score,

            "time_score":
                time_score,

            "anomaly_type":
                "UNDETERMINED",

            "anomaly_level":
                "UNKNOWN",

            "reason":
                (
                    "Insufficient location or time "
                    "information to classify the case."
                )

        }

    # ========================================================
    # FOUR-WAY CLASSIFICATION
    # ========================================================

    classification = (

        classify_location_time_anomaly(

            location_unusual,

            time_unusual

        )

    )

    # ========================================================
    # FINAL OUTPUT
    # ========================================================

    return {

        **base_fields,

        "analysis_status":
            "SUCCESS",

        "location_unusual":
            classification[
                "location_unusual"
            ],

        "time_unusual":
            classification[
                "time_unusual"
            ],

        "anomaly_type":
            classification[
                "anomaly_type"
            ],

        "anomaly_level":
            classification[
                "anomaly_level"
            ],

        "reason":
            classification[
                "reason"
            ],

        # Keep scores for transparency/debugging
        "location_score":
            location_score,

        "time_score":
            time_score

    }


# ============================================================
# BUILD SUMMARY
# ============================================================

def build_anomaly_summary(
    report
):

    summary = {

        "total_cases_analyzed":
            len(
                report
            ),

        "normal_cases":
            0,

        "location_anomalies":
            0,

        "time_anomalies":
            0,

        "location_and_time_anomalies":
            0,

        "insufficient_history":
            0,

        "partial_data":
            0,

        "invalid_cases":
            0

    }

    for result in report:

        status = result.get(
            "analysis_status"
        )

        if status == "INSUFFICIENT_HISTORY":

            summary[
                "insufficient_history"
            ] += 1

        elif status == "PARTIAL_DATA":

            summary[
                "partial_data"
            ] += 1

        elif status == "INVALID_CASE":

            summary[
                "invalid_cases"
            ] += 1

        elif status == "SUCCESS":

            anomaly_type = result.get(
                "anomaly_type"
            )

            if (

                anomaly_type
                ==
                "NORMAL_PATTERN"

            ):

                summary[
                    "normal_cases"
                ] += 1

            elif (

                anomaly_type
                ==
                "LOCATION_ANOMALY"

            ):

                summary[
                    "location_anomalies"
                ] += 1

            elif (

                anomaly_type
                ==
                "TIME_ANOMALY"

            ):

                summary[
                    "time_anomalies"
                ] += 1

            elif (

                anomaly_type
                ==
                "LOCATION_AND_TIME_ANOMALY"

            ):

                summary[
                    "location_and_time_anomalies"
                ] += 1

    return summary


# ============================================================
# BUILD COMPLETE ANOMALY REPORT
# ============================================================

def build_anomaly_report(

    cases,

    case_ids=None

):

    # --------------------------------------------------------
    # Build historical index
    # --------------------------------------------------------

    (
        group_index,

        group_dates

    ) = build_case_index(
        cases
    )

    # --------------------------------------------------------
    # Select cases
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # Analyze every case
    # --------------------------------------------------------

    report = [

        score_case(

            case,

            group_index,

            group_dates

        )

        for case

        in target_cases

    ]

    # --------------------------------------------------------
    # Sort:
    # HIGH first
    # MEDIUM next
    # NORMAL last
    # --------------------------------------------------------

    level_priority = {

        "HIGH":
            3,

        "MEDIUM":
            2,

        "NORMAL":
            1,

        "UNKNOWN":
            0

    }

    report.sort(

        key=lambda row:

        level_priority.get(

            row.get(
                "anomaly_level"
            ),

            0

        ),

        reverse=True

    )

    # --------------------------------------------------------
    # Build summary
    # --------------------------------------------------------

    summary = build_anomaly_summary(
        report
    )

    return {

        "summary":
            summary,

        "results":
            report

    }


# # ============================================================
# # TEST CODE
# # ============================================================

# if __name__ == "__main__":

#     import json

#     import random

#     random.seed(
#         7
#     )

#     cases = []

#     case_id = 1

#     # ========================================================
#     # Create historical cases
#     # ========================================================

#     # District 1
#     # Crime type 1
#     #
#     # Most historical cases:
#     # - Location ID = 101
#     # - Time = evening
#     #
#     # This gives us a normal baseline.
#     # ========================================================

#     for week in range(10):

#         for _ in range(3):

#             day_offset = (

#                 week * 7

#                 +

#                 random.randint(
#                     0,
#                     6
#                 )

#             )

#             current_date = (

#                 date(
#                     2026,
#                     1,
#                     1
#                 )

#                 +

#                 __import__(
#                     "datetime"
#                 ).timedelta(
#                     days=day_offset
#                 )

#             )

#             cases.append({

#                 "case_id":
#                     case_id,

#                 "district_id":
#                     1,

#                 "crime_major_head_id":
#                     1,

#                 "crime_registered_date":
#                     current_date.isoformat(),

#                 "hour":
#                     19,

#                 "location_id":
#                     101,

#                 "latitude":
#                     22.5726,

#                 "longitude":
#                     88.3639

#             })

#             case_id += 1


#     # ========================================================
#     # Add four test cases
#     # ========================================================

#     # --------------------------------------------------------
#     # Case 31
#     # Normal location + normal time
#     # Expected:
#     # False + False
#     # --------------------------------------------------------

#     cases.append({

#         "case_id":
#             31,

#         "district_id":
#             1,

#         "crime_major_head_id":
#             1,

#         "crime_registered_date":
#             "2026-04-01",

#         "hour":
#             19,

#         "location_id":
#             101,

#         "latitude":
#             22.5726,

#         "longitude":
#             88.3639

#     })


#     # --------------------------------------------------------
#     # Case 32
#     # Unusual location + normal time
#     # Expected:
#     # True + False
#     # --------------------------------------------------------

#     cases.append({

#         "case_id":
#             32,

#         "district_id":
#             1,

#         "crime_major_head_id":
#             1,

#         "crime_registered_date":
#             "2026-04-02",

#         "hour":
#             19,

#         "location_id":
#             999,

#         "latitude":
#             22.9000,

#         "longitude":
#             88.9000

#     })


#     # --------------------------------------------------------
#     # Case 33
#     # Normal location + unusual time
#     # Expected:
#     # False + True
#     # --------------------------------------------------------

#     cases.append({

#         "case_id":
#             33,

#         "district_id":
#             1,

#         "crime_major_head_id":
#             1,

#         "crime_registered_date":
#             "2026-04-03",

#         "hour":
#             3,

#         "location_id":
#             101,

#         "latitude":
#             22.5726,

#         "longitude":
#             88.3639

#     })


#     # --------------------------------------------------------
#     # Case 34
#     # Unusual location + unusual time
#     # Expected:
#     # True + True
#     # --------------------------------------------------------

#     cases.append({

#         "case_id":
#             34,

#         "district_id":
#             1,

#         "crime_major_head_id":
#             1,

#         "crime_registered_date":
#             "2026-04-04",

#         "hour":
#             3,

#         "location_id":
#             999,

#         "latitude":
#             22.9000,

#         "longitude":
#             88.9000

#     })


#     # ========================================================
#     # Generate report
#     # ========================================================

#     result = build_anomaly_report(
#         cases
#     )

#     print(
#         json.dumps(
#             result,
#             indent=4
#         )
#     )