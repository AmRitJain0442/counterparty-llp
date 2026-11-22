# Live provider contract

`backend.providers.run_live(desk, subject, consent, inputs)` is synchronous and returns JSON-compatible `evidence`, `steps`, `credits`, `flows`, `signals`. Routing belongs to the caller.

Evidence records contain id, provider, operation, as_of (UTC retrieval time), status, data, and source URL. Retrieval time is not a historical observation date. Failed/missing/disabled providers are not negative evidence. Raw evidence is server-internal: redact personal names unless consented/statutory, always remove birth dates before display.

Signals are conservative facts about collection: `provider_unavailable`, `provider_failure`, `evidence_available`, `consent_required`. Each has provider, operation, evidence_id and status. They are NOT verdicts. The adjudication worker must resolve identities, extract dated employment transitions (next-employer start), mark stale profiles unknown, require two independent witnesses for adverse findings, enforce minimum cohort five and insufficient coverage below fifteen, and kill parent/successor/acqui-hire explanations. No automated legal effect. No inferred historical snapshots. `flows` is empty until dated, sufficiently sized cohorts can be established.

`credits` lists per-call actual X-Credits-Used or null (unknown, never zero inferred). Account price/balance responses remain evidence. Steps expose sanitized status, never tokens or upstream error bodies. Partial failures preserve successful evidence. No paid POST retry after ambiguous failure.

Inputs: `crustdata` maps supported operation names to exact API payloads; candidate person/verify calls require consent=True. Watch creation additionally requires `watch_scope` equal to subject and `watch_confirmed=True`, a 30-day payload SLA, and an explicit watch payload. No implicit watchers. Public inputs: orgnr, cik, domain, ifsc, iban, lei. Optional `summarize=True` uses Vertex and remains untrusted drafting, never another independent witness.

Credentials only from environment: CRUSTDATA_API_KEY, GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION, VERTEX_MODEL, GOOGLE_OAUTH_ACCESS_TOKEN (short-lived), SEC_USER_AGENT, GOOGLE_WEB_RISK_API_KEY. No credential files loaded by this module.

References: https://docs.crustdata.com/ ; https://docs.cloud.google.com/vertex-ai/generative-ai/docs/model-reference/inference ; https://data.brreg.no/enhetsregisteret/api/docs/index.html ; https://www.sec.gov/search-filings/edgar-application-programming-interfaces ; https://www.gleif.org/en/lei-data/gleif-api
