from collections import defaultdict

from trend import build_weekly_series, get_mean
from risk import calculate_linear_trend


# ============================================================
# CONFIGURATION
# ============================================================

MIN_WEEKS_FOR_PREDICTION = 6

PREDICTION_WEEKS_AHEAD = 4

RECENT_WEEKS = 4

STABLE_BAND_PERCENTAGE = 10.0

MIN_HISTORICAL_AVERAGE_FOR_PERCENTAGE = 2.0

# Minimum percentage increase required to consider
# recent crime activity meaningfully elevated.
RECENT_ACTIVITY_WARNING_THRESHOLD = 20.0


# ============================================================
# BASIC HELPERS
# ============================================================

def safe_percentage_change(old_value, new_value):
    """
    Calculates percentage change from old_value to new_value.

    Returns None when old_value is zero because percentage
    increase from zero is not meaningful.
    """

    if old_value is None or new_value is None:
        return None

    if old_value <= 0:
        return None

    return round(
        ((new_value - old_value) / old_value) * 100,
        2
    )


# ============================================================
# FUTURE FORECAST
# ============================================================

def forecast_future_weekly_counts(
    trend_metrics,
    weekly_counts,
    weeks_ahead=PREDICTION_WEEKS_AHEAD
):
    """
    Predicts crime count for each future week.

    Returns:
        [week1_prediction,
         week2_prediction,
         week3_prediction,
         week4_prediction]

    None is returned when there is not enough valid trend data.
    """

    if trend_metrics["status"] != "OK":
        return None

    if not weekly_counts:
        return None

    last_index = len(weekly_counts) - 1

    predictions = []

    for step in range(1, weeks_ahead + 1):

        future_index = last_index + step

        predicted = (
            trend_metrics["slope"] * future_index
            + trend_metrics["intercept"]
        )

        predictions.append(
            round(max(predicted, 0.0), 2)
        )

    return predictions


# ============================================================
# HISTORICAL BASELINE
# ============================================================

def calculate_historical_average(weekly_counts):

    if not weekly_counts:
        return 0.0

    return round(
        get_mean(weekly_counts),
        2
    )


# ============================================================
# RECENT ACTIVITY
# ============================================================

def calculate_recent_average(
    weekly_counts,
    recent_weeks=RECENT_WEEKS
):
    """
    Calculates the average crime count in the most recent
    few weeks.

    Example:

        Historical:
        5, 6, 5, 7, 6, 8, 9, 10

        Recent 4 weeks:
        6, 8, 9, 10

        Recent average:
        8.25
    """

    if not weekly_counts:
        return 0.0

    recent_counts = weekly_counts[-recent_weeks:]

    if not recent_counts:
        return 0.0

    return round(
        get_mean(recent_counts),
        2
    )


def calculate_recent_activity_change(
    historical_average,
    recent_average
):
    """
    Measures how much recent crime activity has changed
    compared with the overall historical average.
    """

    return safe_percentage_change(
        historical_average,
        recent_average
    )


# ============================================================
# PREDICTED INCREASE
# ============================================================

def calculate_predicted_increase(
    historical_average,
    predicted_weekly_average
):
    """
    Calculates percentage change between historical crime
    activity and predicted future activity.
    """

    return safe_percentage_change(
        historical_average,
        predicted_weekly_average
    )


# ============================================================
# PREDICTION DIRECTION
# ============================================================

def classify_prediction_direction(
    trend_metrics,
    predicted_increase_percentage
):
    """
    Classifies future crime direction as:

        INCREASING
        STABLE
        DECREASING
        UNKNOWN
    """

    if trend_metrics["status"] != "OK":
        return "UNKNOWN"

    if predicted_increase_percentage is None:

        if trend_metrics["slope"] > 0:
            return "INCREASING"

        if trend_metrics["slope"] < 0:
            return "DECREASING"

        return "STABLE"

    if predicted_increase_percentage > STABLE_BAND_PERCENTAGE:
        return "INCREASING"

    if predicted_increase_percentage < -STABLE_BAND_PERCENTAGE:
        return "DECREASING"

    return "STABLE"


