from collections import defaultdict
from scipy.stats import pearsonr, spearmanr # type: ignore
from sklearn.ensemble import RandomForestRegressor # type: ignore


MIN_DISTRICTS_FOR_ANALYSIS = 10
MIN_OBSERVATIONS_FOR_RANDOM_FOREST = 20
SIGNIFICANCE_LEVEL = 0.05


def build_crime_counts_by_district(cases):
    counts = defaultdict(int)

    for record in cases:
        district_id = record.get("district_id")

        if district_id is None:
            continue

        counts[district_id] += 1

    return dict(counts)


def build_crime_rate_per_100k(
    crime_counts,
    population_by_district
):
    rates = {}

    for district_id, count in crime_counts.items():

        population = population_by_district.get(
            district_id
        )

        if population is None or population <= 0:
            continue

        rate = (
            count / population
        ) * 100000

        rates[district_id] = round(
            rate,
            2
        )

    return rates


def align_district_values(
    crime_rates,
    factor_values
):
    x_values = []
    y_values = []

    for district_id, crime_rate in crime_rates.items():

        factor = factor_values.get(
            district_id
        )

        if factor is None:
            continue

        x_values.append(
            factor
        )

        y_values.append(
            crime_rate
        )

    return x_values, y_values


def classify_correlation_strength(
    correlation
):
    absolute_value = abs(
        correlation
    )

    if absolute_value >= 0.7:
        return "STRONG"

    if absolute_value >= 0.4:
        return "MODERATE"

    if absolute_value >= 0.2:
        return "WEAK"

    return "NONE"


def get_correlation_direction(
    correlation
):
    if correlation > 0:
        return "POSITIVE"

    if correlation < 0:
        return "NEGATIVE"

    return "NONE"


def correlate_crime_with_factor(
    crime_rates,
    factor_name,
    factor_values
):
    x_values, y_values = align_district_values(
        crime_rates,
        factor_values
    )

    sample_size = len(
        x_values
    )

    if sample_size < MIN_DISTRICTS_FOR_ANALYSIS:

        return {
            "factor": factor_name,
            "sample_size": sample_size,
            "analysis_status": "INSUFFICIENT_DATA",
            "message": (
                "Need data from at least "
                f"{MIN_DISTRICTS_FOR_ANALYSIS} "
                "districts."
            )
        }

    if len(set(x_values)) < 2:

        return {
            "factor": factor_name,
            "sample_size": sample_size,
            "analysis_status": "NO_VARIATION",
            "message": (
                "The socio-economic factor "
                "has no variation across "
                "the available districts."
            )
        }

    if len(set(y_values)) < 2:

        return {
            "factor": factor_name,
            "sample_size": sample_size,
            "analysis_status": "NO_VARIATION",
            "message": (
                "Crime rates have no variation "
                "across the available districts."
            )
        }

    pearson_r, pearson_p = pearsonr(
        x_values,
        y_values
    )

    spearman_r, spearman_p = spearmanr(
        x_values,
        y_values
    )

    pearson_r = float(
        pearson_r
    )

    pearson_p = float(
        pearson_p
    )

    spearman_r = float(
        spearman_r
    )

    spearman_p = float(
        spearman_p
    )

    return {
        "factor": factor_name,
        "sample_size": sample_size,

        "pearson_correlation": round(
            pearson_r,
            3
        ),

        "pearson_p_value": round(
            pearson_p,
            6
        ),

        "pearson_strength": (
            classify_correlation_strength(
                pearson_r
            )
        ),

        "pearson_direction": (
            get_correlation_direction(
                pearson_r
            )
        ),

        "pearson_statistically_significant": (
            pearson_p
            < SIGNIFICANCE_LEVEL
        ),

        "spearman_correlation": round(
            spearman_r,
            3
        ),

        "spearman_p_value": round(
            spearman_p,
            6
        ),

        "spearman_strength": (
            classify_correlation_strength(
                spearman_r
            )
        ),

        "spearman_direction": (
            get_correlation_direction(
                spearman_r
            )
        ),

        "spearman_statistically_significant": (
            spearman_p
            < SIGNIFICANCE_LEVEL
        ),

        "analysis_status": "SUCCESS"
    }


