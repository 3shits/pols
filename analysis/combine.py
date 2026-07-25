from collections import defaultdict
from datetime import date, timedelta
import json
import random
from pols.analysis.risk import build_risk_report
from pols.analysis.anomaly import build_anomaly_report

try:
    from pols.analysis.cause import sociological_crime_analysis
except ImportError:
    sociological_crime_analysis = None


RECENT_ANOMALY_LOOKBACK_DAYS = 90

OVERALL_RISK_ORDER = [
    "LOW",
    "MEDIUM",
    "HIGH",
    "CRITICAL"
]
# This replaces the missing relationship_graph.py dependency.
# If you later have relationship_graph.py, you can replace
# this function with your actual Part 2 implementation.

def build_relationship_report(accused, cases):
    """
    Builds a simple person-level relationship report.

    accused format:
    {
        "case_id": 1,
        "person_id": 101
    }

    cases format:
    {
        "case_id": 1,
        "district_id": 1,
        "crime_major_head_id": 1
    }

    Output:
    [
        {
            "person_id": 101,
            "case_count": 5,
            "repeat_accused": True,
            "network_degree": 1,
            "associated_persons": [...]
        }
    ]
    """

    cases_by_id = {
        case.get("case_id"): case
        for case in cases
        if case.get("case_id") is not None
    }

    # --------------------------------------------------------
    # Find cases for each person
    # --------------------------------------------------------

    person_cases = defaultdict(set)

    for record in accused:

        case_id = record.get("case_id")
        person_id = record.get("person_id")

        if case_id is None or person_id is None:
            continue

        if case_id not in cases_by_id:
            continue

        person_cases[person_id].add(case_id)

    # --------------------------------------------------------
    # Find people who appeared in the same case
    # --------------------------------------------------------

    case_persons = defaultdict(set)

    for record in accused:

        case_id = record.get("case_id")
        person_id = record.get("person_id")

        if case_id is None or person_id is None:
            continue

        case_persons[case_id].add(person_id)

    # --------------------------------------------------------
    # Build network connections
    # --------------------------------------------------------

    person_connections = defaultdict(CounterSet)

    for case_id, persons in case_persons.items():

        persons = list(persons)

        for person_a in persons:

            for person_b in persons:

                if person_a == person_b:
                    continue

                person_connections[
                    person_a
                ].add(
                    person_b
                )

    # --------------------------------------------------------
    # Create final report
    # --------------------------------------------------------

    report = []

    for person_id, case_ids in person_cases.items():

        associated_persons = []

        connected_people = person_connections.get(
            person_id,
            CounterSet()
        )

        for other_person_id in connected_people:

            # Count how many cases both persons appeared in
            shared_cases = (
                person_cases[person_id]
                &
                person_cases[other_person_id]
            )

            shared_count = len(shared_cases)

            if shared_count >= 3:
                association_strength = "STRONG"

            elif shared_count >= 2:
                association_strength = "MODERATE"

            else:
                association_strength = "WEAK"

            associated_persons.append({
                "person_id": other_person_id,
                "shared_case_count": shared_count,
                "association_strength": association_strength
            })

        associated_persons.sort(
            key=lambda x: -x["shared_case_count"]
        )

        report.append({
            "person_id": person_id,
            "case_count": len(case_ids),
            "repeat_accused": len(case_ids) >= 2,
            "network_degree": len(connected_people),
            "associated_persons": associated_persons
        })

    return sorted(
        report,
        key=lambda x: -x["case_count"]
    )


class CounterSet:
    """
    Small helper class used to store unique connections.
    """

    def __init__(self):
        self.values = set()

    def add(self, value):
        self.values.add(value)

    def __iter__(self):
        return iter(self.values)

    def __len__(self):
        return len(self.values)


# ============================================================
# STEP 1
# INDEX CASES BY ID
# ============================================================

def index_cases_by_id(cases):

    return {
        case["case_id"]: case
        for case in cases
        if case.get("case_id") is not None
    }


# ============================================================
# STEP 2
# GROUP CASE IDS BY DISTRICT + CRIME
# ============================================================

