# Live provider contract

The application calls `backend.live.collect_live(desk, subject, consent, inputs)`. It validates a small set of fields, resolves legal identifiers, dispatches independent read-only provider lanes, interprets dated observations and projects display-safe records. Low-confidence or ambiguous matches stop the enrichment chain. The internal provider transport accepts curated operations. HTTP clients cannot supply provider payloads, destination URLs or watch parameters.

The public response holds evidence cards with source, label, detail, as-of date, mode and source URL. Some cards also have an observation date. Credits are the sum of measured Crustdata charges, or null if any attempted call lacks a valid header. Partial provider failures contribute no witness. Estate counts use a complete bounded query, a coverage floor of fifteen and destination groups of five. New cases collect live evidence. Playback preserves the source and observation date on each filed card.

Gemini drafts use ADC with the configured GCP project and location. An evidence analyst and opposing counsel each receive a minimized projection. Verdicts come from deterministic adjudication. Human corrections and watch events remain separate from the sealed finding.

See [estate processing](discussion/estate.md), [infrastructure](discussion/infrastructure.md), [account rehearsal](rehearsal.md) and [the Crustdata documentation](https://docs.crustdata.com/general/introduction).