def find_associated_factors(
    crime_rates,
    socioeconomic_data
):
    factor_names = set()

    for district_factors in (
        socioeconomic_data.values()
    ):

        factor_names.update(
            district_factors.keys()
        )

    results = []

    for factor_name in factor_names:

        factor_values = {
            district_id: factors.get(
                factor_name
            )
            for district_id, factors
            in socioeconomic_data.items()
        }

        result = correlate_crime_with_factor(
            crime_rates,
            factor_name,
            factor_values
        )

        results.append(
            result
        )

    return sorted(
        results,
        key=lambda result: max(
            abs(
                result.get(
                    "pearson_correlation",
                    0
                )
            ),
            abs(
                result.get(
                    "spearman_correlation",
                    0
                )
            )
        ),
        reverse=True
    )


def build_random_forest_dataset(
    crime_rates,
    socioeconomic_data,
    factor_names
):
    X = []
    y = []
    district_ids = []

    for district_id, crime_rate in (
        crime_rates.items()
    ):

        district_factors = (
            socioeconomic_data.get(
                district_id
            )
        )

        if district_factors is None:
            continue

        row = []

        valid_row = True

        for factor_name in factor_names:

            value = district_factors.get(
                factor_name
            )

            if value is None:
                valid_row = False
                break

            row.append(
                value
            )

        if not valid_row:
            continue

        X.append(
            row
        )

        y.append(
            crime_rate
        )

        district_ids.append(
            district_id
        )

    return X, y, district_ids


def random_forest_feature_importance(
    crime_rates,
    socioeconomic_data
):
    factor_names = sorted({
        name
        for district_factors
        in socioeconomic_data.values()
        for name
        in district_factors.keys()
    })

    if len(factor_names) == 0:

        return {
            "analysis_status": "NO_FACTORS",
            "message": (
                "No socio-economic factors "
                "were provided."
            )
        }

    X, y, district_ids = (
        build_random_forest_dataset(
            crime_rates,
            socioeconomic_data,
            factor_names
        )
    )

    sample_size = len(
        X
    )

    if (
        sample_size
        < MIN_OBSERVATIONS_FOR_RANDOM_FOREST
    ):

        return {
            "analysis_status": "INSUFFICIENT_DATA",
            "sample_size": sample_size,
            "message": (
                "Need at least "
                f"{MIN_OBSERVATIONS_FOR_RANDOM_FOREST} "
                "complete observations for "
                "Random Forest analysis."
            )
        }

    if len(set(y)) < 2:

        return {
            "analysis_status": "NO_VARIATION",
            "sample_size": sample_size,
            "message": (
                "Crime rates have no variation "
                "for model training."
            )
        }

    model = RandomForestRegressor(
        n_estimators=200,
        random_state=42,
        n_jobs=-1
    )

    model.fit(
        X,
        y
    )

    importances = list(
        zip(
            factor_names,
            model.feature_importances_
        )
    )

    importances.sort(
        key=lambda pair: -pair[1]
    )

    feature_importance = []

    for factor_name, importance in (
        importances
    ):

        factor_values = {
            district_id: factors.get(
                factor_name
            )
            for district_id, factors
            in socioeconomic_data.items()
        }

        x_values, y_values = (
            align_district_values(
                crime_rates,
                factor_values
            )
        )

        if (
            len(x_values)
            >= MIN_DISTRICTS_FOR_ANALYSIS
            and len(set(x_values)) >= 2
            and len(set(y_values)) >= 2
        ):

            correlation, p_value = pearsonr(
                x_values,
                y_values
            )

            correlation = float(
                correlation
            )

            p_value = float(
                p_value
            )

            direction = (
                get_correlation_direction(
                    correlation
                )
            )

        else:

            correlation = None
            p_value = None
            direction = "UNKNOWN"

        feature_importance.append({
            "factor": factor_name,

            "importance": round(
                float(importance),
                4
            ),

            "correlation_with_crime_rate": (
                round(
                    correlation,
                    3
                )
                if correlation is not None
                else None
            ),

            "correlation_p_value": (
                round(
                    p_value,
                    6
                )
                if p_value is not None
                else None
            ),

            "correlation_direction": (
                direction
            )
        })

    return {
        "analysis_status": "SUCCESS",
        "sample_size": sample_size,
        "feature_importance": (
            feature_importance
        ),
        "interpretation_warning": (
            "Feature importance indicates "
            "predictive usefulness, not causation."
        )
    }


