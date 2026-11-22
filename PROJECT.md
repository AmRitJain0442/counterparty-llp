# #1 COUNTERPARTY LLP (Grand Champion, 46/50)

> **A firm that tests every claim about a counterparty, person or company, against who actually works there and when they moved.**

Track fit: **Trust & compliance** (primary), with Buying & paying, Hiring and Investing. Built for "ContextCon 05: Services, Replaced".

---

This is the original design brief. The [sales guide](docs/sales-guide.md) describes the shipped live workflows and verified provider coverage.

## 1. The problem and the fee we replace

Every service firm in finance, insurance and compliance is paid to answer one question:

> *Is the party on the other side who they say they are, and are they still alive?*

| Who pays today | For what | Typical fee | Our cost |
|---|---|---|---|
| AP / treasury teams | Vendor-master audits, call-back checks before bank-detail changes | Staff time plus BEC losses (bank-detail fraud) | ~4 credits per check |
| HR / background-check firms | Employment verification | $50–200 per check, 3–10 days | ~20 credits, 40 s |
| Bankruptcy trustees / creditors | First forensic pass on an estate | NOK 150–400k | ~30 credits |
| Investors / compliance | Kroll-style due-diligence report | $5–25k, 2 weeks | ~15 credits |

**Why us:** the hardest thing to fake at scale is who actually works somewhere and when they joined or left. Crustdata provides that as dated, queryable data. Public registries and filings act as independent second witnesses.

---

## 2. What it is

One firm, **four desks**, and **one evidence ledger**. Each desk ends in a single, physical verdict:

| Desk | Question | Verdict |
|---|---|---|
| **Payment** (Ghost Controller) | Is the person asking us to change bank details still at the vendor? | **HELD** / RELEASED |
| **Candidate** (Colleague Witness) | Does this CV survive the candidate's own dated record and their colleagues? | **FAILED** / VERIFIED |
| **Estate** (AFTERLIFE) | A large firm went bankrupt: where did its people go, and is anything trading under its name? | **KILLED** / REQUEST FOR EXPLANATION |
| **Name a Company** (Key-Person + Audit the Auditor) | Is leadership or finance moving ahead of the filings? | **SIGNED** forward prediction |

Desk #1 and desk #2 are also written up as standalone projects in `02_COLLEAGUE_WITNESS.md` and `03_GHOST_CONTROLLER.md`.

---

## 3. Architecture

```
 Inputs: email / CV / company name / registry feed
        │
        ▼
 ┌─────────────────────┐    aliases: orgnr, LEI, CIK, domain
 │ 1. Identity spine   │◄── Crustdata /company/identify, /person/identify
 └─────────┬───────────┘    (confidence < 0.8 → "who is this?" card)
           ▼
 ┌─────────────────────┐   ┌──────────────────────┐
 │ 2. People desk      │   │ 3. Company desk      │
 │ /person/enrich      │   │ /company/enrich      │
 │ /person/search      │   │ /company/search      │
 │ /batch/person/verify│   │ /job/search (aggs)   │
 └─────────┬───────────┘   └──────────┬───────────┘
           └────────────┬─────────────┘
                        ▼
 ┌──────────────────────────────────────────────┐
 │ 4. Witness desk (non-Crustdata)              │
 │ Brønnøysund /enheter + /roller · EDGAR 8-K   │
 │ RDAP · crt.sh · IFSC · OpenIBAN · Wayback    │
 │ GLEIF · GCP Web Risk                         │
 └─────────────────────┬────────────────────────┘
                       ▼
 ┌──────────────────────────────────────────────┐
 │ 6. Adjudication: Gemini drafts → opposing    │
 │ counsel (deterministic kill rules) → partner │
 │ signs only two-witness findings → Rekor hash │
 └─────────────────────┬────────────────────────┘
                       ▼
 7. Meter + ledger (Firestore, BigQuery cache, cost meter)
 5. Watch desk (Crustdata watchers → Cloud Run → Pub/Sub) reopens past decisions
```