def group_case_ids_by_district_crime(cases):

    groups = defaultdict(set)

    for case in cases:

        district_id = case.get(
            "district_id"
        )

        crime_id = case.get(
            "crime_major_head_id"
        )

        case_id = case.get(
            "case_id"
        )

        if (
            district_id is None
            or crime_id is None
            or case_id is None
        ):
            continue

        groups[
            (
                district_id,
                crime_id
            )
        ].add(
            case_id
        )

    return dict(groups)


# ============================================================
# STEP 3
# ROLL UP PART 6 ANOMALY RESULTS
# ============================================================

def rollup_anomalies_by_group(
    anomaly_results,
    cases_by_id,
    lookback_days=RECENT_ANOMALY_LOOKBACK_DAYS
):

    today = date.today()

    cutoff = (
        today
        -
        timedelta(
            days=lookback_days
        )
    )

    rollup = defaultdict(
        lambda: {
            "recent_anomaly_count": 0,
            "max_anomaly_score": 0.0,
            "highly_anomalous_count": 0,
            "suspicious_count": 0
        }
    )

    for result in anomaly_results:

        if result.get(
            "analysis_status"
        ) != "SUCCESS":
            continue

        district_id = result.get(
            "district_id"
        )

        crime_id = result.get(
            "crime_major_head_id"
        )

        if (
            district_id is None
            or crime_id is None
        ):
            continue

        case_id = result.get(
            "case_id"
        )

        case = cases_by_id.get(
            case_id
        )

        case_date_str = (
            case.get(
                "crime_registered_date"
            )
            if case
            else None
        )

        is_recent = True

        if case_date_str:

            try:

                case_date = date.fromisoformat(
                    str(
                        case_date_str
                    )[:10]
                )

                is_recent = (
                    case_date >= cutoff
                )

            except ValueError:

                is_recent = True

        group_key = (
            district_id,
            crime_id
        )

        bucket = rollup[
            group_key
        ]

        level = result.get(
            "anomaly_level"
        )

        score = result.get(
            "anomaly_score",
            0.0
        ) or 0.0

        bucket[
            "max_anomaly_score"
        ] = max(
            bucket[
                "max_anomaly_score"
            ],
            score
        )

        if is_recent:

            bucket[
                "recent_anomaly_count"
            ] += 1

        if level == "HIGHLY_ANOMALOUS":

            bucket[
                "highly_anomalous_count"
            ] += 1

        elif level == "SUSPICIOUS":

            bucket[
                "suspicious_count"
            ] += 1

    return dict(
        rollup
    )


# ============================================================
# STEP 4
# ROLL UP NETWORK INFORMATION
# ============================================================

def rollup_network_by_group(
    accused,
    cases_by_id,
    person_report
):

    person_by_id = {
        p["person_id"]: p
        for p in person_report
    }

    group_persons = defaultdict(set)

    for record in accused:

        case_id = record.get(
            "case_id"
        )

        person_id = record.get(
            "person_id"
        )

        if (
            case_id is None
            or person_id is None
        ):
            continue

        case = cases_by_id.get(
            case_id
        )

        if case is None:
            continue

        district_id = case.get(
            "district_id"
        )

        crime_id = case.get(
            "crime_major_head_id"
        )

        if (
            district_id is None
            or crime_id is None
        ):
            continue

        group_persons[
            (
                district_id,
                crime_id
            )
        ].add(
            person_id
        )

    rollup = {}

    for group_key, person_ids in group_persons.items():

        repeat_offender_count = 0

        strong_association_count = 0

        max_network_degree = 0

        for person_id in person_ids:

            person = person_by_id.get(
                person_id
            )

            if person is None:
                continue

            if person.get(
                "repeat_accused"
            ):
                repeat_offender_count += 1

            max_network_degree = max(
                max_network_degree,
                person.get(
                    "network_degree",
                    0
                )
            )

            for association in person.get(
                "associated_persons",
                []
            ):

                if (
                    association.get(
                        "association_strength"
                    )
                    ==
                    "STRONG"
                ):

                    strong_association_count += 1

                    break

        rollup[
            group_key
        ] = {
            "person_count": len(
                person_ids
            ),
            "repeat_offender_count":
                repeat_offender_count,
            "strong_association_count":
                strong_association_count,
            "max_network_degree":
                max_network_degree,
            "person_ids":
                sorted(
                    person_ids
                )
        }

    return rollup


