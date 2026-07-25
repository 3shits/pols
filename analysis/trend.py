from datetime import datetime, timedelta

def get_week(date_str):
    d = datetime.strptime(date_str, "%Y-%m-%d")
    year, week, _ = d.isocalendar()
    return str(year) + "-W" + str(week)

def get_month(date_str):
    d = datetime.strptime(date_str, "%Y-%m-%d")
    return str(d.year) + "-" + str(d.month).zfill(2) 
 

def get_year(date_str):
    d = datetime.strptime(date_str, "%Y-%m-%d")
    return str(d.year)


# how many cases happened per district+crime+day
def count_cases_per_day(cases):
    counts = {}
    for c in cases:
        day = c["crime_registered_date"]
        key = (c["district_id"], c["crime_major_head_id"], day)
        if key not in counts:
            counts[key] = 0
        counts[key] = counts[key] + 1
    return counts
 
 
# how many cases happened per district+crime+week
def count_cases_per_week(cases):
    counts = {}
    for c in cases:
        week = get_week(c["crime_registered_date"])
        key = (c["district_id"], c["crime_major_head_id"], week)
        if key not in counts:
            counts[key] = 0
        counts[key] = counts[key] + 1
    return counts
 
def count_cases_per_month(cases):
    counts = {}
    for c in cases:
        month = get_month(c["crime_registered_date"])
        key = (c["district_id"], c["crime_major_head_id"], month)
        if key not in counts:
            counts[key] = 0
        counts[key] = counts[key] + 1
    return counts
 
 
# how many cases happened per district+crime+year
def count_cases_per_year(cases):
    counts = {}
    for c in cases:
        year = get_year(c["crime_registered_date"])
        key = (c["district_id"], c["crime_major_head_id"], year)
        if key not in counts:
            counts[key] = 0
        counts[key] = counts[key] + 1
    return counts


def get_all_weeks(start_date,end_date):
    start_date = (
        start_date
        - timedelta(
            days=start_date.weekday()
        )
    )
    weeks = []
    current_date = start_date
    while current_date <= end_date:
        year, week, _ = (
            current_date.isocalendar()
        )
        weeks.append(
            str(year) + "-W" + str(week)
        )
        current_date += timedelta(
            weeks=1
        )
    return weeks


def get_mean(numbers):
    total = 0
    for n in numbers:
        total = total + n
    return total / len(numbers)

# std dev
def get_stdev(numbers):
    mean = get_mean(numbers)
    squared_diffs = []
    for n in numbers:
        diff = n - mean
        squared_diffs.append(diff * diff)
    variance = get_mean(squared_diffs)
    stdev = variance ** 0.5  
    return stdev

# percentage change from one period to the next
def percentage_change(numbers):
    changes = []
    for i in range(len(numbers)):
        if i == 0:
            changes.append(None)  # no previous period to compare to
            continue
        previous = numbers[i - 1]
        current = numbers[i]
        if previous == 0:
            changes.append(None)  
            continue
        change = ((current - previous) / previous) * 100
        changes.append(round(change, 1))
    return changes

def moving_average(numbers, window=3):
    averages = []
    for i in range(len(numbers)):
        if i < window - 1:
            averages.append(None)  
            continue
        chunk = numbers[i - window + 1: i + 1]
        averages.append(round(get_mean(chunk), 2))
    return averages
 
def build_weekly_series(cases):
    if not cases:
        return {}
    # Convert all dates
    dates = []
    for c in cases:
        date = datetime.strptime(
            c["crime_registered_date"],
            "%Y-%m-%d"
        )
        dates.append(date)
    # Find date range
    start_date = min(dates)
    end_date = max(dates)
    # Generate all weeks
    all_weeks = get_all_weeks(
        start_date,
        end_date
    )
    # Get actual weekly counts
    counts = count_cases_per_week(
        cases
    )
    # Find every District + Crime combination
    combinations = set()
    for c in cases:
        combinations.add(
            (
                c["district_id"],
                c["crime_major_head_id"]
            )
        )
    # Build complete time series
    result = {}
    for district_id, crime_id in combinations:
        group_key = (
            district_id,
            crime_id
        )
        result[group_key] = []
        for week in all_weeks:
            key = (
                district_id,
                crime_id,
                week
            )
            count = counts.get(
                key,
                0
            )
            result[group_key].append(
                {
                    "week": week,
                    "count": count
                }
            )
    return result 
# seasonal patterns - average case count per calendar month

def seasonal_patterns(cases):
    month_counts = {}  
 
    monthly = count_cases_per_month(cases)  
 
    for key, count in monthly.items():
        year_month = key[2]        
        month_only = year_month.split("-")[1]  
 
        if month_only not in month_counts:
            month_counts[month_only] = []
        month_counts[month_only].append(count)
 
    seasonal = {}
    for month_only, counts in month_counts.items():
        seasonal[month_only] = round(get_mean(counts), 2)
 
    return seasonal

def rolling_zscore(numbers, window=4):
    z_scores = []
 
    for i in range(len(numbers)):
        history = numbers[max(0, i - window): i]  
 
        if len(history) < window:
            z_scores.append(None)  
            continue
 
        mean = get_mean(history)
        stdev = get_stdev(history)
        if stdev == 0:
            stdev = 0.000001  
 
        z = (numbers[i] - mean) / stdev
        z_scores.append(round(z, 2))
 
    return z_scores
 
