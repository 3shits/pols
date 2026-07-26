from itertools import combinations
from collections import Counter, defaultdict

from anomaly import (
    parse_date,
    parse_hour,
    get_time_of_day_bucket
)


# ============================================================
# CONFIGURATION
# ============================================================

MO_MIN_CASES_FOR_PATTERN = 2

MIN_COVERAGE_FOR_SUBPATTERN = 0.5

DOMINANCE_THRESHOLD = 0.5

DAY_NAMES = [
    "MONDAY",
    "TUESDAY",
    "WEDNESDAY",
    "THURSDAY",
    "FRIDAY",
    "SATURDAY",
    "SUNDAY"
]


# ============================================================
# BASIC VALIDATION
# ============================================================

def is_valid_accused_record(record):
    if "case_id" not in record:
        return False

    if "person_id" not in record:
        return False

    if record["case_id"] is None:
        return False

    if record["person_id"] is None:
        return False

    return True


# ============================================================
# PERSON - CASE RELATIONSHIPS
# ============================================================

def build_person_case_relationships(accused):
    person_cases = defaultdict(set)

    for record in accused:

        if not is_valid_accused_record(record):
            continue

        person_id = record["person_id"]
        case_id = record["case_id"]

        person_cases[person_id].add(case_id)

    return dict(person_cases)


# ============================================================
# REPEAT ACCUSED DETECTION
# ============================================================

def find_repeat_accused(person_cases, threshold=3):

    repeat_accused = []

    for person_id, cases in person_cases.items():

        case_count = len(cases)

        if case_count >= threshold:

            repeat_accused.append({
                "person_id": person_id,
                "case_count": case_count,
                "is_repeat_accused": True
            })

    return repeat_accused


# ============================================================
# PERSON ASSOCIATION ANALYSIS
# ============================================================

def find_person_associations(accused):

    case_persons = defaultdict(set)

    for record in accused:

        if not is_valid_accused_record(record):
            continue

        case_id = record["case_id"]
        person_id = record["person_id"]

        case_persons[case_id].add(person_id)

    associations = defaultdict(int)

    for case_id, persons in case_persons.items():

        unique_persons = sorted(persons)

        for person_a, person_b in combinations(unique_persons, 2):

            associations[(person_a, person_b)] += 1

    return dict(associations)


def classify_association(shared_cases):

    if shared_cases >= 5:
        return "STRONG"

    if shared_cases >= 3:
        return "MEDIUM"

    if shared_cases >= 1:
        return "WEAK"

    return "NONE"


# ============================================================
# PERSON LOCATION ANALYSIS
# ============================================================

def find_person_locations(accused, cases):

    case_to_location = {}

    for case in cases:

        case_id = case.get("case_id")
        location_id = case.get("location_id")

        if case_id is not None and location_id is not None:

            case_to_location[case_id] = location_id

    person_cases = defaultdict(set)

    for record in accused:

        if not is_valid_accused_record(record):
            continue

        person_id = record["person_id"]
        case_id = record["case_id"]

        person_cases[person_id].add(case_id)

    person_locations = defaultdict(lambda: defaultdict(int))

    for person_id, case_ids in person_cases.items():

        for case_id in case_ids:

            location_id = case_to_location.get(case_id)

            if location_id is not None:

                person_locations[person_id][location_id] += 1

    return {
        person_id: dict(locations)
        for person_id, locations in person_locations.items()
    }


# ============================================================
# BUILD PERSON CASE RECORDS
# ============================================================

def build_person_case_records(accused, cases):

    case_by_id = {
        case["case_id"]: case
        for case in cases
        if case.get("case_id") is not None
    }

    person_case_records = defaultdict(list)

    for record in accused:

        if not is_valid_accused_record(record):
            continue

        case = case_by_id.get(record["case_id"])

        if case is not None:

            person_case_records[
                record["person_id"]
            ].append(case)

    return dict(person_case_records)


# ============================================================
# GENERIC BREAKDOWN
# ============================================================

def build_breakdown(case_records, extractor):

    counter = Counter()

    for case in case_records:

        value = extractor(case)

        if value is not None:

            counter[value] += 1

    return counter


# ============================================================
# DOMINANT VALUE
# ============================================================

def dominant_from_counter(counter, total_cases):

    if not counter or total_cases == 0:

        return None, 0, 0.0

    items_sorted = sorted(
        counter.items(),
        key=lambda kv: (-kv[1], str(kv[0]))
    )

    dominant_key, dominant_count = items_sorted[0]

    return (
        dominant_key,
        dominant_count,
        round(dominant_count / total_cases, 3)
    )


