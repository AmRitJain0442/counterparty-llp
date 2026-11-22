# Counterparty LLP: investor pitch

**One-liner** · Counterparty tells a procurement team whether the evidence behind a supplier claim is real, dated and independently witnessed, or whether six data points are really one.

## The 80-second founder pitch

*About 210 words. Read aloud at a normal pace.*

> A renewal goes to committee tomorrow. Someone says the supplier's team is shrinking. The analyst brings a profile, a headcount chart and a list of job openings. The committee asks two things: which date does that number describe, and who else saw it?
>
> Most tools stop at the lookup. We start where the lookup ends.
>
> We ran a live investigation on Crustdata itself. The headcount estimate was 47 profiles on October 19 and 47 again on November 2. The index showed 25 postings, the newest dated November 18. A posting means someone advertised a role. It doesn't mean anyone joined. Six source cards went into the file, but they all traced back to one vendor. So the team filed **Insufficient witnesses**. It also named the next step: ask the supplier for a dated staffing figure.
>
> That collection used 2.23 Crustdata credits. Thirty-six lead and specialist reports are on file for the case, and a reviewer can open any of them.
>
> A confident wrong answer costs a bad renewal or a paid fraudster. An honest "not enough yet" costs one phone call.
>
> We're asking for two introductions to procurement or vendor-risk leads. Each would pick three suppliers and one claim per supplier. We'll compare time to assemble evidence, findings they would defend, and questions left for a phone call.

## Why now

- Dated company and job data is now available through an API. The question has moved from "can I find the number?" to "can I defend it?"
- Generating a fluent answer is cheap. Deciding when the evidence does not support one is the scarce skill, and it is what a committee actually needs.
- Every new investigation here runs live against the providers. A reviewer can see what each source returned, when it returned it and what it cost.

## Buyer-first beachhead

**Buyer:** a procurement or vendor-risk lead who has to defend a supplier decision.

**Wedge:** the Company desk, used before a renewal or a committee paper. It takes one claim, such as "this supplier's team is shrinking", and returns a case file with dated observations, the source behind each, the strongest challenge and a recorded next step.

**First question for the buyer:** "When two sources seem to agree about a supplier, how do you check where each got its information?"

**Why this wedge:** the unit of work is one claim and one case, so the first pilot needs no integration. The finding is easy to judge: either the reviewer can defend it in the room or they cannot.

## The business insight

The bad outcome in vendor review is not a missing data point. It is several data points that look like corroboration and are not. In the Crustdata case, six cards were one witness. A system that counts cards would report agreement. A system that counts independent witnesses reports **Insufficient witnesses** and says what to ask for next.

That changes the product from a research assistant into a gate. The reviewer's time goes to the questions that remain open, not to reopening tabs.

## Expansion

The same intake, evidence, challenge and decision path already runs on three more desks:

1. **Payment.** Does a vendor's bank-change request match the vendor's identity, domain and claimed affiliation? An unresolved mismatch leads to a callback on a number already on file.
2. **Candidate.** Do a consenting candidate's dates and team size line up with employment records and dated headcount?
3. **Estate.** After a Norwegian bankruptcy, where did groups of employees move, and did the proposed successor already exist?

Expansion path: Company claims, then payment-change checks for the same accounts-payable and procurement teams, then the other desks. The next step in each direction is to reuse the same buyer, the same ledger and the same independence rules.

## Revenue hypothesis (unvalidated)

None of this has been tested with a paying customer. There is no revenue and no pilot signed.

- **Hypothesis A, per case.** The buyer pays for each closed case file that reaches a human decision.
- **Hypothesis B, subscription.** A team pays a platform fee that covers a set volume of cases and shared ledger access.
- **Known cost inputs.** The filed Company case cost 2.23 Crustdata credits for collection. A full live Estate case cost 40.38 credits. Gemini and cloud charges are separate and not yet totalled.
- **What the pilot must settle.** The price depends on what a reviewer would pay to avoid reassembling the evidence. We will set it from the measured time saved and the real cost per case, not from a guess made now.

## Defensibility versus generic wrappers

A wrapper sends a prompt and returns a paragraph. Counterparty is built around parts that are harder to copy:

- **Independence rules.** Findings need witnesses that do not share an origin. Crustdata observations are checked against separate records such as registry, filing, domain and legal-entity sources where they apply.
- **Opposing counsel.** A separate step challenges each draft finding before it is filed. Gemini drafts, but it has no signing authority.
- **Provenance in the file.** Every card records its source, observation date and availability. The case keeps the reported credit cost.
- **Receipts and a ledger.** A filed case has a receipt a second reviewer can verify. The receipt on the Company case is `LOCAL_ONLY`. Public timestamping is off on the deployed revision.
- **Reviewer decisions.** Dispositions and notes accumulate next to the evidence. Over time this becomes the record of which findings survived human review.
- **Privacy built into the workflow.** Candidate checks require consent. Movement groups smaller than five stay hidden. Adverse results call for a human callback, not an automatic action.

The moat is not the model. It is the discipline around the evidence, and the reviewer history that builds up on top.

## What is real today, and what is not

| Claim | Status |
| --- | --- |
| Every new investigation runs live and can incur provider charges | True. Submissions from the map, a desk or the streaming API all run live. |
| The Crustdata case | A filed live case. Opening it shows what the providers returned when it ran. Playback spends no credits. |
| Four desks, 12 leads, 24 specialists | Built. A fully executed live case runs 28 Gemini reviews. |
| Customers, revenue, price, market size, ROI | None validated. None claimed. |
| Dependence on Crustdata | A real risk. The provider's coverage and its account entitlements shape what the product can check. |

## The ask

**Two introductions to procurement or vendor-risk leads** at organizations that take supplier renewals to a committee.

Each pilot runs on three suppliers the team already knows, with one claim per supplier. We measure three things against how the team works today:

1. Time to assemble the evidence.
2. Findings the team would defend in the room.
3. Questions still worth a phone call.

Success is a team that can say, per case, whether the file saved time and whether it changed what they would have said. If it does not, we learn that on three suppliers, not thirty.

**Links:** [Filed Crustdata case](https://counterparty-939419364980.asia-south1.run.app/?case=c4b983b065f7413daaf908c9ab06f9a6#swarm) · [Receipt](https://counterparty-939419364980.asia-south1.run.app/api/cases/c4b983b065f7413daaf908c9ab06f9a6/receipt) · [Start a live investigation](https://counterparty-939419364980.asia-south1.run.app/workspace.html#live) · [Sales guide](sales-guide.md)