1. **Identity spine.** Crustdata `/company/identify` (0.2 credits) and `/person/identify` (1 credit) produce a Crustdata ID, with aliases for the Norwegian org number, LEI, domain and SEC CIK. If confidence is low, the system says so and does not guess.
2. **People desk.** `/person/enrich` returns `experience[]` with start and end dates. `/person/search` finds colleagues whose dates overlapped and everyone who ever worked at a given company. `/batch/person/verify` checks CV claims, with consent.
3. **Company desk.** `/company/enrich` with the `headcount`, `people`, `hiring`, `funding` and `news` groups. `/company/search` for peer baselines. `/job/search` aggregations serve as the "still hiring?" life sign.
4. **Witness desk.** Independent public sources (see §4).
5. **Watch desk.** Crustdata `/watch/company` and person watchers on a **30-day SLA**, armed days before the presentation (never the 1-day SLA, which costs 150 credits per record). Webhooks go to Cloud Run, then Pub/Sub.
6. **Adjudication.**
   - Gemini on Vertex AI drafts each finding.
   - An **opposing-counsel agent** attacks it using deterministic rules: a successor or parent company, an acqui-hire, a sample that is too small, or a stale profile.
   - The **partner** signs only findings with **two witnesses**.
   - Each finding is hashed to **Sigstore Rekor**.
7. **Meter and ledger.**
   - The `/account/endpoints` price card plus the `X-Credits-Used` header drive a live cost meter, shown against the human fee.
   - Firestore holds the decision ledger.
   - BigQuery holds cached batch pulls.
   - A token-bucket gateway enforces per-endpoint rate limits.

---

## 4. Data sources

### Crustdata (the star)
| Endpoint | Used for | Cost (docs) |
|---|---|---|
| `/company/identify` | Name or domain → Crustdata ID | 0.2 cr |
| `/person/identify` | Profile URL or **email** → person ID | 1 cr |
| `/company/enrich` | Headcount (and growth), people, hiring, funding, news | 2–4 cr |
| `/company/search` | Peer baselines, screener | 0.03 cr per result |
| `/person/enrich` | Dated employment history | 1 cr (+add-ons) |
| `/person/search` | Colleagues whose dates overlapped; past employees of X | 0.03 cr per result |
| `/batch/person/verify` | Work-history verification | 10 cr per result |
| `/job/search` | Postings and aggregations | 0.03 cr per result |
| `/watch/company`, person watchers | Change alerts | 5 cr per change (30-day) |
| `/account/endpoints`, `/account/credits` | Entitlements, prices, balance | free |

> ⚠️ **Not yet live-tested.** All Crustdata figures come from docs.crustdata.com. Run the Day-0 checklist (§9) before building.

### Supporting witnesses (tested live 2026-11-22 unless noted)
| Source | Role |
|---|---|
| Brønnøysund `/enheter?konkurs=true`, `/enheter/{orgnr}/roller` | Bankruptcy flag and date; directors with name + date of birth (used for matching, never displayed) |
| SEC EDGAR full-text search + submissions | 8-K Item 5.02 (officer change), Item 4.01 (auditor change); a User-Agent header is required |
| RDAP, crt.sh (exact-domain lookups only) | Domain age, certificate history |
| Razorpay IFSC, OpenIBAN | Bank branch, city, BIC |
| Wayback CDX | Website history, life signs |
| GLEIF | Legal entity, parent companies |
| GCP Web Risk *(needs enabling)* | Flags hijacked or malicious domains |
| Gemini on Vertex AI (with Search grounding) | Drafting, dated corroboration |
| Sigstore Rekor | Tamper-evident receipts |

---

## 5. Proposed presentation script (~5 minutes)

**Act 1: The Payment (70 s) → HELD**
- **Setup:** a judge forwards a seeded "please update our bank details" email that uses a real vendor contact's name.
- **What the system shows:**
  - The contact's profile shows they **left the vendor in August**, dated by their start date at the new employer.
  - The sending domain is 11 days old (RDAP).
  - The new IFSC belongs to a different bank and city.
