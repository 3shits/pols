from collections import defaultdict, Counter
from math import radians

import numpy as np
from sklearn.cluster import DBSCAN

from anomaly import (
    parse_date,
    parse_hour,
    get_time_of_day_bucket,
    is_valid_coordinates,
    haversine_km,
)


# ============================================================
# CONFIGURATION
# ============================================================

EARTH_RADIUS_KM = 6371.0

# Maximum geographic distance between points in the same cluster
DEFAULT_EPS_KM = 1.0

# Minimum number of nearby cases required to form a cluster
DEFAULT_MIN_SAMPLES = 5

# Minimum number of cases in a district/crime group
# before DBSCAN is attempted
MIN_CASES_FOR_CLUSTERING = 5

TIME_BUCKETS = [
    "MORNING",
    "AFTERNOON",
    "EVENING",
    "NIGHT",
]


# ============================================================
# BASIC VALIDATION
# ============================================================

def is_valid_hotspot_case(case):
    """
    Checks whether a case contains enough information
    for hotspot detection.
    """

    if not isinstance(case, dict):
        return False

    if case.get("case_id") is None:
        return False

    if case.get("district_id") is None:
        return False

    if case.get("crime_major_head_id") is None:
        return False

    if not is_valid_coordinates(
        case.get("latitude"),
        case.get("longitude")
    ):
        return False

    return True


def filter_valid_cases(cases):
    """
    Keeps only cases that can be used for hotspot detection.
    """

    return [
        case
        for case in cases
        if is_valid_hotspot_case(case)
    ]


# ============================================================
# COORDINATE PREPARATION
# ============================================================

def build_radian_coordinates(cases):
    """
    DBSCAN with haversine distance requires
    latitude and longitude in radians.
    """

    return np.array([
        [
            radians(float(case["latitude"])),
            radians(float(case["longitude"]))
        ]
        for case in cases
    ])


# ============================================================
# DBSCAN CLUSTERING
# ============================================================

def run_dbscan(
    cases,
    eps_km=DEFAULT_EPS_KM,
    min_samples=DEFAULT_MIN_SAMPLES
):
    """
    Runs DBSCAN on geographical coordinates.

    Returns:
        List of cluster labels.

    Example:
        0, 0, 0, 1, 1, -1

    Meaning:
        Cluster 0
        Cluster 0
        Cluster 0
        Cluster 1
        Cluster 1
        Noise

    -1 means the case does not belong to a hotspot.
    """

    if len(cases) < min_samples:
        return [-1] * len(cases)

    coordinates = build_radian_coordinates(
        cases
    )

    eps_radians = (
        eps_km
        /
        EARTH_RADIUS_KM
    )

    model = DBSCAN(
        eps=eps_radians,
        min_samples=min_samples,
        metric="haversine",
        algorithm="ball_tree"
    )

    labels = model.fit_predict(
        coordinates
    )

    return [
        int(label)
        for label in labels
    ]


# ============================================================
# LOCATION CALCULATIONS
# ============================================================

def compute_centroid(cluster_cases):
    """
    Calculates the approximate center of a hotspot.
    """

    latitudes = [
        float(case["latitude"])
        for case in cluster_cases
    ]

    longitudes = [
        float(case["longitude"])
        for case in cluster_cases
    ]

    center_latitude = (
        sum(latitudes)
        /
        len(latitudes)
    )

    center_longitude = (
        sum(longitudes)
        /
        len(longitudes)
    )

    return (
        center_latitude,
        center_longitude
    )


def compute_radius_km(
    cluster_cases,
    centroid
):
    """
    Calculates the maximum distance between
    the hotspot center and any case in the cluster.
    """

    center_latitude, center_longitude = centroid

    distances = []

    for case in cluster_cases:

        distance = haversine_km(
            float(case["latitude"]),
            float(case["longitude"]),
            center_latitude,
            center_longitude
        )

        distances.append(
            distance
        )

    if not distances:
        return 0.0

    return round(
        max(distances),
        3
    )


# ============================================================
# TIME ANALYSIS
# ============================================================

def get_time_pattern(cluster_cases):
    """
    Finds the most common time-of-day for crimes
    inside the hotspot.

    Returns:
        MORNING
        AFTERNOON
        EVENING
        NIGHT
        UNKNOWN
    """

    time_counter = Counter()

    for case in cluster_cases:

        hour = parse_hour(
            case
        )

        time_bucket = get_time_of_day_bucket(
            hour
        )

        if time_bucket is not None:

            time_counter[
                time_bucket
            ] += 1

    if not time_counter:
        return "UNKNOWN"

    return time_counter.most_common(
        1
    )[0][0]


