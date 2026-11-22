# Technical reference

Counterparty serves its React frontend and FastAPI routes on the same origin. The public deployment uses Cloud Run and Firestore in Mumbai. The local launcher uses SQLite by default and writes to `.local/ledger.sqlite3`. Everyone using the same deployment shares its ledger.

## Live configuration

| Variable | Purpose |
| --- | --- |
| `CRUSTDATA_API_KEY` | Server-side Crustdata bearer token for collection |
| `GOOGLE_CLOUD_PROJECT` | Project billed for Gemini on Vertex AI |
| `GOOGLE_APPLICATION_CREDENTIALS` | Optional path to credentials outside the checkout. Application Default Credentials also support an attached service account. |
| `GOOGLE_CLOUD_LOCATION`, `VERTEX_MODEL` | Vertex AI location and model. Defaults are `global` and `gemini-2.5-flash`. |
| `SEC_USER_AGENT` | Organization name and contact email for SEC filing requests |
| `SQLITE_PATH` | Override for the local ledger path |

The Windows launcher can read a DPAPI-protected Crustdata token and an ADC path pointer from `%LOCALAPPDATA%\CounterpartyLLP`. To check an account’s endpoint access and pricing, set `CRUSTDATA_API_KEY` and run `python -m scripts.preflight` from the repository root. [Cloud storage and watch setup](../cloud/README.md) · [Infrastructure decisions](discussion/infrastructure.md)

## Investigation API

| Method | Route | Result |
| --- | --- | --- |
| POST | `/api/cases` | File a live investigation. The optional `mode` field accepts only `live`. |
| POST | `/api/cases/stream` | Stream progress as newline-delimited JSON, followed by the filed case |
| GET | `/api/swarms/{desk}` | Lead and specialist personas, assignments, ownership and dependencies |
| GET | `/api/cases` | Shared ledger in reverse creation order |
| GET | `/api/cases/{id}` | A case’s evidence, decision, reports, provider credits and receipt |
| GET | `/api/cases/{id}/receipt` | Verify the stored decision commitment |
| GET | `/api/capabilities` | Current Crustdata balance, prices and endpoint entitlements |
| GET | `/api/health` | Service health |
| GET | `/docs` | Interactive API schema |

## External services

| Service | Use | Access and cost |
| --- | --- | --- |
| [Crustdata](https://docs.crustdata.com/general/introduction) | Company and person identification, enrichment, workforce and job searches, configured watch history | Live requests use the configured account. Collection costs use the returned credit header when available. |
| [Google Cloud](https://cloud.google.com/vertex-ai/generative-ai/docs/start/quickstarts/quickstart-multimodal) | Gemini reviews on Vertex AI and hosted infrastructure | Billed to the configured GCP project |
| [Brønnøysund Register Centre](https://data.brreg.no/enhetsregisteret/api/docs/index.html) | Norwegian entities, bankruptcy status and statutory roles | Free open-data endpoints |
| [SEC EDGAR](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) | Company submissions and dated 8-K items | Free public data API with an identifying user agent |
| [RDAP registries](https://data.iana.org/rdap/dns.json) | Sender-domain registration dates for supported suffixes | Free public lookups subject to registry limits |
| [Razorpay IFSC](https://github.com/razorpay/ifsc) | Indian branch and bank metadata | Free public lookup |
| [GLEIF](https://www.gleif.org/en/lei-data/gleif-api) | Optional legal entity identifier lookup | Free public API |
| [crt.sh](https://crt.sh/), [Wayback CDX](https://github.com/internetarchive/wayback/tree/master/wayback-cdx-server), [OpenIBAN](https://openiban.com/) | Optional domain-history and bank-code adapters | Free public endpoints, subject to availability |
| [Sigstore Rekor](https://docs.sigstore.dev/logging/overview/) | Optional public timestamp for a case commitment | Free public transparency service. The default receipt is a local commitment. |

[Account rehearsal and observed limits](rehearsal.md) · [Privacy and human review](privacy.md) · [Design notes](discussion/design.md)
