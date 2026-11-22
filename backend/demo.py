"""Curated synthetic cases for the four-desk stage rehearsal."""

DAY = "2026-11-22"
CASES = {
    "payment": ("North Quay Instruments", "vendor authority", [
        ("Crustdata", "Next appointment", "The simulated contact started at another employer on 2026-08-03."),
        ("Vendor register", "Revoked payment authority", "The independent supplier register records revocation of this contact's mandate on 2026-08-03."),
        ("RDAP", "Sending domain", "The simulated sending domain was registered eleven days before intake."),
        ("IFSC", "Receiving branch", "The new branch differs from the verified vendor-master entry.")
    ], "Hold the requested bank change for a callback using the vendor-master number."),
    "candidate": ("Meridian Engineering · synthetic CV", "engineering headcount in Q2", [
        ("Crustdata", "Quarterly engineering cohort", "The reconstructed engineering headcount is 11 for Q2 2025."),
        ("Employer attestation", "Dated staffing return", "The synthetic signed quarterly return lists eleven engineers within the claimed reporting unit."),
        ("Consented CV", "Claim under review", "The candidate claims direct responsibility for 40 engineers in the same unit and quarter.")
    ], "The 40-engineer claim fails corroboration for this unit and quarter. Invite the candidate to explain its scope."),
    "estate": ("Sundvik Marine AS · synthetic estate", "new successor after filing", [
        ("Crustdata", "Former employee destinations", "The reconstruction follows 84 distinct profiles. Publishable cohorts moved to three employers."),
        ("Registry", "Pre-existing parent", "The top destination was incorporated in 2011 and was registered as the solvent parent before the 2024 filing."),
        ("Registry", "Statutory board overlap", "An officer served on both boards before the filing.")
    ], "Opposing counsel killed the new-successor hypothesis. The parent company predates the filing and the appointments."),
    "company": ("Aster Transit plc · synthetic issuer", "finance transition review", [
        ("Crustdata", "Finance leadership transition", "A dated finance leadership change appears in the reconstructed workforce record."),
        ("EDGAR", "Officer-change filing", "A synthetic Item 5.02 filing independently records the same transition."),
        ("Watch replay", "Earlier watch observation", "A replayed observation places the profile movement before the simulated filing.")
    ], "Rehearsal forecast: check the next quarterly filing for a permanent finance appointment. The demo receipt is local.")
}


def build_demo(desk):
    name, claim, rows, explanation = CASES[desk]
    cards = [{"id": f"exhibit-{i+1}", "source": source, "label": label, "detail": detail,
              "as_of": DAY, "mode": "REPLAY" if source == "Watch replay" else "DEMO", "url": None,
              "claim": claim if i < 2 else None} for i, (source, label, detail) in enumerate(rows)]
    signals = [{"type": "claim_observation", "evidence_id": row["id"], "claim": claim} for row in cards[:2]]
    if desk == "estate":
        signals.append({"type":"predates_filing", "evidence_id":"exhibit-2"})
    flows = [{"from":name,"to":dest,"count":n} for dest,n in (
        ("Sundvik Holding",32),("Fjord Service",19),("Kyst Engineering",15),("Unknown or suppressed",18)
    )] if desk == "estate" else []
    return {"subject":name, "mode":"demo", "as_of":DAY, "evidence":cards, "signals":signals,
            "steps":[{"name":stage,"status":"complete","detail":note} for stage,note in [
                ("Identity", "Synthetic identities resolved for this exhibit."),
                ("Evidence desk", f"{len(cards)} dated exhibits examined."),
                ("Opposing counsel", explanation), ("Partner review","Filed for human review.")]],
            "credits":0,"flows":flows,"proposition":claim}
