"""Apply deterministic claim-level evidence gates before a partner finding."""


def adjudicate(desk, raw):
    claim = raw.get("proposition")
    if desk == "payment" and claim:
        cited = {s.get("evidence_id") for s in raw.get("signals", []) if
                 s.get("type") == "claim_observation" and s.get("claim") == claim}
        sources = {c.get("source") for c in raw.get("evidence", []) if
                   c.get("id") in cited and c.get("claim") == claim
                   and c.get("label") == "Vendor domain cross-check" and c.get("mode") == "LIVE"}
        if sources >= {"Crustdata", "Brønnøysund"}:
            return {"verdict": "HELD", "summary": claim + " Confirm the request by calling the number on file."}
    if desk == "company" and raw.get("forecast"):
        return {"verdict": "FORECAST FOR REVIEW", "summary": raw["forecast"]["prediction"]}
    unresolved = any(s.get("status") == "unresolved" for s in raw.get("steps", []))
    if unresolved:
        return {"verdict":"IDENTITY REVIEW", "summary":"An identifier could not be tied to the subject. Review the source records before relying on this case."}
    if desk == "estate" and any("rules out formation" in str(c.get("detail")) for c in raw.get("evidence", [])
                                 if c.get("label","").startswith("Opposing counsel")):
        return {"verdict":"KILLED","summary":"The destination entity predates the filing. Its formation cannot support the proposed post-filing successor hypothesis."}
    return {"verdict":"INSUFFICIENT WITNESSES",
            "summary":"The collected observations do not independently establish the same claim. The case remains open for human review."}