# ============================================================
# STEP 5
# BUILD DISTRICT CAUSE LOOKUP
# ============================================================

def build_district_cause_lookup(
    cause_report
):

    crime_rates = (
        cause_report.get(
            "crime_rate_per_100k_by_district",
            {}
        )
    )

    top_factors = []

    strength_order = [
        "NONE",
        "WEAK",
        "MODERATE",
        "STRONG"
    ]

    for factor in cause_report.get(
        "associated_socioeconomic_factors",
        []
    ):

        if (
            factor.get(
                "analysis_status"
            )
            != "SUCCESS"
        ):
            continue

        pearson_strength = factor.get(
            "pearson_strength",
            "NONE"
        )

        spearman_strength = factor.get(
            "spearman_strength",
            "NONE"
        )

        strengths = [
            pearson_strength,
            spearman_strength
        ]

        strongest = max(
            strengths,
            key=lambda s:
            strength_order.index(s)
            if s in strength_order
            else 0
        )

        top_factors.append({
            "factor": factor.get(
                "factor"
            ),
            "strength": strongest,
            "direction": factor.get(
                "pearson_direction",
                "NONE"
            )
        })

    top_factors = top_factors[:3]

    lookup = {}

    for district_id, rate in crime_rates.items():

        lookup[
            district_id
        ] = {
            "crime_rate_per_100k":
                rate,
            "top_socioeconomic_factors":
                top_factors
        }

    return lookup


# ============================================================
# STEP 6
# COMPUTE OVERALL RISK
# ============================================================

def compute_overall_risk(
    risk_level,
    anomaly_bucket,
    network_bucket
):

    if risk_level in OVERALL_RISK_ORDER:

        level_index = (
            OVERALL_RISK_ORDER.index(
                risk_level
            )
        )

    else:

        level_index = 0

    bump = 0

    if (
        anomaly_bucket
        and
        anomaly_bucket.get(
            "highly_anomalous_count",
            0
        ) > 0
    ):

        bump += 1

    if (
        network_bucket
        and
        network_bucket.get(
            "repeat_offender_count",
            0
        ) >= 2
    ):

        bump += 1

    final_index = min(
        level_index + bump,
        len(
            OVERALL_RISK_ORDER
        ) - 1
    )

    return OVERALL_RISK_ORDER[
        final_index
    ]


# ============================================================
# MAIN PART 7 FUNCTION
# ============================================================

