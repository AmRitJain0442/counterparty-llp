# Counterparty LLP

An evidence room for checking a payment request, an employment claim, a bankrupt estate or a listed company. Each desk collects dated observations, tests an alternative explanation and files a reviewable decision.

## Run locally

Use Python 3.12 and Node.js 22 or newer. From the repository root on Windows:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
Push-Location web
npm.cmd ci
npm.cmd run build
Pop-Location
.\scripts\start.ps1
```

Open **http://127.0.0.1:8080**. On macOS or Linux use `python3.12 -m venv .venv`, install the requirements with `.venv/bin/pip`, build the web app as above, and run `.venv/bin/python -m uvicorn backend.main:app --port 8080`. The production bundle and API share one origin.

**Demo** runs the four curated cases locally, with source labels and dates. **Live** spends credits on the configured Crustdata account and runs two Gemini analysts, two challengers and a review partner through Vertex AI. Each completed run creates a ledger entry. SQLite defaults to `.local/ledger.sqlite3`.

## Swarm map

The first screen combines a radial workflow and an inspector. Select a node to focus its incoming and outgoing handoffs, or use **Find** to locate an agent. The inspector opens beside the map on desktop and as a bottom sheet on phones. **Run** opens the current desk’s intake. **Trace** replays a filed investigation without calling providers.

Twelve workers handle each case. Seven do deterministic work such as indexing sources, checking dates and applying evidence rules. Five live Gemini reviewers run in three stages. Both analysts see the dated source cards. Both challengers receive both analyses, and the review partner receives both challenges. Each reviewer returns an assessment and source references. Missing reviews or requests for material evidence refer a proposed adverse finding or forecast to a human. A completed run seals the reports and their dependency events into the case receipt. Demo runs use curated evidence and local review logic.

## Credentials

| Variable | Use |
|---|---|
| CRUSTDATA_API_KEY | Server-side Crustdata bearer token |
| GOOGLE_CLOUD_PROJECT | Project billed for Gemini on Vertex AI |
| GOOGLE_APPLICATION_CREDENTIALS | Optional path to a service account outside the checkout. ADC also supports workload identity. |
| GOOGLE_CLOUD_LOCATION, VERTEX_MODEL | Defaults are global and gemini-2.5-flash. |
| SEC_USER_AGENT | Organization name and contact email for SEC filing requests |
| SQLITE_PATH | Optional local ledger path |

The Windows launcher also reads the current user's DPAPI-protected Crustdata token and ADC path pointer under LocalAppData/CounterpartyLLP. The current workstation has both configured. Run `python -m scripts.preflight` with the Crustdata environment variable set to inspect endpoint availability and pricing. The cloud adapter configuration is documented under [cloud](cloud/) and [infrastructure decisions](docs/discussion/infrastructure.md).

## Investigation interfaces

| Route | Result |
|---|---|
| POST /api/cases | File a demo or live investigation |
| POST /api/cases/stream | Same investigation with newline-delimited progress and a final case |
| GET /api/swarms/{desk} | Twelve named workers, their assignments and their dependencies |
| GET /api/cases | Ledger in reverse creation order |
| GET /api/cases/{id} | Stored evidence, decision, cost and receipt |
| GET /api/capabilities | Current account balance, prices and entitlements |
| GET /api/cases/{id}/receipt | Verify the stored decision commitment |
| GET /api/health | Service health |
| GET /docs | Interactive API schema |

Keep private ingress on hosted deployments. Everyone with application access shares one firm's ledger. The demo supports a synthetic candidate. A real candidate check requires consent and identifiers appropriate to the inquiry.

## External API inventory

| Service | Purpose | Access and costs |
|---|---|---|
| [Crustdata](https://docs.crustdata.com/general/introduction) | Identity, profile enrichment, workforce searches | Supplied account. The meter uses the returned credit header. |
| [Google Cloud](https://cloud.google.com/vertex-ai/generative-ai/docs/start/quickstarts/quickstart-multimodal) | Gemini drafting, optional persistent cloud services | Supplied GCP project, usage billed by Google. |
| [Brønnøysund Register Centre](https://data.brreg.no/enhetsregisteret/api/docs/index.html) | Norwegian entities, bankruptcy status and statutory roles | Free open-data endpoints |
| [SEC EDGAR](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) | Company submissions and dated 8-K items | Free public data API, identifying user agent required |
| [RDAP registries](https://data.iana.org/rdap/dns.json) | Sender-domain registration dates for supported suffixes | Free public lookups subject to each registry's limits |
| [Razorpay IFSC](https://github.com/razorpay/ifsc) | Indian branch and bank metadata | Free public lookup |
| [GLEIF](https://www.gleif.org/en/lei-data/gleif-api) | Optional LEI lookup | Free public API |
| [crt.sh](https://crt.sh/), [Wayback CDX](https://github.com/internetarchive/wayback/tree/master/wayback-cdx-server), [OpenIBAN](https://openiban.com/) | Optional internal domain-history and bank-code adapters | Free public endpoints, best effort |
| [Sigstore Rekor](https://docs.sigstore.dev/logging/overview/) | Optional public commitment timestamp | Free public transparency service; private receipts are the default |

## Further reading

- [Live account rehearsal and observed limits](docs/rehearsal.md)
- [Privacy and reviewer workflow](docs/privacy.md)
- [Design discussion](docs/discussion/design.md)
- [Original project brief](PROJECT.md)
