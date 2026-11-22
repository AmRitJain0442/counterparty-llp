from backend.adjudication import adjudicate
from backend.vendor import vendor_records


def test_payment_hold_requires_two_bound_sources():
    inputs = {"domain":"vendor.no", "sender_domain":"other.no", "orgnr":"123456789"}
    company = {"basic_info":{"name":"Example AS","primary_domain":"vendor.no"}}
    rows = [{"operation":"brreg", "status":"ok", "data":{"navn":"Example AS","organisasjonsnummer":"123456789",
             "hjemmeside":"https://vendor.no"},"as_of":"2026-11-21","source":"https://data.brreg.no"},
            {"operation":"company_identify","status":"ok","as_of":"2026-11-21","source":"https://api.crustdata.com"}]
    cards = vendor_records(inputs, company, rows)
    raw = {"mode":"live","evidence":cards,"proposition":cards[0]["claim"],
           "signals":[{"type":"claim_observation","claim":c["claim"],"evidence_id":c["id"]} for c in cards]}
    assert adjudicate("payment", raw)["verdict"] == "HELD"
    assert adjudicate("payment", {**raw,"evidence":cards[:1]})["verdict"] == "INSUFFICIENT WITNESSES"
    assert vendor_records({**inputs,"domain":"unrelated.no"}, company, rows) == []