def get_spike_severity(z_score):
    if z_score is None:
        return "UNKNOWN"
    if z_score >= 3:
        return "HIGH"
    if z_score >= 2:
        return "MEDIUM"
    return "NORMAL"


def find_rolling_spikes(cases,window=8,z_threshold=2.0):
    # Build complete weekly series
    weekly_series = (
        build_weekly_series(
            cases
        )
    )
    spikes = []
    # Process each District + Crime
    for group_key, weekly_data in (
        weekly_series.items()
    ):
        district_id = group_key[0]
        crime_id = group_key[1]
        # Extract weekly counts
        numbers = [
            item["count"]
            for item in weekly_data
        ]
        # Calculate rolling Z-scores
        z_scores = rolling_zscore(
            numbers,
            window
        )
        # Check every week
        for i in range(
            len(weekly_data)
        ):
            z = z_scores[i]
            # No valid Z-score yet
            if z is None:
                continue
            # Detect spike
            if z >= z_threshold:
                spikes.append(
                    {
                        "district_id":
                            district_id,
                        "crime_major_head_id":
                            crime_id,
                        "week":
                            weekly_data[i]["week"],
                        "case_count":
                            weekly_data[i]["count"],
                        "z_score":z,
                        "severity":
                            get_spike_severity(z)
                    }
                )
    return spikes
 
def find_spikes(cases, z_threshold=2.0):
    counts = count_cases_per_week(cases)
    grouped = {}
    for key, count in counts.items():
        district_id = key[0]
        crime_id = key[1]
        week = key[2]
        group_key = (district_id, crime_id)
        if group_key not in grouped:
            grouped[group_key] = []
        grouped[group_key].append((week, count))
 
    spikes = []
    for group_key, weekly_data in grouped.items():
        numbers = []
        for week, count in weekly_data:
            numbers.append(count)
        mean = get_mean(numbers)
        stdev = get_stdev(numbers)
        if stdev == 0:
            continue
        for week, count in weekly_data:
            z_score = (count - mean) / stdev
            if z_score >= z_threshold:
                spikes.append({
                    "district_id": group_key[0],
                    "crime_major_head_id": group_key[1],
                    "week": week,
                    "case_count": count,
                    "mean": mean,
                    "stdev": stdev,
                    "z_score": z_score,
                    "severity": get_spike_severity(z_score)
                })
    return spikes


test_cases = [
    {"district_id": 1, "crime_major_head_id": 1, "crime_registered_date": "2026-01-05"},
    {"district_id": 1, "crime_major_head_id": 1, "crime_registered_date": "2026-02-10"},
    {"district_id": 1, "crime_major_head_id": 1, "crime_registered_date": "2026-02-12"},
    {"district_id": 1, "crime_major_head_id": 1, "crime_registered_date": "2026-03-01"},
    {"district_id": 1, "crime_major_head_id": 1, "crime_registered_date": "2026-06-01"},
    {"district_id": 1, "crime_major_head_id": 1, "crime_registered_date": "2026-06-02"},
    {"district_id": 1, "crime_major_head_id": 1, "crime_registered_date": "2026-06-08"},
    {"district_id": 1, "crime_major_head_id": 1, "crime_registered_date": "2026-06-15"},
    {"district_id": 1, "crime_major_head_id": 1, "crime_registered_date": "2026-06-22"},
    {"district_id": 1, "crime_major_head_id": 1, "crime_registered_date": "2026-06-22"},
    {"district_id": 1, "crime_major_head_id": 1, "crime_registered_date": "2026-06-22"},
    {"district_id": 1, "crime_major_head_id": 1, "crime_registered_date": "2026-06-22"},
    {"district_id": 1, "crime_major_head_id": 1, "crime_registered_date": "2026-06-22"},
]

print("--- daily counts ---")
for key, count in count_cases_per_day(test_cases).items():
    print(key, "->", count)

print("\n--- weekly counts ---")
weekly = count_cases_per_week(test_cases)
for key, count in weekly.items():
    print(key, "->", count)

print("\n--- monthly counts ---")
for key, count in count_cases_per_month(test_cases).items():
    print(key, "->", count)

print("\n--- yearly counts ---")
for key, count in count_cases_per_year(test_cases).items():
    print(key, "->", count)

weekly_values = list(weekly.values())

print("\n--- percentage change (weekly counts, in order) ---")
print(percentage_change(weekly_values))

print("\n--- moving average (window=2) ---")
print(moving_average(weekly_values, window=2))

print("\n--- seasonal patterns (avg cases per calendar month) ---")
print(seasonal_patterns(test_cases))

print("\n--- build_weekly_series (fills in zero-count weeks) ---")
series = build_weekly_series(test_cases)
for group_key, data in series.items():
    print(group_key, data)

print("\n--- spikes (whole-series z-score) ---")
for row in find_spikes(test_cases):
    print(row)

print("\n--- spikes (rolling z-score, window=8) ---")
for row in find_rolling_spikes(test_cases, window=8):
    print(row)