- **Verdict:** **HELD**, with a call-back to the number on file.
- **Live calls:** `/person/identify`, `/person/enrich`, `/company/enrich`, RDAP, IFSC. Nothing is cached.
- **Fee line:** *"A vendor-master audit and a BEC loss, against about 4 credits."*

**Act 2: The Candidate (75 s) → FAILED**
- **Part 1:** with the judge's consent, the system checks their own profile. It finds 3 colleagues whose dates overlapped and, with permission, names them.
- **Part 2:** a seeded false CV claims "led 40 engineers". The company's engineering headcount that quarter was **11**, so the claim **FAILS**.
- **Live calls:** `/person/enrich`, `/person/search`, `/company/enrich`, `/batch/person/verify`. An "as of" date is shown.
- **Fee line:** *"A $50–200, 5-day background check, against about 20 credits in 40 seconds."*

**Act 3: The Estate (80 s) → KILLED**
- **Part 1 (live):** **Ruta Entreprenør AS**, 139 employees, went bankrupt on 2026-11-02. The system fetches ruta.no and counts how many former staff still list Ruta and how many have moved on.
- **Part 2 (cached, labelled CACHED):** an older large bankruptcy shows a **Sankey diagram of where its people went**. The directors of the top destination company are checked against the dead firm's directors.
- **The hit:** **Balder Bulk Holding AS** appears as a shared-board hit.
- **The kill:** opposing counsel **KILLS** it. It is the solvent parent company and existed before the bankruptcy. *We show our own false-positive filter.*
- **Live calls:** Brønnøysund ×3, `/company/enrich`, `/person/search`, a fetch of ruta.no.
- **Fee line:** *"The trustee's first forensic review."*

**Act 4: Name a Company (75 s) → SIGNED**
- **Setup:** a judge names a US-listed company. EDGAR pulls its latest 8-K Items 5.02 and 4.01.
- **What the system shows:**
  - From Crustdata: CXO tenure, finance-team movement, and a key-person "bus factor".
  - A **REPLAY** of the watcher log shows when the profile data moved compared with the filing date.
- **Verdict:** a forward prediction is **SIGNED** and timestamped in Rekor.
- **Fee line:** *"A Kroll-style DD report, $5–25k, against about 15 credits."*

**Close:** the meter shows about 60 credits in total, against the human fees listed above. If anything must be cut, **cut Act 4 before Act 3**.

---

## 6. Live-call budget

Starter plan: 5 requests/min per endpoint, 100 RPM overall.

