# Account and data rehearsal

On 22 November 2026 the supplied Crustdata key returned HTTP 200 from both account endpoints, 15,200 starting credits, 100 total requests per minute and 5 per minute on the enabled identity, enrichment, person search and job search routes. Batch person verification was disabled. The account price card omitted entity watch endpoints. No subscription was upgraded. No real person was submitted for candidate verification.

The supplied Google service account completed a Gemini 2.5 Flash generation on Vertex AI in its own project using the global endpoint.

| Inquiry | Provider response | Consequence |
|---|---|---|
| Ruta exact domain | ruta.no matched Ruta Entreprenør AS at 1.0, identity cost 0.2 credits. Basic info, headcount and people enrichment returned 200 for 2 credits. | Safe starting identity for the live estate walkthrough. |
| Ruta registry | 983830196 returned bankrupt and 139 employees. | Use this number in the estate desk. |
| Ruta people search | A Unicode-preserving company-name filter returned 169 total matches and 15 profiles in the first page, costing 4.95 credits on this request. | Provider totals describe search matches. Dated movements require examination of the returned histories. |
| Balder Bulk Holding AS | Top name-match confidence 0.6. Registry identifies the holding company as 835318222 and the bankrupt operating company as 915644686. | Stop at the identity gate for the ambiguous name. |
| Isfjord Norway AS | Name match 1.0. Registry 981647459 returned bankrupt and 247 employees. | Available as a second estate subject. |

Historical snapshot retention is unconfirmed. The demo uses labeled reconstructions. Watch evidence in the stage example is a replay. A real callback needs an entitled watch and a reachable authenticated receiver. Re-run the account preflight with `python -m scripts.preflight` after a plan change.