def get_time_of_day_breakdown(
    cluster_cases
):
    """
    Returns the number of crimes occurring
    in each time-of-day bucket.
    """

    time_counter = Counter()

    for case in cluster_cases:

        hour = parse_hour(
            case
        )

        time_bucket = get_time_of_day_bucket(
            hour
        )

        if time_bucket is not None:

            time_counter[
                time_bucket
            ] += 1

    return dict(
        time_counter
    )


# ============================================================
# DATE ANALYSIS
# ============================================================

def get_date_range(
    cluster_cases
):
    """
    Finds the earliest and latest crime dates
    in a hotspot.
    """

    dates = []

    for case in cluster_cases:

        case_date = parse_date(
            case.get(
                "crime_registered_date"
            )
        )

        if case_date is not None:

            dates.append(
                case_date
            )

    if not dates:

        return {
            "earliest": None,
            "latest": None
        }

    return {
        "earliest": min(
            dates
        ).isoformat(),

        "latest": max(
            dates
        ).isoformat()
    }


# ============================================================
# HOTSPOT INTENSITY
# ============================================================

def classify_hotspot_intensity(
    case_count,
    all_cluster_sizes
):
    """
    Classifies hotspot intensity relative to
    other detected hotspots.

    CRITICAL:
        >= 75% of largest hotspot

    HIGH:
        >= 50% of largest hotspot

    MEDIUM:
        >= 25% of largest hotspot

    LOW:
        < 25% of largest hotspot
    """

    if not all_cluster_sizes:

        return "LOW"

    max_size = max(
        all_cluster_sizes
    )

    if max_size <= 0:

        return "LOW"

    ratio = (
        case_count
        /
        max_size
    )

    if ratio >= 0.75:

        return "CRITICAL"

    if ratio >= 0.50:

        return "HIGH"

    if ratio >= 0.25:

        return "MEDIUM"

    return "LOW"


# ============================================================
# HOTSPOT REASON
# ============================================================

def generate_hotspot_reason(
    case_count,
    time_pattern
):
    """
    Generates a short explanation for the hotspot.
    """

    if time_pattern == "UNKNOWN":

        return "HIGH CRIME CONCENTRATION"

    return (
        f"HIGH CRIME CONCENTRATION - "
        f"{time_pattern}"
    )


# ============================================================
# CREATE HOTSPOT RECORD
# ============================================================

def summarize_cluster(
    hotspot_id,
    cluster_cases,
    district_id,
    crime_major_head_id,
    time_bucket=None
):
    """
    Converts a DBSCAN cluster into a clean
    hotspot output record.
    """

    centroid = compute_centroid(
        cluster_cases
    )

    center_latitude = centroid[0]
    center_longitude = centroid[1]

    radius_km = compute_radius_km(
        cluster_cases,
        centroid
    )

    crime_counter = Counter(
        case[
            "crime_major_head_id"
        ]
        for case in cluster_cases
    )

    time_pattern = get_time_pattern(
        cluster_cases
    )

    date_range = get_date_range(
        cluster_cases
    )

    return {
        "hotspot_id": hotspot_id,

        "district_id": district_id,

        "crime_major_head_id":
            crime_major_head_id,

        "case_count":
            len(cluster_cases),

        "center_latitude":
            round(
                center_latitude,
                5
            ),

        "center_longitude":
            round(
                center_longitude,
                5
            ),

        "radius_km":
            radius_km,

        "dominant_crime_type":
            crime_counter.most_common(
                1
            )[0][0]
            if crime_counter
            else None,

        "time_pattern":
            time_pattern,

        "time_bucket_filter":
            time_bucket,

        "time_of_day_breakdown":
            get_time_of_day_breakdown(
                cluster_cases
            ),

        "hotspot_reason":
            generate_hotspot_reason(
                len(cluster_cases),
                time_pattern
            ),

        "date_range":
            date_range,

        "case_ids": [
            case["case_id"]
            for case in cluster_cases
        ]
    }


# ============================================================
# GROUP CASES
# ============================================================

