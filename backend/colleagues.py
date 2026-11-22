"""Bounded contemporaneous-employment check; only publishes an aggregate."""
from datetime import date


def _bounds(profile, company_id):
    positions = (profile.get("experience") or {}).get("employment_details") or {}
    for role in (positions.get("current") or []) + (positions.get("past") or []):
        if role.get("crustdata_company_id") != company_id:
            continue
        try:
            start = date.fromisoformat(role["start_date"][:10])
            # A position with no dated endpoint supports its start as a point.
            end = date.fromisoformat((role.get("end_date") or role["start_date"])[:10])
        except (ValueError, TypeError, KeyError):
            continue
        if start <= end <= date.today():
            yield start, end


def overlap_count(person_data, search_data, company_id):
    pid = person_data.get("crustdata_person_id")
    if not pid:
        return None
    reference = list(_bounds(person_data, company_id))
    if not reference:
        return None
    overlaps = set()
    for colleague in search_data.get("profiles", []):
        other = colleague.get("crustdata_person_id")
        if not other or other == pid:
            continue
        if any(max(a, x) <= min(b, y) for a, b in reference
               for x, y in _bounds(colleague, company_id)):
            overlaps.add(other)
    return len(overlaps)