# ============================================================
# PREDICTION LEVEL
# ============================================================

def classify_prediction_level(
    predicted_weekly_average,
    historical_average,
    predicted_increase_percentage
):
    """
    Classifies future prediction severity.

    LOW
    MEDIUM
    HIGH
    CRITICAL
    UNKNOWN
    """

    if predicted_weekly_average is None:
        return "UNKNOWN"

    # Low-volume crime categories should not be
    # judged purely by percentage increases.
    if historical_average < MIN_HISTORICAL_AVERAGE_FOR_PERCENTAGE:

        if predicted_weekly_average >= 8:
            return "HIGH"

        if predicted_weekly_average >= 4:
            return "MEDIUM"

        return "LOW"

    if predicted_increase_percentage is None:
        return "LOW"

    if predicted_increase_percentage >= 75:
        return "CRITICAL"

    if predicted_increase_percentage >= 35:
        return "HIGH"

    if predicted_increase_percentage >= 10:
        return "MEDIUM"

    return "LOW"


# ============================================================
# CONFIDENCE
# ============================================================

def calculate_prediction_confidence(
    weekly_count,
    trend_metrics
):
    """
    Confidence is separate from prediction level.

    Example:

        Prediction Level: HIGH
        Confidence: LOW

    means:
        The model sees a potentially serious increase,
        but there is not enough reliable historical data
        to trust the prediction strongly.
    """

    if weekly_count < MIN_WEEKS_FOR_PREDICTION:

        return {
            "level": "LOW",
            "score": 0.25
        }

    if (
        trend_metrics["status"] == "OK"
        and trend_metrics["significant"]
    ):

        if weekly_count >= 12:

            return {
                "level": "HIGH",
                "score": 1.0
            }

        return {
            "level": "MEDIUM",
            "score": 0.75
        }

    if trend_metrics["status"] == "OK":

        return {
            "level": "MEDIUM",
            "score": 0.5
        }

    return {
        "level": "LOW",
        "score": 0.3
    }


# ============================================================
# EARLY WARNING PRIORITY
# ============================================================

def classify_early_warning_priority(
    prediction_level,
    confidence_level,
    recent_activity_change,
    prediction_direction
):
    """
    Creates an early-warning priority.

    This is more informative than a simple True/False flag.

    Possible values:

        CRITICAL
        HIGH
        MEDIUM
        LOW
        NONE
    """

    if confidence_level == "LOW":
        return "NONE"

    if prediction_level == "CRITICAL":

        if confidence_level == "HIGH":
            return "CRITICAL"

        return "HIGH"

    if prediction_level == "HIGH":

        if (
            confidence_level == "HIGH"
            and recent_activity_change is not None
            and recent_activity_change >= RECENT_ACTIVITY_WARNING_THRESHOLD
        ):
            return "HIGH"

        return "MEDIUM"

    if (
        prediction_level == "MEDIUM"
        and prediction_direction == "INCREASING"
    ):
        return "MEDIUM"

    if prediction_level == "LOW":
        return "LOW"

    return "NONE"


# ============================================================
# EARLY WARNING BOOLEAN
# ============================================================

def calculate_early_warning(
    early_warning_priority
):
    """
    Converts priority into a simple True / False flag
    for dashboards that need a boolean alert.
    """

    return early_warning_priority in (
        "CRITICAL",
        "HIGH",
        "MEDIUM"
    )


# ============================================================
# EXPLAINABLE PREDICTION REASONS
# ============================================================