def group_cases_by_district_and_crime(
    cases
):
    """
    Groups cases by:

        district_id
        crime_major_head_id

    This prevents cases from unrelated districts
    being clustered together.
    """

    groups = defaultdict(list)

    for case in cases:

        key = (
            case["district_id"],
            case["crime_major_head_id"]
        )

        groups[key].append(
            case
        )

    return groups


# ============================================================
# SPATIAL HOTSPOTS
# ============================================================

def find_hotspots(
    cases,
    eps_km=DEFAULT_EPS_KM,
    min_samples=DEFAULT_MIN_SAMPLES
):
    """
    Finds geographical crime hotspots.

    Cases are grouped by:

        District
        +
        Crime Type

    DBSCAN is then applied to each group.
    """

    valid_cases = filter_valid_cases(
        cases
    )

    grouped_cases = (
        group_cases_by_district_and_crime(
            valid_cases
        )
    )

    hotspots = []

    hotspot_id = 1

    for (
        district_id,
        crime_id
    ), group_cases in grouped_cases.items():

        if len(
            group_cases
        ) < MIN_CASES_FOR_CLUSTERING:

            continue

        labels = run_dbscan(
            group_cases,
            eps_km=eps_km,
            min_samples=min_samples
        )

        clusters = defaultdict(list)

        for case, label in zip(
            group_cases,
            labels
        ):

            if label == -1:

                continue

            clusters[
                label
            ].append(
                case
            )

        for cluster_cases in clusters.values():

            hotspot = summarize_cluster(
                hotspot_id,
                cluster_cases,
                district_id,
                crime_id
            )

            hotspots.append(
                hotspot
            )

            hotspot_id += 1

    # --------------------------------------------------------
    # Classify intensity
    # --------------------------------------------------------

    cluster_sizes = [
        hotspot["case_count"]
        for hotspot in hotspots
    ]

    for hotspot in hotspots:

        hotspot[
            "intensity"
        ] = classify_hotspot_intensity(
            hotspot["case_count"],
            cluster_sizes
        )

    return sorted(
        hotspots,
        key=lambda x: -x[
            "case_count"
        ]
    )


# ============================================================
# SPATIOTEMPORAL HOTSPOTS
# ============================================================

def find_spatiotemporal_hotspots(
    cases,
    eps_km=DEFAULT_EPS_KM,
    min_samples=DEFAULT_MIN_SAMPLES
):
    """
    Finds hotspots using:

        District
        +
        Crime Type
        +
        Time of Day

    Example:

        District 1
        Crime Type 1
        EVENING

    This answers:

        "Where does this crime repeatedly
         happen during a particular time?"
    """

    valid_cases = filter_valid_cases(
        cases
    )

    grouped_cases = defaultdict(list)

    for case in valid_cases:

        hour = parse_hour(
            case
        )

        time_bucket = (
            get_time_of_day_bucket(
                hour
            )
        )

        if time_bucket is None:

            continue

        key = (
            case["district_id"],
            case["crime_major_head_id"],
            time_bucket
        )

        grouped_cases[
            key
        ].append(
            case
        )

    hotspots = []

    hotspot_id = 1

    for (
        district_id,
        crime_id,
        time_bucket
    ), group_cases in grouped_cases.items():

        if len(
            group_cases
        ) < MIN_CASES_FOR_CLUSTERING:

            continue

        labels = run_dbscan(
            group_cases,
            eps_km=eps_km,
            min_samples=min_samples
        )

        clusters = defaultdict(list)

        for case, label in zip(
            group_cases,
            labels
        ):

            if label == -1:

                continue

            clusters[
                label
            ].append(
                case
            )

        for cluster_cases in clusters.values():

            hotspot = summarize_cluster(
                hotspot_id,
                cluster_cases,
                district_id,
                crime_id,
                time_bucket
            )

            hotspots.append(
                hotspot
            )

            hotspot_id += 1

    # --------------------------------------------------------
    # Classify intensity
    # --------------------------------------------------------

    cluster_sizes = [
        hotspot["case_count"]
        for hotspot in hotspots
    ]

    for hotspot in hotspots:

        hotspot[
            "intensity"
        ] = classify_hotspot_intensity(
            hotspot["case_count"],
            cluster_sizes
        )

    return sorted(
        hotspots,
        key=lambda x: -x[
            "case_count"
        ]
    )


# ============================================================
# FINAL HOTSPOT REPORT
# ============================================================

