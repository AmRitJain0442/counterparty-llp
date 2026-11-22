# Decision ledger and watch integration

## Application contract

The case API imports the synchronous ledger and receipt functions and mounts the FastAPI watch router. Async routes run blocking ledger and SDK calls in a worker thread.

- `backend.storage.save_case(case)` persists a JSON decision with a nonempty string `id` and returns the stored decision. `list_cases()` returns full decisions newest first. `get_case(id)` returns the decision or `None`. The caller supplies the display-safe case, including its original verdict, evidence labels and as-of dates.
- `backend.storage.bind_watch(watch_id, case_id)` binds a provider-issued entity watch to an existing case after an operator confirms its scope. Dedicate each watch to one case. Bindings survive restarts. Registering a binding makes no provider call.
- `app.include_router(backend.watch.router)` mounts `POST /watch/webhook` and `POST /watch/pubsub`. The watch worker adds a separate `watch_review` object with `status="REOPENED"`, `event_count`, `as_of` and `event_id`. Display it as a request for human review alongside the original decision.
- `backend.storage.put_cached_batch(key, data, *, as_of, ttl_seconds)` and `get_cached_batch(key)` handle JSON batch results. A hit returns `{"mode": "CACHED", "as_of": ..., "data": ...}`. Callers scope keys to the source, query, consent boundary and projection, and pass the source observation date where available.
- `backend.receipts.create_receipt(finding)` creates a private, salted commitment. A trusted caller may request publication for a signed finding with `publish=True` and operator opt-in. `verify_receipt(finding, receipt)` rechecks the commitment and any published bundle. Persist the receipt beside the exact JSON finding it covers.

## Decisions

SQLite on a persistent local disk is the default. Firestore is the shared ledger for Cloud Run replicas. Selecting Firestore explicitly makes service and credential failures visible to the caller. BigQuery is an optional, expiring cache for batch results.

Crustdata signs the timestamp and exact webhook body. Only a genuine change from a bound company or person entity watch opens a review. Test deliveries and baseline samples can exercise the receiver without creating reviews. The ledger stores an event before publication. Pub/Sub carries its opaque ID. The consumer authenticates Google's push identity and commits deduplication together with the review update. [Crustdata entity watcher](https://docs.crustdata.com/watcher-docs/company/entity.md) · [Pub/Sub push authentication](https://cloud.google.com/pubsub/docs/authenticate-push-subscriptions)

Rekor publication uses a dedicated signing key and a salted commitment that the firm can open privately. Verification uses Sigstore's signed bundle, an independently trusted log root and the firm's public key. A verified receipt dates the commitment. The decision and its witnesses retain their own evidentiary meaning. [Sigstore blob signing](https://docs.sigstore.dev/cosign/signing/signing_with_blobs/) · [Sigstore verification](https://docs.sigstore.dev/cosign/verifying/verify/)

## Delivery and failure behavior

| Boundary | Durable effect | Recovery |
| --- | --- | --- |
| Valid provider change | Stage an event under SHA-256 of the provider namespace, watch ID and chunk notification ID. Resolve its case through the pre-existing binding. | Unbound watches return 409. Repeated notifications reuse the first staged event. |
| Publisher acknowledgement | Move the event from pending to published. The topic contains the 64-character event ID. | Provider retry or the outbox drain retries pending rows. A crash after Pub/Sub accepts the message can produce two pushes. |
| Pub/Sub push | Verify the Google issuer, signature, expiration, configured audience, verified service account email and subscription. In one transaction update the case review and mark the event applied. | A repeated push receives 204. Failed transactions can be retried. A late publisher acknowledgement cannot undo an applied event. |
| Out-of-order updates | Increment the count for each distinct event and retain the latest provider delivery time. | The case's original evidence, as-of time, decision and receipt remain available for review. |

The provider's delivery time dates the review trigger. A reviewer must still establish when the underlying employment or company change occurred. The callback accepts inline entity watcher results. Link-mode downloads, discovery watches and new provider watch registrations have separate collection and consent requirements. [Crustdata delivery formats](https://docs.crustdata.com/watcher-docs/payload-delivery.md)

## Storage and trust boundaries

SQLite uses explicit write transactions and full synchronization. Firestore uses retryable document transactions for the same state changes. The full case JSON is a string field so nested evidence arrays round-trip identically on both backends. Re-saving the same case ID updates its decision and preserves ledger-managed review state. File a fresh ID for a new adjudication that needs its own historical record. Listing reads the complete ledger as required by the case API.

The batch cache keeps the original as-of value, data scope and expiry independent of filing time. A cache hit is always marked `CACHED`. Keep large batch pulls out of the decision document and save the minimized evidence needed to explain the ruling.

A version-1 receipt commits to a domain separator, a private random 256-bit nonce and the finding's sorted, compact UTF-8 JSON. Top-level `receipt`, `receipt_record` and `watch_review` are ledger decorations. The decision body includes the identifiers, evidence and dates being attested. A local commitment can be checked by an authorized reader. Public assurance additionally requires offline Cosign verification of the artifact signature, signed checkpoint, inclusion path and RFC 3161 timestamp. Use `verify_receipt(case, receipt, require_rekor=True)` when that assurance is required. A concurrent decision edit prevents attachment to the wrong snapshot.

The private case service and narrow callback service share the ledger. Operators bind watches and publish receipts through authenticated ledger access. Provisioning, region selection, IAM grants, outbox recovery and verification commands are in the [cloud setup guide](../../cloud/README.md).