def build_prediction_reasons(
    historical_average,
    recent_average,
    recent_activity_change,
    predicted_weekly_average,
    predicted_increase_percentage,
    direction,
    level,
    confidence,
    trend_metrics,
    hotspot_context
):
    """
    Generates human-readable reasons explaining WHY
    the prediction engine produced its result.

    This is important for an intelligence platform because
    investigators should not see a prediction score without
    understanding the evidence behind it.
    """

    reasons = []

    # --------------------------------------------------------
    # Recent activity
    # --------------------------------------------------------

    if (
        recent_activity_change is not None
        and recent_activity_change >= RECENT_ACTIVITY_WARNING_THRESHOLD
    ):

        reasons.append(
            f"Recent crime activity is "
            f"{recent_activity_change}% above the historical average."
        )

    elif (
        recent_activity_change is not None
        and recent_activity_change <= -RECENT_ACTIVITY_WARNING_THRESHOLD
    ):

        reasons.append(
            f"Recent crime activity is "
            f"{abs(recent_activity_change)}% below the historical average."
        )

    # --------------------------------------------------------
    # Future prediction
    # --------------------------------------------------------

    if (
        predicted_increase_percentage is not None
        and predicted_increase_percentage > STABLE_BAND_PERCENTAGE
    ):

        reasons.append(
            f"Crime activity is predicted to increase by "
            f"{predicted_increase_percentage}% compared with the "
            f"historical average."
        )

    elif (
        predicted_increase_percentage is not None
        and predicted_increase_percentage < -STABLE_BAND_PERCENTAGE
    ):

        reasons.append(
            f"Crime activity is predicted to decrease by "
            f"{abs(predicted_increase_percentage)}% compared with "
            f"the historical average."
        )

    # --------------------------------------------------------
    # Trend
    # --------------------------------------------------------

    if trend_metrics["status"] == "OK":

        if trend_metrics["slope"] > 0:

            if trend_metrics["significant"]:

                reasons.append(
                    "The long-term crime trend is increasing "
                    "and statistically significant."
                )

            else:

                reasons.append(
                    "The long-term crime trend is increasing, "
                    "but the trend is not statistically significant."
                )

        elif trend_metrics["slope"] < 0:

            reasons.append(
                "The long-term crime trend is decreasing."
            )

        else:

            reasons.append(
                "The long-term crime trend is relatively stable."
            )

    # --------------------------------------------------------
    # Hotspot
    # --------------------------------------------------------

    if hotspot_context:

        reasons.append(
            f"{len(hotspot_context)} related crime hotspot(s) "
            f"were detected in the district."
        )

    # --------------------------------------------------------
    # Confidence
    # --------------------------------------------------------

    if confidence["level"] == "HIGH":

        reasons.append(
            "The prediction is supported by a strong historical data record."
        )

    elif confidence["level"] == "MEDIUM":

        reasons.append(
            "The prediction has moderate confidence based on available historical data."
        )

    else:

        reasons.append(
            "The prediction has low confidence because historical data is limited."
        )

    return reasons


# ============================================================
# HOTSPOT CONTEXT
# ============================================================

def attach_hotspot_context(
    district_id,
    crime_major_head_id,
    hotspots
):
    """
    Matches hotspot information to the district and crime type.

    NOTE:
        If hotspot.py is later upgraded to include unit_id,
        this function can be made station-specific.

    Current matching:
        district + crime type
    """

    if not hotspots:
        return []

    return [

        {
            "hotspot_id": h.get("hotspot_id"),
            "case_count": h.get("case_count"),
            "hotspot_level": h.get("hotspot_level"),
            "peak_time": h.get("peak_time"),
        }

        for h in hotspots

        if (
            h.get("district_id") == district_id
            and h.get("crime_major_head_id") == crime_major_head_id
        )

    ]


# ============================================================
# GROUP CASES
# ============================================================

def build_cases_by_group(cases):

    cases_by_group = defaultdict(list)

    for case in cases:

        key = (
            case.get("district_id"),
            case.get("unit_id"),
            case.get("crime_major_head_id")
        )

        cases_by_group[key].append(case)

    return cases_by_group


# ============================================================
# MAIN PREDICTION REPORT
# ============================================================