# ============================================================
# COVERAGE CHECK
# ============================================================

def has_enough_coverage(
    counter,
    total_cases,
    min_coverage=MIN_COVERAGE_FOR_SUBPATTERN
):

    if total_cases == 0:

        return False

    covered = sum(counter.values())

    return (
        covered / total_cases
    ) >= min_coverage


# ============================================================
# CRIME PATTERN
# ============================================================

def build_crime_pattern(case_records, total_cases):

    major_breakdown = build_breakdown(
        case_records,
        lambda c: c.get("crime_major_head_id")
    )

    (
        dominant_crime_type,
        dominant_crime_count,
        dominant_crime_percentage
    ) = dominant_from_counter(
        major_breakdown,
        total_cases
    )

    pattern = {

        "crime_type_breakdown":
            dict(major_breakdown),

        "dominant_crime_type":
            dominant_crime_type,

        "dominant_crime_count":
            dominant_crime_count,

        "dominant_crime_percentage":
            dominant_crime_percentage
    }

    minor_breakdown = build_breakdown(
        case_records,
        lambda c: c.get("crime_minor_head_id")
    )

    if (
        minor_breakdown
        and has_enough_coverage(
            minor_breakdown,
            total_cases
        )
    ):

        (
            dominant_minor,
            dominant_minor_count,
            dominant_minor_percentage
        ) = dominant_from_counter(
            minor_breakdown,
            sum(minor_breakdown.values())
        )

        pattern.update({

            "crime_minor_breakdown":
                dict(minor_breakdown),

            "dominant_crime_minor_type":
                dominant_minor,

            "dominant_crime_minor_count":
                dominant_minor_count,

            "dominant_crime_minor_percentage":
                dominant_minor_percentage
        })

    return pattern


# ============================================================
# LOCATION PATTERN
# ============================================================

def build_location_pattern(case_records, total_cases):

    # -------------------------
    # DISTRICT
    # -------------------------

    district_breakdown = build_breakdown(
        case_records,
        lambda c: c.get("district_id")
    )

    (
        dominant_district,
        dominant_district_count,
        dominant_district_percentage
    ) = dominant_from_counter(
        district_breakdown,
        total_cases
    )

    pattern = {

        "district_breakdown":
            dict(district_breakdown),

        "dominant_district":
            dominant_district,

        "dominant_district_case_count":
            dominant_district_count,

        "dominant_district_percentage":
            dominant_district_percentage
    }

    # -------------------------
    # POLICE STATION
    # -------------------------

    station_breakdown = build_breakdown(
        case_records,
        lambda c: c.get("unit_id")
    )

    if (
        station_breakdown
        and has_enough_coverage(
            station_breakdown,
            total_cases
        )
    ):

        (
            dominant_station,
            dominant_station_count,
            dominant_station_percentage
        ) = dominant_from_counter(
            station_breakdown,
            sum(station_breakdown.values())
        )

        pattern.update({

            "station_breakdown":
                dict(station_breakdown),

            "dominant_station":
                dominant_station,

            "dominant_station_case_count":
                dominant_station_count,

            "dominant_station_percentage":
                dominant_station_percentage
        })

    return pattern


# ============================================================
# TIME PATTERN
# ============================================================

def build_time_pattern(case_records, total_cases):

    time_of_day_breakdown = build_breakdown(
        case_records,
        lambda c:
            get_time_of_day_bucket(
                parse_hour(c)
            )
    )

    pattern = {}

    if (
        time_of_day_breakdown
        and has_enough_coverage(
            time_of_day_breakdown,
            total_cases
        )
    ):

        cases_with_time = sum(
            time_of_day_breakdown.values()
        )

        (
            dominant_time_period,
            dominant_time_count,
            dominant_time_percentage
        ) = dominant_from_counter(
            time_of_day_breakdown,
            cases_with_time
        )

        pattern.update({

            "time_of_day_breakdown":
                dict(time_of_day_breakdown),

            "dominant_time_period":
                dominant_time_period,

            "dominant_time_case_count":
                dominant_time_count,

            "dominant_time_percentage":
                dominant_time_percentage
        })

    # -------------------------
    # EXACT HOUR
    # -------------------------

    hour_breakdown = build_breakdown(
        case_records,
        lambda c: parse_hour(c)
    )

    if (
        hour_breakdown
        and has_enough_coverage(
            hour_breakdown,
            total_cases
        )
    ):

        pattern["hour_pattern"] = {
            str(hour): count
            for hour, count
            in sorted(hour_breakdown.items())
        }

    return pattern


