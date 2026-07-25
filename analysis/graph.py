from itertools import combinations
from collections import defaultdict
import json


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


def build_person_case_relationships(accused):
    person_cases = defaultdict(set)

    for record in accused:
        if not is_valid_accused_record(record):
            continue

        person_id = record["person_id"]
        case_id = record["case_id"]

        person_cases[person_id].add(case_id)

    return dict(person_cases)


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

        for person_a, person_b in combinations(
            unique_persons,
            2
        ):
            associations[
                (person_a, person_b)
            ] += 1

    return dict(associations)


def classify_association(shared_cases):
    if shared_cases >= 5:
        return "STRONG"

    if shared_cases >= 3:
        return "MEDIUM"

    if shared_cases >= 1:
        return "WEAK"

    return "NONE"


def find_person_locations(accused, cases):
    case_to_location = {}

    for case in cases:
        case_id = case.get("case_id")
        location_id = case.get("location_id")

        if (
            case_id is not None
            and location_id is not None
        ):
            case_to_location[case_id] = location_id

    person_cases = defaultdict(set)

    for record in accused:
        if not is_valid_accused_record(record):
            continue

        person_id = record["person_id"]
        case_id = record["case_id"]

        person_cases[person_id].add(case_id)

    person_locations = defaultdict(
        lambda: defaultdict(int)
    )

    for person_id, case_ids in person_cases.items():
        for case_id in case_ids:
            location_id = case_to_location.get(case_id)

            if location_id is not None:
                person_locations[
                    person_id
                ][
                    location_id
                ] += 1

    return {
        person_id: dict(locations)
        for person_id, locations in person_locations.items()
    }


def build_relationship_report(
    accused,
    cases,
    repeat_threshold=3
):
    person_cases = build_person_case_relationships(
        accused
    )

    repeat_accused_records = find_repeat_accused(
        person_cases,
        repeat_threshold
    )

    repeat_accused = {
        record["person_id"]
        for record in repeat_accused_records
    }

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
            "person_id": person_b,
            "shared_cases": shared_cases,
            "association_strength": strength
        })

        associations_by_person[
            person_b
        ].append({
            "person_id": person_a,
            "shared_cases": shared_cases,
            "association_strength": strength
        })

    person_locations = find_person_locations(
        accused,
        cases
    )

    report = []

    for person_id, cases_set in person_cases.items():

        associated_persons = sorted(
            associations_by_person.get(
                person_id,
                []
            ),
            key=lambda association:
                -association["shared_cases"]
        )

        locations = person_locations.get(
            person_id,
            {}
        )

        frequent_locations = [
            {
                "location_id": location_id,
                "case_count": count
            }
            for location_id, count in sorted(
                locations.items(),
                key=lambda item: -item[1]
            )
        ]

        network_degree = len(
            associated_persons
        )

        report.append({
            "person_id": person_id,
            "repeat_accused": (
                person_id in repeat_accused
            ),
            "total_cases": len(cases_set),
            "network_degree": network_degree,
            "associated_persons": associated_persons,
            "frequent_locations": frequent_locations
        })

    return sorted(
        report,
        key=lambda person:
            -person["total_cases"]
    )


# if __name__ == "__main__":

#     cases = [
#         {"case_id": 1, "location_id": 10},
#         {"case_id": 2, "location_id": 10},
#         {"case_id": 3, "location_id": 20},
#         {"case_id": 4, "location_id": 10},
#         {"case_id": 5, "location_id": 10},
#         {"case_id": 6, "location_id": 30},
#         {"case_id": 7, "location_id": 10},
#         {"case_id": 8, "location_id": 20}
#     ]

#     accused = [
#         {"case_id": 1, "person_id": 101},
#         {"case_id": 1, "person_id": 102},
#         {"case_id": 2, "person_id": 101},
#         {"case_id": 2, "person_id": 102},
#         {"case_id": 3, "person_id": 101},
#         {"case_id": 4, "person_id": 101},
#         {"case_id": 4, "person_id": 102},
#         {"case_id": 5, "person_id": 101},
#         {"case_id": 5, "person_id": 102},
#         {"case_id": 6, "person_id": 103},
#         {"case_id": 7, "person_id": 101},
#         {"case_id": 8, "person_id": 103},
#         {"case_id": 8, "person_id": 102}
#     ]

#     report = build_relationship_report(
#         accused=accused,
#         cases=cases,
#         repeat_threshold=3
#     )

#     print(
#         json.dumps(
#             report,
#             indent=4
#         )
#     )