def build_district_crime_report(
    cases,
    accused,
    population_by_district,
    socioeconomic_data,
    unresolved_status_ids=None,
    weeks_ahead=4
):

    cases_by_id = (
        index_cases_by_id(
            cases
        )
    )

    # --------------------------------------------------------
    # PART 5
    # Predictive risk analysis
    # --------------------------------------------------------

    risk_report = build_risk_report(
        cases,
        unresolved_status_ids=
        unresolved_status_ids,
        weeks_ahead=
        weeks_ahead
    )

    # --------------------------------------------------------
    # PART 6
    # Anomaly detection
    # --------------------------------------------------------

    anomaly_report = (
        build_anomaly_report(
            cases
        )
    )

    anomaly_rollup = (
        rollup_anomalies_by_group(
            anomaly_report[
                "results"
            ],
            cases_by_id
        )
    )

    # --------------------------------------------------------
    # PART 4
    # Socio-economic analysis
    # --------------------------------------------------------

    district_cause_lookup = {}

    if sociological_crime_analysis:

        try:

            cause_report = (
                sociological_crime_analysis(
                    cases,
                    population_by_district,
                    socioeconomic_data
                )
            )

            district_cause_lookup = (
                build_district_cause_lookup(
                    cause_report
                )
            )

        except Exception as error:

            print(
                "Warning: Part 4 analysis failed:",
                error
            )

    # --------------------------------------------------------
    # PART 2
    # Network analysis
    # --------------------------------------------------------

    person_report = (
        build_relationship_report(
            accused,
            cases
        )
    )

    network_rollup = (
        rollup_network_by_group(
            accused,
            cases_by_id,
            person_report
        )
    )

    # --------------------------------------------------------
    # COMBINE EVERYTHING
    # --------------------------------------------------------

    combined = []

    for risk_row in risk_report:

        district_id = risk_row[
            "district_id"
        ]

        crime_id = risk_row[
            "crime_major_head_id"
        ]

        group_key = (
            district_id,
            crime_id
        )

        anomaly_bucket = (
            anomaly_rollup.get(
                group_key,
                {
                    "recent_anomaly_count": 0,
                    "max_anomaly_score": 0.0,
                    "highly_anomalous_count": 0,
                    "suspicious_count": 0
                }
            )
        )

        network_bucket = (
            network_rollup.get(
                group_key,
                {
                    "person_count": 0,
                    "repeat_offender_count": 0,
                    "strong_association_count": 0,
                    "max_network_degree": 0,
                    "person_ids": []
                }
            )
        )

        cause_bucket = (
            district_cause_lookup.get(
                district_id,
                {
                    "crime_rate_per_100k":
                        None,
                    "top_socioeconomic_factors":
                        []
                }
            )
        )

        overall_risk = (
            compute_overall_risk(
                risk_row[
                    "risk_level"
                ],
                anomaly_bucket,
                network_bucket
            )
        )

        combined.append({

            "district_id":
                district_id,

            "crime_major_head_id":
                crime_id,

            # --------------------------------------------
            # OVERALL RISK
            # --------------------------------------------

            "overall_risk":
                overall_risk,

            # --------------------------------------------
            # PART 5
            # --------------------------------------------

            "risk_score":
                risk_row.get(
                    "risk_score"
                ),

            "risk_level":
                risk_row.get(
                    "risk_level"
                ),

            "trend_slope":
                risk_row.get(
                    "trend_slope"
                ),

            "trend_significant":
                risk_row.get(
                    "trend_significant"
                ),

            "forecast_next_period_count":
                risk_row.get(
                    "forecast_next_period_count"
                ),

            "recent_case_total":
                risk_row.get(
                    "recent_case_total"
                ),

            # --------------------------------------------
            # PART 4
            # --------------------------------------------

            "crime_rate_per_100k":
                cause_bucket[
                    "crime_rate_per_100k"
                ],

            "top_socioeconomic_factors":
                cause_bucket[
                    "top_socioeconomic_factors"
                ],

            # --------------------------------------------
            # PART 6
            # --------------------------------------------

            "recent_anomaly_count":
                anomaly_bucket[
                    "recent_anomaly_count"
                ],

            "highly_anomalous_case_count":
                anomaly_bucket[
                    "highly_anomalous_count"
                ],

            "suspicious_case_count":
                anomaly_bucket[
                    "suspicious_count"
                ],

            "max_anomaly_score":
                anomaly_bucket[
                    "max_anomaly_score"
                ],

            # --------------------------------------------
            # PART 2
            # --------------------------------------------

            "repeat_offender_count":
                network_bucket[
                    "repeat_offender_count"
                ],

            "strong_association_count":
                network_bucket[
                    "strong_association_count"
                ],

            "max_network_degree":
                network_bucket[
                    "max_network_degree"
                ],

            "flagged_person_ids":
                network_bucket[
                    "person_ids"
                ]
        })

    return sorted(
        combined,
        key=lambda row:
        -(
            row.get(
                "risk_score"
            )
            or 0
        )
    )


# ============================================================
# PERSON REPORT
# ============================================================

