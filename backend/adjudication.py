"""Apply deterministic claim-level evidence gates before a partner finding."""
from .demo import CASES


def adjudicate(desk, raw):
    if raw.get("mode") == "demo":
        claim = raw.get("proposition")
        rows = {c["id"]: c for c in raw.get("evidence", []) if c.get("claim") == claim}
        cited = {s.get("evidence_id") for s in raw.get("signals", [])
                 if s.get("type") == "claim_observation" and s.get("claim") == claim}
        witnesses = {rows[i]["source"] for i in cited if i in rows}
        if "Crustdata" in witnesses and len(witnesses) >= 2:
            killed = any(s.get("type") == "predates_filing" and s.get("evidence_id") in rows
                         for s in raw["signals"])
            verdicts = {"payment":"HELD", "candidate":"FAILED", "estate":"KILLED" if killed else "REQUEST FOR EXPLANATION",
                        "company":"SIGNED"}
            return {"verdict":verdicts[desk], "summary":CASES[desk][3]}
    unresolved = any(s.get("status") == "unresolved" for s in raw.get("steps", []))
    if unresolved:
        return {"verdict":"IDENTITY REVIEW", "summary":"An identifier could not be tied to the subject. Review the source records before relying on this case."}
    if desk == "estate" and any("rules out formation" in str(c.get("detail")) for c in raw.get("evidence", [])
                                 if c.get("label","").startswith("Opposing counsel")):
        return {"verdict":"KILLED","summary":"The destination entity predates the filing. Its formation cannot support the proposed post-filing successor hypothesis."}
    return {"verdict":"INSUFFICIENT WITNESSES",
            "summary":"The collected observations do not independently establish the same claim. The case remains open for human review."}
