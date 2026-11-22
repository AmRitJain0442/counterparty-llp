# Selling Counterparty LLP

**Buyer** · a procurement or vendor-risk lead who has to defend a supplier decision.

**First question** · “When two sources seem to agree about a supplier, how do you check where each got its information?”

## The buyer’s story

It is Thursday afternoon. A renewal goes to committee tomorrow, and someone says a supplier’s team is shrinking. An analyst brings a company profile, a headcount chart and a list of job openings. The committee asks two questions. “Which date does that number describe? Who else saw it?” Someone has to reopen the tabs.

Counterparty gives the analyst a file they can open in that meeting. It matches the supplier in Crustdata, dates each observation, and checks what independent records can establish. A reviewer can open the original finding, see who challenged it, and record the next decision. A useful outcome can be as specific as “We have one estimate. Ask the supplier for a dated staffing figure before relying on it.”

## A 90-second demo script

**0–15s** · Open the recorded Company investigation.

> “You’re about to renew a supplier. Someone says its team is shrinking. Before that goes into the committee paper, what would you accept as evidence? Let me show you how we’d check.”

**15–35s** · In **Trace → Evidence**, expand **Whole-company headcount** and **Indexed job posting**.

> “This is a replay of a real investigation we ran on Crustdata itself. The Company desk matched its domain, enriched the company record and searched indexed jobs. The headcount estimate was 47 profiles on October 19 and still 47 on November 2. The index also showed a posting dated November 18. A posting tells us someone advertised a role. It doesn’t tell us anyone joined.”

**35–55s** · Use **Find** to select **Independence checker**. Show its lead and its cited card.

> “Here’s the question I’d ask before the meeting. Who else saw that headcount? This specialist traced the figure back to Crustdata. Six cards went into the file, but the figure still had one source. The team filed ‘Insufficient witnesses.’ I can show my committee exactly why.”

**55–75s** · Show the credit total and receipt in **Trace**.

> “The original collection used 2.23 Crustdata credits. Opening the replay spends none. The receipt lets another reviewer check that this is the record we filed. I would ask the supplier for a staffing figure covering the same business unit and date.”

**75–90s** · Return to the buyer.

> “Would you try this on three public suppliers you already know? Pick one claim per supplier. We’ll compare the time to assemble the evidence, the findings your team can defend, and the questions still worth a phone call.”

