# Live estate employee flows

`backend.estate.estate_evidence(subject, domain, resolved_company, bankruptcy_date, as_of) -> dict` is synchronous. Call it from the live estate desk after matching a confirmed bankruptcy record to one resolved company. Pass the registry filing date and the investigation cutoff. The result describes first subsequent employer starts reconstructed from the histories available at retrieval time.

## Inputs and provider request

- `resolved_company` accepts the matched Crustdata `company_data` object or a positive integer Crustdata company ID. The collector reads the ID from the record or its `basic_info`. For a domain-only match it uses the verified `primary_domain`, `website`, or `all_domains` in that record. The intake `domain` can select among those aliases. A name or intake domain alone cannot establish the identity. `subject` is the desk label and never enters the query. [Company Identify](https://docs.crustdata.com/company-docs/identify/introduction)
- `bankruptcy_date` and `as_of` accept Python dates, datetimes, ISO calendar dates or ISO timestamps. Offset-aware timestamps are converted to UTC. The movement window includes both calendar days and ends by today's UTC date.
- The collector posts to `https://api.crustdata.com/person/search` with the server's `CRUSTDATA_API_KEY` and API version `2025-11-01`. It uses one exact all-employers filter on `experience.employment_details.company_id` or `experience.employment_details.company_website_domain`. The projection requests the person ID for deduplication. On both `current` and `past` roles it selects `crustdata_company_id`, `company_website`, `start_date` and `end_date`. [Search field reference](https://docs.crustdata.com/person-docs/search/reference#filter-paths-and-their-returned-twins) · [Role response schema](https://docs.crustdata.com/api-reference/person-apis/search-people-using-filters-and-sorting)
- Successive requests preserve the query and sort order and pass `next_cursor` as `cursor`. The search uses the shared endpoint and overall throttles. It reads up to five pages of 50 profiles. A continuation beyond that budget gives a partial result. Each POST has one attempt. [Person Search pagination](https://docs.crustdata.com/person-docs/search/reference#paginate-through-results)

## Counting rules

**Coverage** counts distinct person IDs with an estate role that could have begun by filing. It includes stale and undated listings, even when a move cannot be established. This measures the histories examined. Registry headcount and the provider's search total have separate meanings.

**One person contributes to at most one destination.** The collector starts with estate positions evidenced by filing and follows consecutive estate roles through promotions. A dated past estate end establishes the ordering. The first subsequent external employer's **start** dates the move. That next appointment may already be in the past. An intervening pre-filing appointment rules out attributing a later job to the estate. A later rehire leaves an earlier observed move intact. An overlapping appointment, tied starts at different employers, an unresolved next employer, or an undated role that could intervene leaves the destination unknown. A still-current estate listing alone also remains unknown. Year and month dates carry their full calendar ranges. A move qualifies only when its ordering and inclusion in the window hold across that uncertainty.

The collector groups by company ID, using an unambiguous normalized website host to connect roles with missing IDs. Conflicting IDs stay distinct. Profiles with missing role sections, invalid dates or conflicting duplicate histories can contribute coverage but cannot establish a movement. A complete search needs a terminal cursor and an exact, consistent total matching the number of distinct returned person IDs.

## Return value and integration

| Key | Meaning |
| --- | --- |
| `status` | `ok`, `insufficient_coverage`, `partial`, `unavailable`, `unresolved_company` or `invalid_window`. |
| `flows` | Rows shaped like `{"from":"estate.example","to":"next.example","count":5}`, largest first. Publication requires a complete search, coverage of at least **15** and at least **5** distinct people per destination. A destination domain needs five supporting movers. An identified company can also appear as `Crustdata company 123`. |
| `coverage`, `unknown` | Coverage is the observed sample size, or `null` when unmeasurable. For a publishable sample, `unknown` counts everyone without a published destination, including small cohorts. A residual of one to four is suppressed as `null`. Incomplete or insufficient searches also leave it `null`. |
| `evidence`, `as_of` | A display-safe evidence card with `source`, `label`, `detail`, `url`, `status`, `mode="LIVE"` and a UTC collection timestamp. Top-level `as_of` is that same collection timestamp. The card describes the movement window separately. |
| `steps` | One `person_search` step per attempted page, including its status and actual credits when known, followed by an `Estate employee flows` summary. An input or credential gate produces only the summary. |
| `credits` | Sum of the actual `X-Credits-Used` headers, including charged failures. A missing or invalid charge makes the total `null`. A run with no attempted calls also returns `null`. |
| `signals` | Empty list. The collector supplies aggregate evidence for subsequent review. |

Append the returned evidence and steps to the case and use the returned flows for the estate diagram. Add the estate credit total only when a `person_search` step exists, propagating an unknown total across billed operations. On interruption, preserve the page steps, known charges and reviewed coverage. The empty flows in that case carry no conclusion about where people went. Person IDs stay in request-local memory. The ledger receives only organization labels, counts and collection metadata.

Run `python -m pytest -q tests/test_estate.py` to exercise the public function against mocked HTTP responses.