def sociological_crime_analysis(
    cases,
    population_by_district,
    socioeconomic_data
):
    crime_counts = (
        build_crime_counts_by_district(
            cases
        )
    )

    crime_rates = (
        build_crime_rate_per_100k(
            crime_counts,
            population_by_district
        )
    )

    correlations = (
        find_associated_factors(
            crime_rates,
            socioeconomic_data
        )
    )

    feature_importance = (
        random_forest_feature_importance(
            crime_rates,
            socioeconomic_data
        )
    )

    return {
        "crime_rate_per_100k_by_district": (
            crime_rates
        ),

        "associated_socioeconomic_factors": (
            correlations
        ),

        "combined_feature_importance": (
            feature_importance
        ),

        "analysis_warning": (
            "These results identify statistical "
            "associations and predictive patterns. "
            "They do not establish that any "
            "socio-economic factor causes crime."
        )
    }

cases = [
    {"case_id": 1, "district_id": 1},
    {"case_id": 2, "district_id": 2},
    {"case_id": 3, "district_id": 3},
    {"case_id": 4, "district_id": 4},
    {"case_id": 5, "district_id": 5},
    {"case_id": 6, "district_id": 6},
    {"case_id": 7, "district_id": 7},
    {"case_id": 8, "district_id": 8},
    {"case_id": 9, "district_id": 9},
    {"case_id": 10, "district_id": 10},
    {"case_id": 11, "district_id": 11},
    {"case_id": 12, "district_id": 12},
    {"case_id": 13, "district_id": 13},
    {"case_id": 14, "district_id": 14},
    {"case_id": 15, "district_id": 15}
]


population_by_district = {
    1: 500000,
    2: 600000,
    3: 450000,
    4: 700000,
    5: 550000,
    6: 800000,
    7: 650000,
    8: 400000,
    9: 900000,
    10: 750000,
    11: 480000,
    12: 620000,
    13: 580000,
    14: 720000,
    15: 520000
}


socioeconomic_data = {
    1: {
        "urbanization_pct": 85,
        "unemployment_rate": 8.5,
        "literacy_rate": 78,
        "population_density": 5000,
        "poverty_rate": 15
    },

    2: {
        "urbanization_pct": 80,
        "unemployment_rate": 7.8,
        "literacy_rate": 82,
        "population_density": 4500,
        "poverty_rate": 13
    },

    3: {
        "urbanization_pct": 75,
        "unemployment_rate": 7.2,
        "literacy_rate": 85,
        "population_density": 4000,
        "poverty_rate": 12
    },

    4: {
        "urbanization_pct": 70,
        "unemployment_rate": 6.8,
        "literacy_rate": 88,
        "population_density": 3500,
        "poverty_rate": 10
    },

    5: {
        "urbanization_pct": 65,
        "unemployment_rate": 6.5,
        "literacy_rate": 80,
        "population_density": 3000,
        "poverty_rate": 14
    },

    6: {
        "urbanization_pct": 60,
        "unemployment_rate": 6.0,
        "literacy_rate": 90,
        "population_density": 2800,
        "poverty_rate": 9
    },

    7: {
        "urbanization_pct": 55,
        "unemployment_rate": 5.8,
        "literacy_rate": 86,
        "population_density": 2500,
        "poverty_rate": 11
    },

    8: {
        "urbanization_pct": 50,
        "unemployment_rate": 5.2,
        "literacy_rate": 92,
        "population_density": 2200,
        "poverty_rate": 8
    },

    9: {
        "urbanization_pct": 45,
        "unemployment_rate": 4.8,
        "literacy_rate": 88,
        "population_density": 2000,
        "poverty_rate": 10
    },

    10: {
        "urbanization_pct": 40,
        "unemployment_rate": 4.5,
        "literacy_rate": 94,
        "population_density": 1800,
        "poverty_rate": 7
    },

    11: {
        "urbanization_pct": 35,
        "unemployment_rate": 4.2,
        "literacy_rate": 83,
        "population_density": 1600,
        "poverty_rate": 12
    },

    12: {
        "urbanization_pct": 30,
        "unemployment_rate": 3.8,
        "literacy_rate": 91,
        "population_density": 1400,
        "poverty_rate": 9
    },

    13: {
        "urbanization_pct": 25,
        "unemployment_rate": 3.5,
        "literacy_rate": 87,
        "population_density": 1200,
        "poverty_rate": 13
    },

    14: {
        "urbanization_pct": 20,
        "unemployment_rate": 3.0,
        "literacy_rate": 95,
        "population_density": 900,
        "poverty_rate": 6
    },

    15: {
        "urbanization_pct": 15,
        "unemployment_rate": 2.8,
        "literacy_rate": 89,
        "population_density": 700,
        "poverty_rate": 8
    }
}
report = sociological_crime_analysis(
    cases,
    population_by_district,
    socioeconomic_data
)

import json

print(
    json.dumps(
        report,
        indent=4
    )
)