def build_person_report(
    cases,
    accused
):

    cases_by_id = (
        index_cases_by_id(
            cases
        )
    )

    person_report = (
        build_relationship_report(
            accused,
            cases
        )
    )

    person_to_groups = defaultdict(
        set
    )

    for record in accused:

        case_id = record.get(
            "case_id"
        )

        person_id = record.get(
            "person_id"
        )

        if (
            case_id is None
            or person_id is None
        ):
            continue

        case = cases_by_id.get(
            case_id
        )

        if case is None:
            continue

        district_id = case.get(
            "district_id"
        )

        crime_id = case.get(
            "crime_major_head_id"
        )

        if (
            district_id is None
            or crime_id is None
        ):
            continue

        person_to_groups[
            person_id
        ].add(
            (
                district_id,
                crime_id
            )
        )

    enriched = []

    for person in person_report:

        groups = sorted(
            person_to_groups.get(
                person[
                    "person_id"
                ],
                set()
            )
        )

        enriched.append({
            **person,

            "district_crime_groups": [
                {
                    "district_id": district_id,
                    "crime_major_head_id": crime_id
                }

                for district_id, crime_id
                in groups
            ]
        })

    return enriched


# ============================================================
# TEST DATA
# ============================================================

if __name__ == "__main__":

    random.seed(
        7
    )

    cases = []

    case_id = 1

    # --------------------------------------------------------
    # DISTRICT 1
    # Rising crime trend
    # --------------------------------------------------------

    for district_id, base_count, growth in [
        (1, 3, 1),
        (2, 2, 0)
    ]:

        for week in range(
            20
        ):

            if growth:

                count = (
                    base_count
                    +
                    week // 2
                    +
                    random.randint(
                        0,
                        1
                    )
                )

            else:

                count = (
                    base_count
                    +
                    random.randint(
                        0,
                        1
                    )
                )

            for _ in range(
                count
            ):

                day_offset = (
                    week * 7
                    +
                    random.randint(
                        0,
                        6
                    )
                )

                # Keep dates valid for testing
                start_date = date(
                    2026,
                    1,
                    1
                )

                case_date = (
                    start_date
                    +
                    timedelta(
                        days=day_offset
                    )
                )

                cases.append({

                    "case_id":
                        case_id,

                    "district_id":
                        district_id,

                    "crime_major_head_id":
                        1,

                    "crime_registered_date":
                        case_date.isoformat(),

                    "latitude":
                        12.97
                        +
                        district_id
                        *
                        0.1,

                    "longitude":
                        77.59
                        +
                        district_id
                        *
                        0.1,

                    "case_status_id":
                        random.choice(
                            [
                                1,
                                1,
                                2
                            ]
                        )
                })

                case_id += 1

    # --------------------------------------------------------
    # ACCUSED PERSON DATA
    # --------------------------------------------------------

    accused = []

    district_1_case_ids = [

        case["case_id"]

        for case in cases

        if case[
            "district_id"
        ] == 1

    ][:8]

    for cid in district_1_case_ids:

        accused.append({

            "case_id":
                cid,

            "person_id":
                101
        })

        accused.append({

            "case_id":
                cid,

            "person_id":
                102
        })

    # --------------------------------------------------------
    # POPULATION
    # --------------------------------------------------------

    population_by_district = {

        1:
            500000,

        2:
            300000
    }

    # --------------------------------------------------------
    # SOCIO-ECONOMIC DATA
    # --------------------------------------------------------

    socioeconomic_data = {

        1: {
            "urbanization_pct":
                85,

            "unemployment_rate":
                9.0
        },

        2: {
            "urbanization_pct":
                30,

            "unemployment_rate":
                4.0
        }
    }

    # --------------------------------------------------------
    # RUN PART 7
    # --------------------------------------------------------

    report = (
        build_district_crime_report(

            cases,

            accused,

            population_by_district,

            socioeconomic_data,

            unresolved_status_ids={
                1
            },

            weeks_ahead=4
        )
    )

    print(
        "=== DISTRICT x CRIME REPORT ==="
    )

    print(
        json.dumps(
            report,
            indent=2
        )
    )

    # --------------------------------------------------------
    # PERSON REPORT
    # --------------------------------------------------------

    person_report = (
        build_person_report(
            cases,
            accused
        )
    )

    print(
        "\n=== PERSON REPORT ==="
    )

    print(
        json.dumps(
            person_report,
            indent=2
        )
    )