def build_prediction_report(
    cases,
    hotspots=None,
    weeks_ahead=PREDICTION_WEEKS_AHEAD
):
    """
    Builds one prediction record per:

        District
        +
        Police Station
        +
        Crime Type
    """

    weekly_series = build_weekly_series(cases)

    if not weekly_series:
        return []

    cases_by_group = build_cases_by_group(cases)

    report = []

    for group_key, weekly_data in weekly_series.items():

        (
            district_id,
            unit_id,
            crime_major_head_id
        ) = group_key

        weekly_counts = [
            item["count"]
            for item in weekly_data
        ]

        weekly_count_total = len(weekly_counts)

        historical_case_count = len(
            cases_by_group.get(group_key, [])
        )

        # ----------------------------------------------------
        # INSUFFICIENT DATA
        # ----------------------------------------------------

        if weekly_count_total < MIN_WEEKS_FOR_PREDICTION:

            report.append({

                "district_id": district_id,

                "unit_id": unit_id,

                "crime_major_head_id":
                    crime_major_head_id,

                "historical_case_count":
                    historical_case_count,

                "analysis_status":
                    "INSUFFICIENT_DATA",

                "prediction_level":
                    "UNKNOWN",

                "confidence_level":
                    "LOW",

                "early_warning":
                    False,

                "early_warning_priority":
                    "NONE",

                "message":
                    (
                        f"Need at least "
                        f"{MIN_WEEKS_FOR_PREDICTION} weeks "
                        f"of data for this station/crime "
                        f"combination to produce a reliable "
                        f"prediction."
                    )

            })

            continue

        # ----------------------------------------------------
        # TREND
        # ----------------------------------------------------

        trend_metrics = calculate_linear_trend(
            weekly_counts
        )

        # ----------------------------------------------------
        # HISTORICAL AVERAGE
        # ----------------------------------------------------

        historical_average = (
            calculate_historical_average(
                weekly_counts
            )
        )

        # ----------------------------------------------------
        # RECENT ACTIVITY
        # ----------------------------------------------------

        recent_average = (
            calculate_recent_average(
                weekly_counts,
                RECENT_WEEKS
            )
        )

        recent_activity_change = (
            calculate_recent_activity_change(
                historical_average,
                recent_average
            )
        )

        # ----------------------------------------------------
        # FUTURE PREDICTION
        # ----------------------------------------------------

        predicted_weekly_counts = (
            forecast_future_weekly_counts(
                trend_metrics,
                weekly_counts,
                weeks_ahead
            )
        )

        predicted_total = (

            round(
                sum(predicted_weekly_counts),
                2
            )

            if predicted_weekly_counts
            else None

        )

        predicted_weekly_average = (

            round(
                predicted_total / weeks_ahead,
                2
            )

            if predicted_total is not None
            else None

        )

        # ----------------------------------------------------
        # PREDICTED CHANGE
        # ----------------------------------------------------

        predicted_increase_percentage = (
            calculate_predicted_increase(
                historical_average,
                predicted_weekly_average
            )
        )

        # ----------------------------------------------------
        # DIRECTION
        # ----------------------------------------------------

        direction = (
            classify_prediction_direction(
                trend_metrics,
                predicted_increase_percentage
            )
        )

        # ----------------------------------------------------
        # LEVEL
        # ----------------------------------------------------

        level = (
            classify_prediction_level(
                predicted_weekly_average,
                historical_average,
                predicted_increase_percentage
            )
        )

        # ----------------------------------------------------
        # CONFIDENCE
        # ----------------------------------------------------

        confidence = (
            calculate_prediction_confidence(
                weekly_count_total,
                trend_metrics
            )
        )

        # ----------------------------------------------------
        # HOTSPOT CONTEXT
        # ----------------------------------------------------

        hotspot_context = (
            attach_hotspot_context(
                district_id,
                crime_major_head_id,
                hotspots
            )
        )

        # ----------------------------------------------------
        # EARLY WARNING PRIORITY
        # ----------------------------------------------------

        early_warning_priority = (
            classify_early_warning_priority(
                prediction_level=level,
                confidence_level=confidence["level"],
                recent_activity_change=recent_activity_change,
                prediction_direction=direction
            )
        )

        early_warning = (
            calculate_early_warning(
                early_warning_priority
            )
        )

        # ----------------------------------------------------
        # EXPLAINABLE REASONS
        # ----------------------------------------------------

        prediction_reasons = (
            build_prediction_reasons(
                historical_average=
                    historical_average,

                recent_average=
                    recent_average,

                recent_activity_change=
                    recent_activity_change,

                predicted_weekly_average=
                    predicted_weekly_average,

                predicted_increase_percentage=
                    predicted_increase_percentage,

                direction=
                    direction,

                level=
                    level,

                confidence=
                    confidence,

                trend_metrics=
                    trend_metrics,

                hotspot_context=
                    hotspot_context
            )
        )

        # ----------------------------------------------------
        # FINAL OUTPUT
        # ----------------------------------------------------

        report.append({

            # ----------------------------------------------
            # IDENTIFICATION
            # ----------------------------------------------

            "district_id":
                district_id,

            "unit_id":
                unit_id,

            "crime_major_head_id":
                crime_major_head_id,

            # ----------------------------------------------
            # HISTORICAL DATA
            # ----------------------------------------------

            "historical_case_count":
                historical_case_count,

            "historical_weekly_average":
                historical_average,

            # ----------------------------------------------
            # RECENT ACTIVITY
            # ----------------------------------------------

            "recent_weeks_analyzed":
                min(
                    RECENT_WEEKS,
                    weekly_count_total
                ),

            "recent_weekly_average":
                recent_average,

            "recent_vs_historical_percentage":
                recent_activity_change,

            # ----------------------------------------------
            # FUTURE PREDICTION
            # ----------------------------------------------

            "predicted_weekly_breakdown":
                predicted_weekly_counts,

            "predicted_next_n_weeks":
                predicted_total,

            "predicted_weekly_average":
                predicted_weekly_average,

            # ----------------------------------------------
            # PREDICTION RESULT
            # ----------------------------------------------

            "prediction_direction":
                direction,

            "predicted_increase_percentage":
                predicted_increase_percentage,

            "prediction_level":
                level,

            # ----------------------------------------------
            # CONFIDENCE
            # ----------------------------------------------

            "confidence_level":
                confidence["level"],

            "confidence_score":
                confidence["score"],

            # ----------------------------------------------
            # EARLY WARNING
            # ----------------------------------------------

            "early_warning":
                early_warning,

            "early_warning_priority":
                early_warning_priority,

            # ----------------------------------------------
            # EXPLAINABILITY
            # ----------------------------------------------

            "prediction_reasons":
                prediction_reasons,

            # ----------------------------------------------
            # TREND INFORMATION
            # ----------------------------------------------

            "trend_slope":
                round(
                    trend_metrics.get(
                        "slope",
                        0.0
                    ),
                    3
                ),

            "trend_significant":
                trend_metrics.get(
                    "significant",
                    False
                ),

            # ----------------------------------------------
            # HOTSPOT
            # ----------------------------------------------

            "district_hotspots":
                hotspot_context,

            # ----------------------------------------------
            # STATUS
            # ----------------------------------------------

            "analysis_status":
                "SUCCESS"

        })

    # Highest early-warning priority first.
    priority_order = {

        "CRITICAL": 5,

        "HIGH": 4,

        "MEDIUM": 3,

        "LOW": 2,

        "NONE": 1

    }

    return sorted(

        report,

        key=lambda row: (

            priority_order.get(
                row.get(
                    "early_warning_priority",
                    "NONE"
                ),
                0
            ),

            row.get(
                "predicted_next_n_weeks"
            )
            if row.get(
                "predicted_next_n_weeks"
            ) is not None
            else -1

        ),

        reverse=True

    )