def build_hotspot_report(
    cases,
    eps_km=DEFAULT_EPS_KM,
    min_samples=DEFAULT_MIN_SAMPLES
):
    """
    Main function for hotspot analysis.

    Returns:

        spatial_hotspots

        spatiotemporal_hotspots

        parameters

        summary
    """

    spatial_hotspots = find_hotspots(
        cases,
        eps_km=eps_km,
        min_samples=min_samples
    )

    spatiotemporal_hotspots = (
        find_spatiotemporal_hotspots(
            cases,
            eps_km=eps_km,
            min_samples=min_samples
        )
    )

    return {

        "summary": {

            "total_valid_cases":
                len(
                    filter_valid_cases(
                        cases
                    )
                ),

            "spatial_hotspot_count":
                len(
                    spatial_hotspots
                ),

            "spatiotemporal_hotspot_count":
                len(
                    spatiotemporal_hotspots
                ),

        },

        "spatial_hotspots":
            spatial_hotspots,

        "spatiotemporal_hotspots":
            spatiotemporal_hotspots,

        "parameters": {

            "eps_km":
                eps_km,

            "min_samples":
                min_samples,

            "minimum_cases_for_clustering":
                MIN_CASES_FOR_CLUSTERING

        }
    }


# ============================================================
# TEST DATA
# ============================================================

if __name__ == "__main__":

    import json
    import random

    random.seed(10)

    cases = []

    case_id = 1


    # ========================================================
    # HOTSPOT 1
    #
    # District 1
    # Crime Type 1
    # 20 nearby cases
    # Mostly evening
    # ========================================================

    for i in range(20):

        cases.append({

            "case_id":
                case_id,

            "district_id":
                1,

            "crime_major_head_id":
                1,

            "crime_registered_date":
                f"2026-01-{1 + i:02d}",

            "hour":
                random.choice(
                    [18, 19, 20]
                ),

            "latitude":
                22.5726
                +
                random.uniform(
                    -0.002,
                    0.002
                ),

            "longitude":
                88.3639
                +
                random.uniform(
                    -0.002,
                    0.002
                )
        })

        case_id += 1


    # ========================================================
    # HOTSPOT 2
    #
    # District 1
    # Crime Type 1
    # Another location
    # Mostly night
    # ========================================================

    for i in range(10):

        cases.append({

            "case_id":
                case_id,

            "district_id":
                1,

            "crime_major_head_id":
                1,

            "crime_registered_date":
                f"2026-02-{1 + i:02d}",

            "hour":
                random.choice(
                    [21, 22, 23]
                ),

            "latitude":
                22.5850
                +
                random.uniform(
                    -0.002,
                    0.002
                ),

            "longitude":
                88.3750
                +
                random.uniform(
                    -0.002,
                    0.002
                )
        })

        case_id += 1


    # ========================================================
    # DISTRICT 2
    #
    # Different district
    # Same crime type
    # Mostly morning
    # ========================================================

    for i in range(10):

        cases.append({

            "case_id":
                case_id,

            "district_id":
                2,

            "crime_major_head_id":
                1,

            "crime_registered_date":
                f"2026-02-{1 + i:02d}",

            "hour":
                random.choice(
                    [8, 9, 10]
                ),

            "latitude":
                22.5200
                +
                random.uniform(
                    -0.002,
                    0.002
                ),

            "longitude":
                88.3400
                +
                random.uniform(
                    -0.002,
                    0.002
                )
        })

        case_id += 1


    # ========================================================
    # SCATTERED NOISE CASES
    #
    # These cases are far apart and should not
    # normally form a hotspot.
    # ========================================================

    for i in range(10):

        cases.append({

            "case_id":
                case_id,

            "district_id":
                1,

            "crime_major_head_id":
                1,

            "crime_registered_date":
                "2026-03-01",

            "hour":
                random.randint(
                    0,
                    23
                ),

            "latitude":
                22.4
                +
                random.uniform(
                    -0.3,
                    0.3
                ),

            "longitude":
                88.2
                +
                random.uniform(
                    -0.3,
                    0.3
                )
        })

        case_id += 1


    # ========================================================
    # RUN HOTSPOT ANALYSIS
    # ========================================================

    report = build_hotspot_report(
        cases,
        eps_km=1.0,
        min_samples=5
    )


    print(
        json.dumps(
            report,
            indent=4
        )
    )