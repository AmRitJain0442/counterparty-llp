"""Define a falsifiable prospective question from a recent interim appointment and issuer filing."""
import re
from datetime import date, timedelta


def forecast_window(cid, enriched, cards, today):
    filings = [c for c in cards if c.get("label") == "8-K Item 5.02" and c.get("source") == "sec"
               and c.get("status") == "ok" and c.get("observed_on")]
    if not filings:
        return None
    filed = date.fromisoformat(filings[0]["observed_on"])
    if not timedelta(0) <= today - filed <= timedelta(days=120):
        return None
    for officer in (enriched.get("people") or {}).get("cxos") or []:
        positions = (officer.get("experience") or {}).get("employment_details") or {}
        for job in positions.get("current") or []:
            title = str(job.get("employee_title") or job.get("title") or "").lower()
            if not (re.search(r"\b(interim|acting)\b", title) and re.search(r"\bcfo\b|chief financial officer", title)):
                continue
            if str(job.get("employer_company_id") or job.get("crustdata_company_id")) != str(cid):
                continue
            try:
                start = date.fromisoformat(str(job.get("employee_start_date") or job.get("start_date"))[:10])
                refreshed = date.fromisoformat(str((officer.get("basic_profile") or {}).get("last_updated"))[:10])
            except ValueError:
                continue
            if not (start <= today and abs((start - filed).days) <= 45
                    and timedelta(0) <= today - refreshed <= timedelta(days=60)):
                continue
            deadline = today + timedelta(days=180)
            return {"due":str(deadline), "observed_on":str(start), "filing_on":str(filed),
                    "prediction":f"By {deadline}, the issuer will publicly report a permanent principal financial officer.",
                    "resolution":"Check filings submitted after the forecast date and by its deadline for a permanent appointment."}
    return None