| Endpoint | Calls on stage | Peak/min | Credits (est.) |
|---|---|---|---|
| /person/identify | 1 | 1 | 1 |
| /company/identify | 2 | 1 | 0.4 |
| /person/enrich | 2 | 1 | ~5 |
| /company/enrich | 4 | 1–2 | ~14 |
| /person/search (≤100 results each) | 3 | 1 | ~9 |
| /batch/person/verify (seeded, 2 people) | 1 | 1 | 20 |
| /account/* | 2 | 1 | 0 |
| **Total** | **15** | **≤3 on any endpoint** | **~50** |

Free public calls add about 12 more. Keep a 2× credit buffer. Night-before caching costs about 1.5k credits.

---

## 7. Honesty and privacy rules (non-negotiable)

1. **Two witnesses.** Every adverse finding needs Crustdata **plus** one non-Crustdata source.
2. **Movement is evidence; a stale profile is context.**
   - Date an exit by the **start date at the next employer**.
   - A "current employer" field that hasn't changed proves nothing.
   - People who never update their profile go into an "unknown" bucket.
3. **Aggregate workers.**
   - Show counts and timelines only, with a minimum group of 5.
   - Name people **only** with their consent or when they are statutory officers.
   - Never display a date of birth.
4. **No automated legal effect** (GDPR Art. 22). Adverse results mean **hold plus a human call-back**. Keep a one-page note on the legitimate-interest basis (GDPR Art. 6(1)(f)).
5. **Phrasing.** Findings are **"Requests for Explanation"**, never accusations.
6. **Label everything.**
   - Every card shows an "as of" date.
   - Replayed watcher events are labelled **REPLAY**; cached data is labelled **CACHED**.
7. **No backtest claims** until Crustdata confirms it stores point-in-time snapshots. Until then:
   - Call it a "retrospective reconstruction".
   - Make forward predictions only, timestamped in Rekor.

---

## 8. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Verify, batch or search isn't enabled on our key | Check `/account/endpoints` first. Act 2 falls back to enrich plus colleague overlap. Act 3 falls back to the company `people` group. |
| An entity-resolution error defames a director | Match on name + date of birth. Auto-kill parent or group companies and companies that predate the bankruptcy. Use RfE wording. |
| Thin or stale coverage | Show an "insufficient witnesses" card when fewer than 15 profiles are found. Pre-qualify fallbacks: Isfjord Norway (247 staff), Balder Bulk (151). |
| Judges ask about look-ahead bias | Forward predictions only, Rekor timestamps, "as of" dates on everything. |
| Rate limits stall a live call | Token-bucket gateway. Batch caching the night before. Budget of 15 live calls or fewer. |

---

## 9. Day-0 checklist (do these when the Crustdata key arrives)

1. `GET /account/endpoints`: record which endpoints are enabled (verify, batch, search, live, watchers, Agent Search) and their prices.
2. `GET /account/credits`: check the balance. Decide whether to spend $5 to reach 15 RPM.
3. `/company/identify` on Ruta, Balder Bulk and Isfjord: check the match rate and that headcount roughly matches the registry (139 / 151 / 247).
4. `/person/search` with past employer = Ruta: how many profiles, how many with a start date after 2026-11-02, and whether any department has at least 15.
5. Headcount history: stored snapshots or reconstructed? This settles the backtest rule.
6. `/person/enrich` on a teammate: how fresh are the experience dates?
7. A dry run of `/batch/person/verify` on one consented CV: check the output format and polling time.
8. **Arm watchers now** (30-day SLA) so a real log exists by presentation day.
9. Load-test the gateway at 5 RPM. Confirm `X-Credits-Used` reaches the meter.

---

## 10. Build plan

| Milestone | Deliverable |
|---|---|
| M0 | Day-0 checklist done. Crustdata client with token bucket, cache and cost meter. |
| M1 | Identity spine plus the witness desk (Brønnøysund, EDGAR, RDAP, IFSC adapters). |
| M2 | Payment desk working end to end (this is also project #3). |
| M3 | Candidate desk with consent flow and verify (this is also project #2). |
| M4 | Estate desk: Ruta live, one cached older estate, Balder kill rule. |
| M5 | Adjudication: opposing-counsel rules, partner signing, Rekor hashing. |
| M6 | Name-a-Company desk with EDGAR 5.02/4.01 and a replayed watcher log. |
| M7 | Stage UI: four verdict cards, cost meter, "as of" / CACHED / REPLAY badges, rehearsal. |

**Stack:** Python (FastAPI) on Cloud Run, Pub/Sub, Firestore, BigQuery, Gemini on Vertex AI, and a React or Next.js stage UI.

---

## 11. Q&A prep

- **"Isn't this just LinkedIn scraping?"** No. Crustdata is a licensed data provider. We use movement data only as a *first witness*, and every adverse finding is confirmed by a registry, filing or bank record.
- **"What if someone hasn't updated their profile?"** They count as "unknown". They never count as evidence against anyone.
- **"Did you predict this in advance?"** Only the forward predictions in Rekor, which carry visible timestamps. Anything else is labelled a reconstruction.
- **"What about privacy?"** We show aggregates, name people only with consent or when they are statutory officers, put a human in the loop, and have a documented legitimate-interest basis.