# ============================================================
# DAY PATTERN
# ============================================================

def build_day_pattern(case_records, total_cases):

    def extract_day_name(case):

        parsed_date = parse_date(
            case.get("crime_registered_date")
        )

        if parsed_date is None:

            return None

        return DAY_NAMES[
            parsed_date.weekday()
        ]

    day_breakdown = build_breakdown(
        case_records,
        extract_day_name
    )

    if (
        not day_breakdown
        or not has_enough_coverage(
            day_breakdown,
            total_cases
        )
    ):

        return {}

    cases_with_day = sum(
        day_breakdown.values()
    )

    (
        dominant_day,
        dominant_day_count,
        dominant_day_percentage
    ) = dominant_from_counter(
        day_breakdown,
        cases_with_day
    )

    return {

        "day_breakdown":
            dict(day_breakdown),

        "dominant_day":
            dominant_day,

        "dominant_day_case_count":
            dominant_day_count,

        "dominant_day_percentage":
            dominant_day_percentage
    }


# ============================================================
# JURISDICTION PATTERN
# ============================================================

def build_jurisdiction_pattern(location_pattern):

    district_breakdown = location_pattern.get(
        "district_breakdown",
        {}
    )

    station_breakdown = location_pattern.get(
        "station_breakdown",
        {}
    )

    district_count = len(
        district_breakdown
    )

    station_count = len(
        station_breakdown
    ) if station_breakdown else 0

    # ========================================================
    # JURISDICTION CLASSIFICATION
    # ========================================================

    if district_count == 1 and station_count == 1:

        jurisdiction_pattern = (
            "SINGLE_DISTRICT_SINGLE_STATION"
        )

    elif district_count == 1 and station_count > 1:

        jurisdiction_pattern = (
            "SINGLE_DISTRICT_MULTI_STATION"
        )

    elif district_count > 1:

        jurisdiction_pattern = (
            "MULTI_DISTRICT_MULTI_STATION"
        )

    else:

        jurisdiction_pattern = (
            "UNKNOWN_JURISDICTION_PATTERN"
        )

    return {

        "district_count":
            district_count,

        "station_count":
            station_count,

        "cross_district_activity":
            district_count > 1,

        "cross_station_activity":
            station_count > 1,

        "jurisdiction_pattern":
            jurisdiction_pattern
    }


# ============================================================
# MO PROFILE
# ============================================================

def build_mo_profile(
    total_cases,
    crime_pattern,
    location_pattern,
    time_pattern,
    jurisdiction_pattern
):

    if total_cases < MO_MIN_CASES_FOR_PATTERN:

        return {

            "analysis_status":
                "INSUFFICIENT_DATA",

            "message":
                f"Fewer than {MO_MIN_CASES_FOR_PATTERN} cases -- "
                "not enough to establish a pattern."
        }

    # -------------------------
    # CRIME PATTERN
    # -------------------------

    if (
        crime_pattern[
            "dominant_crime_percentage"
        ]
        >= DOMINANCE_THRESHOLD
    ):

        crime_tag = (
            f"REPEATED_CRIME_TYPE_"
            f"{crime_pattern['dominant_crime_type']}"
        )

    else:

        crime_tag = (
            "MIXED_CRIME_TYPES"
        )

    # -------------------------
    # LOCATION PATTERN
    # -------------------------

    if (
        location_pattern[
            "dominant_district_percentage"
        ]
        >= DOMINANCE_THRESHOLD
    ):

        location_tag = (
            "DISTRICT_CONCENTRATED"
        )

    else:

        location_tag = (
            "MULTI_DISTRICT"
        )

    # -------------------------
    # TIME PATTERN
    # -------------------------

    if (
        time_pattern.get(
            "dominant_time_percentage",
            0.0
        )
        >= DOMINANCE_THRESHOLD
    ):

        time_tag = (
            f"{time_pattern['dominant_time_period']}"
            "_PATTERN"
        )

    else:

        time_tag = (
            "NO_CLEAR_TIME_PATTERN"
        )

    # -------------------------
    # JURISDICTION PATTERN
    # -------------------------

    jurisdiction_tag = jurisdiction_pattern[
        "jurisdiction_pattern"
    ]

    return {

        "analysis_status":
            "SUCCESS",

        "crime_pattern":
            crime_tag,

        "location_pattern":
            location_tag,

        "time_pattern":
            time_tag,

        "jurisdiction_pattern":
            jurisdiction_tag
    }


