from collections import defaultdict
from scipy.stats import chi2 # type: ignore


MIN_SAMPLE_SIZE = 30
MIN_EXPECTED_COUNT = 5
SIGNIFICANCE_LEVEL = 0.05


def is_valid_case_record(record, field_a, field_b):
    if field_a not in record or field_b not in record:
        return False

    if record[field_a] is None or record[field_b] is None:
        return False

    return True


def build_contingency_table(cases, field_a, field_b):
    table = defaultdict(lambda: defaultdict(int))

    for record in cases:
        if not is_valid_case_record(
            record,
            field_a,
            field_b
        ):
            continue

        a_value = record[field_a]
        b_value = record[field_b]

        table[a_value][b_value] += 1

    return {
        a_value: dict(b_counts)
        for a_value, b_counts in table.items()
    }


def get_row_totals(table):
    return {
        a_value: sum(b_counts.values())
        for a_value, b_counts in table.items()
    }


def get_column_totals(table):
    col_totals = defaultdict(int)

    for b_counts in table.values():
        for b_value, count in b_counts.items():
            col_totals[b_value] += count

    return dict(col_totals)


def get_degrees_of_freedom(table):
    num_rows = len(table)
    num_cols = len(get_column_totals(table))

    return (
        num_rows - 1
    ) * (
        num_cols - 1
    )


def chi_square_statistic(table):
    row_totals = get_row_totals(table)
    col_totals = get_column_totals(table)

    grand_total = sum(row_totals.values())

    if grand_total == 0:
        return {
            "chi_square": 0,
            "grand_total": 0,
            "degrees_of_freedom": 0,
            "min_expected_count": 0,
            "small_expected_cells": False
        }

    chi_square_value = 0
    min_expected_count = float("inf")

    for a_value, row_total in row_totals.items():

        for b_value, col_total in col_totals.items():

            observed = (
                table
                .get(a_value, {})
                .get(b_value, 0)
            )

            expected = (
                row_total * col_total
            ) / grand_total

            if expected == 0:
                continue

            min_expected_count = min(
                min_expected_count,
                expected
            )

            chi_square_value += (
                (observed - expected) ** 2
            ) / expected

    degrees_of_freedom = get_degrees_of_freedom(
        table
    )

    small_expected_cells = (
        min_expected_count
        < MIN_EXPECTED_COUNT
    )

    return {
        "chi_square": chi_square_value,
        "grand_total": grand_total,
        "degrees_of_freedom": degrees_of_freedom,
        "min_expected_count": min_expected_count,
        "small_expected_cells": small_expected_cells
    }


def calculate_p_value(
    chi_square_value,
    degrees_of_freedom
):
    if degrees_of_freedom <= 0:
        return 1.0

    return float(
        chi2.sf(
            chi_square_value,
            degrees_of_freedom
        )
    )


def cramers_v(
    chi_square_value,
    grand_total,
    table
):
    if grand_total == 0:
        return 0

    num_rows = len(table)
    num_cols = len(
        get_column_totals(table)
    )

    min_dimension = min(
        num_rows - 1,
        num_cols - 1
    )

    if min_dimension <= 0:
        return 0

    v = (
        chi_square_value
        / (
            grand_total
            * min_dimension
        )
    ) ** 0.5

    return round(v, 3)


def classify_correlation_strength(v):
    if v >= 0.5:
        return "STRONG"

    if v >= 0.3:
        return "MODERATE"

    if v >= 0.1:
        return "WEAK"

    return "NONE"