# # ============================================================
# # DEMO
# # ============================================================

# if __name__ == "__main__":

#     import json

#     cases = []

#     case_id = 1

#     # ========================================================
#     # STATION 101
#     # Increasing theft trend
#     # ========================================================

#     weekly_counts_101 = [
#         3, 4, 5, 6,
#         8, 9, 10, 12
#     ]

#     for week_index, count in enumerate(
#         weekly_counts_101
#     ):

#         for _ in range(count):

#             day = (
#                 week_index * 7
#                 + 1
#             )

#             date_str = (
#                 f"2026-"
#                 f"{1 + day // 28:02d}-"
#                 f"{1 + day % 28:02d}"
#             )

#             cases.append({

#                 "case_id":
#                     case_id,

#                 "district_id":
#                     1,

#                 "unit_id":
#                     101,

#                 "crime_major_head_id":
#                     1,

#                 "crime_registered_date":
#                     date_str

#             })

#             case_id += 1

#     # ========================================================
#     # STATION 102
#     # Stable theft trend
#     # ========================================================

#     weekly_counts_102 = [
#         10, 9, 10, 9,
#         10, 11, 9, 10
#     ]

#     for week_index, count in enumerate(
#         weekly_counts_102
#     ):

#         for _ in range(count):

#             day = (
#                 week_index * 7
#                 + 2
#             )