# ============================================================
# MO SUMMARY
# ============================================================

def build_mo_summary(
    crime_pattern,
    location_pattern,
    time_pattern,
    jurisdiction_pattern
):

    return {

        "dominant_crime_type":
            crime_pattern.get(
                "dominant_crime_type"
            ),

        "dominant_crime_case_count":
            crime_pattern.get(
                "dominant_crime_count"
            ),

        "dominant_district":
            location_pattern.get(
                "dominant_district"
            ),

        "dominant_district_case_count":
            location_pattern.get(
                "dominant_district_case_count"
            ),

        "dominant_station":
            location_pattern.get(
                "dominant_station"
            ),

        "dominant_station_case_count":
            location_pattern.get(
                "dominant_station_case_count"
            ),

        "dominant_time_period":
            time_pattern.get(
                "dominant_time_period"
            ),

        "dominant_time_case_count":
            time_pattern.get(
                "dominant_time_case_count"
            ),

        "cross_district":
            jurisdiction_pattern.get(
                "cross_district_activity",
                False
            ),

        "cross_station":
            jurisdiction_pattern.get(
                "cross_station_activity",
                False
            ),

        "jurisdiction_pattern":
            jurisdiction_pattern.get(
                "jurisdiction_pattern"
            )
    }


# ============================================================
# COMPLETE MO ANALYSIS
# ============================================================

def build_mo_analysis(case_records):

    total_cases = len(
        case_records
    )

    crime_pattern = build_crime_pattern(
        case_records,
        total_cases
    )

    location_pattern = build_location_pattern(
        case_records,
        total_cases
    )

    time_pattern = build_time_pattern(
        case_records,
        total_cases
    )

    day_pattern = build_day_pattern(
        case_records,
        total_cases
    )

    jurisdiction_pattern = build_jurisdiction_pattern(
        location_pattern
    )

    return {

        "crime_pattern":
            crime_pattern,

        "location_pattern":
            location_pattern,

        "time_pattern":
            time_pattern,

        "day_pattern":
            day_pattern,

        "jurisdiction_pattern":
            jurisdiction_pattern,

        "mo_summary":
            build_mo_summary(
                crime_pattern,
                location_pattern,
                time_pattern,
                jurisdiction_pattern
            ),

        "mo_profile":
            build_mo_profile(
                total_cases,
                crime_pattern,
                location_pattern,
                time_pattern,
                jurisdiction_pattern
            )
    }


# ============================================================
# COMPLETE RELATIONSHIP REPORT
# ============================================================

def build_relationship_report(
    accused,
    cases,
    repeat_threshold=3
):

    # -------------------------
    # PERSON CASES
    # -------------------------

    person_cases = build_person_case_relationships(
        accused
    )

    # -------------------------
    # REPEAT ACCUSED
    # -------------------------

    repeat_accused_records = find_repeat_accused(
        person_cases,
        repeat_threshold
    )

    repeat_accused = {
        record["person_id"]
        for record in repeat_accused_records
    }

    # -------------------------
    # ASSOCIATIONS
    # -------------------------

    associations = find_person_associations(
        accused
    )

    associations_by_person = defaultdict(list)

    for (
        person_a,
        person_b
    ), shared_cases in associations.items():

        strength = classify_association(
            shared_cases
        )

        associations_by_person[
            person_a
        ].append({

            "person_id":
                person_b,

            "shared_cases":
                shared_cases,

            "association_strength":
                strength
        })

        associations_by_person[
            person_b
        ].append({

            "person_id":
                person_a,

            "shared_cases":
                shared_cases,

            "association_strength":
                strength
        })

    # -------------------------
    # LOCATIONS
    # -------------------------

    person_locations = find_person_locations(
        accused,
        cases
    )

    # -------------------------
    # FULL CASE RECORDS
    # -------------------------

    person_case_records = build_person_case_records(
        accused,
        cases
    )

    report = []

    # ========================================================
    # BUILD PERSON REPORT
    # ========================================================

    for person_id, cases_set in person_cases.items():

        associated_persons = sorted(

            associations_by_person.get(
                person_id,
                []
            ),

            key=lambda association:
                -association[
                    "shared_cases"
                ]
        )

        locations = person_locations.get(
            person_id,
            {}
        )

        frequent_locations = [

            {
                "location_id":
                    location_id,

                "case_count":
                    count
            }

            for location_id, count

            in sorted(
                locations.items(),
                key=lambda item:
                    -item[1]
            )
        ]

        network_degree = len(
            associated_persons
        )

        mo_analysis = build_mo_analysis(

            person_case_records.get(
                person_id,
                []
            )
        )

        report.append({

            "person_id":
                person_id,

            "repeat_accused":
                person_id in repeat_accused,

            "total_cases":
                len(cases_set),

            "network_degree":
                network_degree,

            "associated_persons":
                associated_persons,

            "frequent_locations":
                frequent_locations,

            # Detailed MO analysis
            **mo_analysis

        })

    return sorted(

        report,

        key=lambda person:
            -person[
                "total_cases"
            ]
    )