def correlate_fields(
    cases,
    field_a,
    field_b
):
    table = build_contingency_table(
        cases,
        field_a,
        field_b
    )

    row_totals = get_row_totals(table)
    column_totals = get_column_totals(table)

    grand_total = sum(
        row_totals.values()
    )

    if grand_total < MIN_SAMPLE_SIZE:
        return {
            "field_a": field_a,
            "field_b": field_b,
            "sample_size": grand_total,
            "analysis_status": "INSUFFICIENT_DATA",
            "data_quality": "INSUFFICIENT",
            "message": (
                "Not enough data for reliable "
                "association analysis."
            )
        }

    if len(row_totals) < 2 or len(column_totals) < 2:
        return {
            "field_a": field_a,
            "field_b": field_b,
            "sample_size": grand_total,
            "analysis_status": "NO_VARIATION",
            "data_quality": "INSUFFICIENT",
            "message": (
                "At least two unique values are "
                "required in both fields."
            )
        }

    chi_square_result = chi_square_statistic(
        table
    )

    chi_square_value = (
        chi_square_result[
            "chi_square"
        ]
    )

    degrees_of_freedom = (
        chi_square_result[
            "degrees_of_freedom"
        ]
    )

    min_expected_count = (
        chi_square_result[
            "min_expected_count"
        ]
    )

    small_expected_cells = (
        chi_square_result[
            "small_expected_cells"
        ]
    )

    p_value = calculate_p_value(
        chi_square_value,
        degrees_of_freedom
    )

    v = cramers_v(
        chi_square_value,
        grand_total,
        table
    )

    strength = classify_correlation_strength(
        v
    )

    statistically_significant = (
        p_value < SIGNIFICANCE_LEVEL
    )

    if small_expected_cells:
        data_quality = "CAUTION"
        analysis_status = "SUCCESS_CAUTION"
    else:
        data_quality = "RELIABLE"
        analysis_status = "SUCCESS_RELIABLE"

    return {
        "field_a": field_a,
        "field_b": field_b,
        "sample_size": grand_total,
        "chi_square": round(
            chi_square_value,
            2
        ),
        "degrees_of_freedom": (
            degrees_of_freedom
        ),
        "p_value": round(
            p_value,
            6
        ),
        "cramers_v": v,
        "correlation_strength": strength,
        "statistically_significant": (
            statistically_significant
        ),
        "significance_level": (
            SIGNIFICANCE_LEVEL
        ),
        "min_expected_count": round(
            min_expected_count,
            2
        ),
        "small_expected_cells": (
            small_expected_cells
        ),
        "data_quality": data_quality,
        "analysis_status": analysis_status
    }


def find_top_correlations(
    cases,
    field_pairs
):
    results = []

    for field_a, field_b in field_pairs:

        result = correlate_fields(
            cases,
            field_a,
            field_b
        )

        results.append(result)

    return sorted(
        results,
        key=lambda result: -result.get(
            "cramers_v",
            0
        )
    )

import random
import json
from pols.analysis.correlation import find_top_correlations

random.seed(42)

cases = []
case_id = 1
for i in range(20):
    cases.append({
        "case_id": case_id,
        "crime_major_head_id": 1,
        "district_id": 1 if random.random() < 0.8 else 2,
        "case_status_id": random.choice([1, 2])
    })
    case_id += 1
for i in range(20):
    cases.append({
        "case_id": case_id,
        "crime_major_head_id": 2,
        "district_id": 2 if random.random() < 0.8 else 1,
        "case_status_id": random.choice([1, 2])
    })
    case_id += 1

field_pairs = [
    ("crime_major_head_id", "district_id"),
    ("crime_major_head_id", "case_status_id"),
]

print("=== enough data (40 cases) ===")
print(json.dumps(find_top_correlations(cases, field_pairs), indent=2))

small_cases = cases[:10]
print("\n=== too few rows (10 cases) -> should say INSUFFICIENT_DATA ===")
print(json.dumps(find_top_correlations(small_cases, field_pairs), indent=2))

same_value_cases = [
    {"case_id": i, "crime_major_head_id": 1, "district_id": 1, "case_status_id": 1}
    for i in range(35)
]
print("\n=== one field always the same value (35 cases) -> should say NO_VARIATION ===")
print(json.dumps(find_top_correlations(same_value_cases, [("crime_major_head_id", "district_id")]), indent=2))