#             date_str = (
#                 f"2026-"
#                 f"{1 + day // 28:02d}-"
#                 f"{1 + day % 28:02d}"
#             )

#             cases.append({

#                 "case_id":
#                     case_id,

#                 "district_id":
#                     1,

#                 "unit_id":
#                     102,

#                 "crime_major_head_id":
#                     1,

#                 "crime_registered_date":
#                     date_str

#             })

#             case_id += 1

#     # ========================================================
#     # STATION 103
#     # Decreasing crime trend
#     # ========================================================

#     weekly_counts_103 = [
#         15, 13, 12, 11,
#         9, 8, 7, 5
#     ]

#     for week_index, count in enumerate(
#         weekly_counts_103
#     ):

#         for _ in range(count):

#             day = (
#                 week_index * 7
#                 + 3
#             )

#             date_str = (
#                 f"2026-"
#                 f"{1 + day // 28:02d}-"
#                 f"{1 + day % 28:02d}"
#             )

#             cases.append({

#                 "case_id":
#                     case_id,

#                 "district_id":
#                     2,

#                 "unit_id":
#                     103,

#                 "crime_major_head_id":
#                     2,

#                 "crime_registered_date":
#                     date_str

#             })

#             case_id += 1

#     # ========================================================
#     # STATION 104
#     # Insufficient history
#     # ========================================================

#     for week_index, count in enumerate(
#         [2, 3, 2]
#     ):

#         for _ in range(count):

#             day = (
#                 week_index * 7
#                 + 4
#             )

#             date_str = (
#                 f"2026-"
#                 f"{1 + day // 28:02d}-"
#                 f"{1 + day % 28:02d}"
#             )

#             cases.append({

#                 "case_id":
#                     case_id,

#                 "district_id":
#                     1,

#                 "unit_id":
#                     104,

#                 "crime_major_head_id":
#                     1,

#                 "crime_registered_date":
#                     date_str

#             })

#             case_id += 1

#     # ========================================================
#     # SAMPLE HOTSPOT
#     # ========================================================

#     sample_hotspots = [

#         {

#             "hotspot_id":
#                 1,

#             "district_id":
#                 1,

#             "crime_major_head_id":
#                 1,

#             "case_count":
#                 30,

#             "hotspot_level":
#                 "HIGH",

#             "peak_time":
#                 "EVENING"

#         }

#     ]

#     # ========================================================
#     # BUILD REPORT
#     # ========================================================

#     report = build_prediction_report(

#         cases,

#         hotspots=
#             sample_hotspots,

#         weeks_ahead=
#             4

#     )

#     print(
#         json.dumps(
#             report,
#             indent=2
#         )
#     )