[Open the recorded case](https://counterparty-939419364980.asia-south1.run.app/?case=c4b983b065f7413daaf908c9ab06f9a6#swarm) · [Verify its receipt](https://counterparty-939419364980.asia-south1.run.app/api/cases/c4b983b065f7413daaf908c9ab06f9a6/receipt)

## The skeptical buyer

**“We already pay for Crustdata. Why would I pay for a tool that tells me there isn’t enough evidence?”**

“If all you need is a company lookup, you already have it. The work we take on starts when someone has to defend a decision. Your reviewer gets the dated observation, the source behind it, the strongest challenge and a record they can hand to a colleague. Let’s use cases your team has already reviewed and measure whether that handoff saves time. The original case cost above covers Crustdata collection only. Gemini and cloud charges are separate.”

## What ships today

| Feature | What the buyer gets | How Crustdata contributes |
| --- | --- | --- |
| Company identity | Match a name or domain to a company before investigating it. Ambiguity can be sent to identity review. | Company Identify returns candidates and confidence. A unique qualifying match with a company ID unlocks enrichment. |
| Payment desk | Assess a vendor bank-change request. A supported domain mismatch can lead to a callback using a number already on file. The payment decision stays with the reviewer. | Company identity and domain data can be checked against the Norwegian registry. With consent, person history can be checked for a change of employer. RDAP and Indian IFSC lookups provide additional context for relevant inputs. |
| Candidate desk | Check consented employment dates, colleague overlap and a claimed team size. The reviewer can record a question for the candidate. | Person Identify and Person Enrich supply the employment history. An employer-specific Person Search provides a colleague sample. Dated company headcount puts team-size claims in context. |
| Estate desk and archive | Examine workforce movement after a Norwegian bankruptcy. See destination groups and unknowns on a flow diagram, and test a successor theory against formation dates and statutory roles. A separate archive holds a dated, cached example. | Company matching and paginated Person Search supply employment histories. The desk uses dated next-employer starts, requires sufficient profile coverage and suppresses destination groups smaller than five. Bankruptcy and corporate roles come from the registry. |
| Company desk | Review executive changes, headcount and hiring alongside issuer filings. A qualifying interim finance appointment and filing can produce a time-bounded forecast for human review. | Company Enrich supplies people and headcount observations. Job Search supplies the most recent indexed posting. SEC EDGAR supplies independent dated filing evidence when the issuer can be matched. |
| Independent evidence | Each card records its source, date and availability. Reviewers can trace several observations back to their common source and request corroboration. | Crustdata is one source of evidence. Norwegian registry records, SEC filings, domain registries, IFSC metadata and legal-entity lookups contribute where identifiers and coverage permit. |
| Agent map and discussion room | Four swarms, 12 leads and 24 specialists. Zoom, pan or search the map, inspect personas and citations, stream handoffs and replay a filed investigation. Each lead receives both specialist reports. | The team reviews the collected source cards. A fully executed live case runs 28 Gemini reviews through Vertex AI. Other work includes calendar arithmetic and deterministic evidence checks. |
| Case ledger and human review | Filter by desk or mode, reopen findings and specialist referrals, add a reviewer disposition or note, and copy or verify the case digest. The hosted deployment uses Firestore. | Filed cases retain the projected Crustdata observations and reported credit costs alongside the other evidence. The receipt checks the integrity of that filed record. |
| Provider room and account meter | Inspect the account’s credit balance, endpoint prices, entitlements, rate limits and actual case spend when reported. | The app reads Crustdata’s account endpoints and credit headers. The Company example cost 2.23 credits. A documented Estate rehearsal cost 40.38. |
| Company watch | Inspect a configured company watch, its run times, status, records checked and credits. The hosted Ruta watch returned a successful baseline. | Watch history is pulled from Crustdata. The application also has an authenticated callback receiver and Pub/Sub processing for watches configured to deliver notifications. |
| Demo, replay and fresh runs | Rehearse with a curated case, replay an existing case, or submit a new live investigation. A streaming API and an interactive API reference are available. | Only a fresh live investigation collects new Crustdata evidence. A replay reads the evidence saved with the original case. The provider room separately reads account and watch information. |

## What is live on the hosted app?

Checked on **November 22, 2026**. The main map and desk intake open in **Demo**. Choose **Run → Live** for fresh collection, or use the dedicated **Live investigation** page. The public deployment shares its ledger across visitors. Use public company information for a sales walkthrough.

| Status | Coverage |
| --- | --- |
| **Verified live collection** | The recorded Company case succeeded on Company Identify, Company Enrich and Job Search. All 36 reports completed. The live server also returned an available Crustdata account card and an active watch for `ruta.no` with one successful run. |
| **Enabled on this Crustdata account** | Company Identify, Company Enrich, Company Search, Person Identify, Person Enrich, Person Search and Job Search. The desks call the subset required by the case. Person-level investigation requires consent. Company Search is an account entitlement, separate from the Company desk’s domain identification step. |
| **Conditional live sources** | Norwegian registry and roles, SEC EDGAR, supported domain RDAP, Indian IFSC and GLEIF require suitable identifiers and provider availability. The Crustdata notification receiver requires delivery configuration. The documented Ruta watch uses pull-based history. |
| **Disabled or optional** | Batch Person Verify is disabled on this account. Public Rekor timestamping is off on the deployed revision. The verified case has a `LOCAL_ONLY` receipt. Certificate history, Wayback and OpenIBAN are lower-level adapters outside the standard public investigation form. |
| **Curated or recorded** | Demo uses synthetic cases, the Estate archive is cached, and the staged watch event is labeled replay. Reopening a recorded live case shows what the providers returned at the time it ran. |

[Start a live investigation](https://counterparty-939419364980.asia-south1.run.app/workspace.html#live) · [Inspect current provider status](https://counterparty-939419364980.asia-south1.run.app/workspace.html#providers) · [API reference](technical-reference.md) · [Measured Estate rehearsal](rehearsal.md)
