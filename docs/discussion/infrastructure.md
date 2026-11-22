# Decision ledger and watch integration

## Application contract

The FastAPI owner can import these synchronous functions. A synchronous route or a worker thread can call them directly.

- `backend.storage.save_case(case)` persists a JSON decision with a nonempty string `id` and returns the stored decision. `list_cases()` returns full decisions newest first. `get_case(id)` returns the decision or `None`. The caller supplies the display-safe case, including its original verdict, evidence labels and as-of dates.
- `backend.storage.bind_watch(watch_id, case_id)` binds a provider-issued entity watch to an existing case after an operator confirms its scope. Dedicate each watch to one case. Bindings survive restarts. Registering a binding makes no provider call.
- `app.include_router(backend.watch.router)` mounts `POST /watch/webhook` and `POST /watch/pubsub`. The watch worker adds a separate `watch_review` object with `status="REOPENED"`, `event_count`, `as_of` and `event_id`. Display it as a request for human review alongside the original decision.
- `backend.storage.put_cached_batch(key, data, *, as_of, ttl_seconds)` and `get_cached_batch(key)` handle JSON batch results. A hit returns `{"mode": "CACHED", "as_of": ..., "data": ...}`. Callers scope keys to the source, query, consent boundary and projection, and pass the source observation date where available.
- `backend.receipts.create_receipt(finding)` creates a private, salted commitment. A trusted caller may request publication for a signed finding with `publish=True` and operator opt-in. `verify_receipt(finding, receipt)` rechecks the commitment and any published bundle. Persist the receipt beside the exact JSON finding it covers.

## Decisions

SQLite on a persistent local disk is the default. Firestore is the shared ledger for Cloud Run replicas. Selecting Firestore explicitly makes service and credential failures visible to the caller. BigQuery is an optional, expiring cache for batch results.

Crustdata signs the timestamp and exact webhook body. Only a genuine change from a bound company or person entity watch opens a review. Test deliveries and baseline samples can exercise the receiver without creating reviews. The ledger stores an event before publication. Pub/Sub carries its opaque ID. The consumer authenticates Google's push identity and commits deduplication together with the review update. [Crustdata entity watcher](https://docs.crustdata.com/watcher-docs/company/entity.md) · [Pub/Sub push authentication](https://cloud.google.com/pubsub/docs/authenticate-push-subscriptions)

Rekor publication uses a dedicated signing key and a salted commitment that the firm can open privately. Verification uses Sigstore's signed bundle, an independently trusted log root and the firm's public key. A verified receipt dates the commitment. The decision and its witnesses retain their own evidentiary meaning. [Sigstore blob signing](https://docs.sigstore.dev/cosign/signing/signing_with_blobs/) · [Sigstore verification](https://docs.sigstore.dev/cosign/verifying/verify/)