# ============================================================
# TEST DATA
# ============================================================

# if __name__ == "__main__":

#     import json

#     cases = [

#         {
#             "case_id": 1,
#             "district_id": 1,
#             "unit_id": 101,
#             "crime_major_head_id": 1,
#             "location_id": 10,
#             "crime_registered_date": "2026-01-02",
#             "hour": 19
#         },

#         {
#             "case_id": 2,
#             "district_id": 1,
#             "unit_id": 101,
#             "crime_major_head_id": 1,
#             "location_id": 10,
#             "crime_registered_date": "2026-01-09",
#             "hour": 20
#         },

#         {
#             "case_id": 3,
#             "district_id": 1,
#             "unit_id": 101,
#             "crime_major_head_id": 1,
#             "location_id": 10,
#             "crime_registered_date": "2026-01-16",
#             "hour": 18
#         },

#         {
#             "case_id": 4,
#             "district_id": 1,
#             "unit_id": 101,
#             "crime_major_head_id": 1,
#             "location_id": 20,
#             "crime_registered_date": "2026-01-23",
#             "hour": 21
#         },

#         {
#             "case_id": 5,
#             "district_id": 1,
#             "unit_id": 102,
#             "crime_major_head_id": 2,
#             "location_id": 10,
#             "crime_registered_date": "2026-01-05",
#             "hour": 14
#         },

#         {
#             "case_id": 6,
#             "district_id": 2,
#             "unit_id": 201,
#             "crime_major_head_id": 1,
#             "location_id": 30,
#             "crime_registered_date": "2026-02-01",
#             "hour": 22
#         },

#         {
#             "case_id": 7,
#             "district_id": 2,
#             "unit_id": 202,
#             "crime_major_head_id": 3,
#             "location_id": 40,
#             "crime_registered_date": "2026-02-08",
#             "hour": 10
#         },

#         {
#             "case_id": 8,
#             "district_id": 1,
#             "unit_id": 101,
#             "crime_major_head_id": 2,
#             "location_id": 20,
#             "crime_registered_date": "2026-02-12",
#             "hour": 15
#         },

#         {
#             "case_id": 9,
#             "district_id": 1,
#             "unit_id": 103,
#             "crime_major_head_id": 1,
#             "location_id": 50,
#             "crime_registered_date": "2026-02-14",
#             "hour": None
#         },

#         {
#             "case_id": 10,
#             "district_id": 3,
#             "unit_id": 301,
#             "crime_major_head_id": 4,
#             "location_id": 60,
#             "crime_registered_date": "2026-02-15",
#             "hour": 9
#         }
#     ]

#     accused = [

#         {
#             "case_id": 1,
#             "person_id": 101
#         },

#         {
#             "case_id": 2,
#             "person_id": 101
#         },

#         {
#             "case_id": 3,
#             "person_id": 101
#         },

#         {
#             "case_id": 3,
#             "person_id": 102
#         },

#         {
#             "case_id": 4,
#             "person_id": 101
#         },

#         {
#             "case_id": 4,
#             "person_id": 102
#         },

#         {
#             "case_id": 5,
#             "person_id": 102
#         },

#         {
#             "case_id": 6,
#             "person_id": 103
#         },

#         {
#             "case_id": 7,
#             "person_id": 103
#         },

#         {
#             "case_id": 8,
#             "person_id": 102
#         },

#         {
#             "case_id": 9,
#             "person_id": 101
#         },

#         {
#             "case_id": 10,
#             "person_id": 104
#         }
#     ]

#     report = build_relationship_report(

#         accused=accused,

#         cases=cases,

#         repeat_threshold=3
#     )

#     print(
#         json.dumps(
#             report,
#             indent=2
#         )
#     )
