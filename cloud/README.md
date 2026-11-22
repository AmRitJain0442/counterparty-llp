# Ledger, watch and receipt setup

Choose local SQLite for a single host with a persistent disk. Use Firestore for a Cloud Run deployment so the case API and every watch replica see the same transactions. These are operator-run setup paths. The application opens existing cloud services with Application Default Credentials (ADC).

## Local ledger

From the repository root, install `requirements.txt` and start the case API with the repository launcher. The default database is `.local/ledger.sqlite3`. Set `SQLITE_PATH` to an absolute file on persistent storage to move it. Restrict access to the service account or workstation user. Use SQLite's online backup API or the `sqlite3` shell's `.backup` command for a consistent backup.

```python
from backend.storage import get_case, list_cases, save_case

case = save_case({"id": "local-example", "verdict": "HELD", "as_of": "2026-01-01"})
assert get_case(case["id"]) == case
assert case in list_cases()
```

The local watch receiver uses the same signed webhook contract and reopens the case in SQLite. Start the narrow receiver with `python -m uvicorn backend.watch:app --host 127.0.0.1 --port 8081`. Keep `WATCH_TRANSPORT=local` for this path. The normal FastAPI application also mounts the router.

## Cloud Run and Firestore

The shell examples use Bash and Google Cloud CLI. Set `PROJECT` to a billing-enabled project, `REGION` to the intended data region and `IMAGE` to the Artifact Registry URL of the application image built from the root Dockerfile. Use explicit project flags when working with multiple projects.

With an existing Artifact Registry repository, build and push the image from the repository root.

```bash
gcloud auth configure-docker "$REGION-docker.pkg.dev"
docker build --platform=linux/amd64 -t "$IMAGE" .
docker push "$IMAGE"
```

```bash
export APP_SA="counterparty-app@$PROJECT.iam.gserviceaccount.com"
export WATCH_SA="counterparty-watch@$PROJECT.iam.gserviceaccount.com"
export PUSH_SA="counterparty-push@$PROJECT.iam.gserviceaccount.com"
export TOPIC="projects/$PROJECT/topics/case-watch"
export SUB="projects/$PROJECT/subscriptions/case-watch-push"

gcloud services enable --project="$PROJECT" run.googleapis.com firestore.googleapis.com \
  pubsub.googleapis.com iam.googleapis.com secretmanager.googleapis.com
```

Use **IAM & Admin → Service Accounts** to create these three identities. Grant the app and watch runtime identities `roles/datastore.user` in the dedicated ledger project. Grant the deployer `iam.serviceAccounts.actAs` on the identities it attaches. The push identity only needs to identify deliveries to the callback application. [Firestore IAM](https://cloud.google.com/firestore/docs/security/iam) · [Push authentication](https://cloud.google.com/pubsub/docs/authenticate-push-subscriptions)

Use an existing Firestore Native database or create it once in the chosen location. The collection names are `counterparty_cases`, `counterparty_watch_bindings` and `counterparty_watch_events`. The recovery query uses the default single-field index on `state`. Exempt the stored decision JSON from indexing. A Firestore document, including its receipt bundle and review fields, must fit within 1 MiB. [Firestore quotas](https://cloud.google.com/firestore/quotas) · [Field index configuration](https://cloud.google.com/sdk/gcloud/reference/firestore/indexes/fields/update)

```bash
gcloud firestore databases create --project="$PROJECT" --database='(default)' \
  --location="$REGION" --type=firestore-native
gcloud firestore indexes fields update decision_json --project="$PROJECT" \
  --database='(default)' --collection-group=counterparty_cases --disable-indexes

gcloud run deploy counterparty-app --project="$PROJECT" --region="$REGION" \
  --image="$IMAGE" --service-account="$APP_SA" --no-allow-unauthenticated \
  --set-env-vars="LEDGER_BACKEND=firestore,GOOGLE_CLOUD_PROJECT=$PROJECT"
```

Grant the intended staff group `roles/run.invoker` on the case service. For a named database, set `FIRESTORE_DATABASE` consistently on the case service, watch service and operator commands. A private workstation can use `gcloud auth application-default login` with a ledger-authorized account. Cloud Run uses its attached service identity. The case service's provider entitlements and credentials are described in the [application guide](../README.md).

## Watch delivery through Pub/Sub

1. Create the topic. Grant the watch identity permission to publish on that topic. Grant the Pub/Sub service agent permission to mint ID tokens for the dedicated push identity.

   ```bash
   gcloud pubsub topics create case-watch --project="$PROJECT"
   gcloud pubsub topics add-iam-policy-binding case-watch --project="$PROJECT" \
     --member="serviceAccount:$WATCH_SA" --role=roles/pubsub.publisher
   NUMBER=$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')
   gcloud beta services identity create --project="$PROJECT" --service=pubsub.googleapis.com
   gcloud iam service-accounts add-iam-policy-binding "$PUSH_SA" --project="$PROJECT" \
     --member="serviceAccount:service-$NUMBER@gcp-sa-pubsub.iam.gserviceaccount.com" \
     --role=roles/iam.serviceAccountTokenCreator
   ```

2. In **Secret Manager**, create `crustdata-watch-signing-key` with the exact Crustdata API key used for this watch. Preserve its bytes without a trailing newline. Grant `roles/secretmanager.secretAccessor` on this secret to `WATCH_SA`. The provider uses that key to sign `timestamp + "." + raw_body`. The application accepts a five-minute clock skew. [Crustdata entity watcher](https://docs.crustdata.com/watcher-docs/company/entity.md)

3. Deploy the watch-only ASGI application as the public callback target. Its two handlers authenticate the provider signature and the Google ID token respectively. Staff case reads and paid collection stay on the private case service. Set the push audience to the full push URL and leave the wrapped message envelope enabled. [Cloud Run callback access](https://cloud.google.com/run/docs/authenticating/public) · [Authenticated push subscriptions](https://cloud.google.com/pubsub/docs/create-push-subscription)

   ```bash
   gcloud run deploy counterparty-watch --project="$PROJECT" --region="$REGION" \
     --image="$IMAGE" --service-account="$WATCH_SA" --no-invoker-iam-check \
     --command=uvicorn --args=backend.watch:app,--host,0.0.0.0,--port,8080 \
     --set-secrets=WATCH_WEBHOOK_SECRET=crustdata-watch-signing-key:1 \
     --set-env-vars="LEDGER_BACKEND=firestore,GOOGLE_CLOUD_PROJECT=$PROJECT,WATCH_TRANSPORT=pubsub,PUBSUB_TOPIC=$TOPIC,PUBSUB_SUBSCRIPTION=$SUB,PUBSUB_PUSH_SERVICE_ACCOUNT=$PUSH_SA"
   WATCH_URL=$(gcloud run services describe counterparty-watch --project="$PROJECT" \
     --region="$REGION" --format='value(status.url)')
   AUD="$WATCH_URL/watch/pubsub"
   gcloud run services update counterparty-watch --project="$PROJECT" --region="$REGION" \
     --update-env-vars="PUBSUB_PUSH_AUDIENCE=$AUD"
   gcloud pubsub subscriptions create case-watch-push --project="$PROJECT" --topic="$TOPIC" \
     --push-endpoint="$AUD" --push-auth-token-audience="$AUD" --push-auth-service-account="$PUSH_SA" \
     --ack-deadline=60 --min-retry-delay=10s --max-retry-delay=600s
   ```

4. File the case. Register a **case-scoped person or company entity watch** using the separately authorized provider workflow. Select the 30-day refresh SLA, inline results and a webhook notification to `$WATCH_URL/watch/webhook`. The receiver accepts up to 2 MiB per delivery. Bind the returned watch ID to the case from a trusted shell. The entire entity set on that watch must be relevant to this case. [Person entity watches](https://docs.crustdata.com/watcher-docs/person/entity.md) · [Inline payloads](https://docs.crustdata.com/watcher-docs/payload-delivery.md)

   ```bash
   export LEDGER_BACKEND=firestore GOOGLE_CLOUD_PROJECT="$PROJECT"
   python -m backend.watch bind "$WATCH_ID" "$CASE_ID"
   ```

5. Use the provider's test-delivery action to confirm signature and routing. A test or free baseline returns `{"status":"ignored"}`. A changed record queues an opaque event ID. The authenticated subscriber acknowledges with 204 after committing the review. Re-read the case to see `watch_review.status`, its count and the delivery time.

### Redelivery and recovery

A duplicate notification or a second Pub/Sub message for the same event shares one durable event key. A 503 on publishing leaves the event pending. Recovery requires the same ledger, transport and topic configuration and the topic publisher permission. Run this command again while it reports a full batch. It can also be run by a scheduled operator job.

```bash
export LEDGER_BACKEND=firestore GOOGLE_CLOUD_PROJECT="$PROJECT"
export WATCH_TRANSPORT=pubsub PUBSUB_TOPIC="$TOPIC"
python -m backend.watch drain --limit 100
```

For a 409, check the provider watch ID and server-side binding. For a push 401 or 403, check the subscription's token audience, push identity and fully qualified subscription name. A push 503 leaves Pub/Sub responsible for redelivery. Monitor unacknowledged message age and the ledger's pending events. If subscription retention expires after a confirmed publish, republish the existing `counterparty_watch_events` document ID with `gcloud pubsub topics publish "$TOPIC" --message="$EVENT_ID"`. Keep event rows for as long as the case can receive redeliveries. [Pub/Sub retry policy](https://cloud.google.com/pubsub/docs/subscription-retry-policy)

## Optional BigQuery batch cache

SQLite mode caches batches locally in the ledger database. Firestore mode without `BIGQUERY_CACHE_TABLE` returns cache misses and skips writes. Setting `BIGQUERY_CACHE_TABLE` selects BigQuery independently of the ledger. BigQuery errors propagate so the caller can handle unavailable data explicitly.

Create a private dataset in the chosen location, then run the supplied table definition. Grant the cache writer `roles/bigquery.dataEditor` on the dataset. Readers can use `roles/bigquery.dataViewer`. Both need `roles/bigquery.jobUser` on the job project. Set the environment variables on each batch reader or writer. [Parameterized queries](https://cloud.google.com/bigquery/docs/parameterized-queries) · [Partition expiration](https://cloud.google.com/bigquery/docs/managing-partitioned-tables)

```bash
gcloud services enable bigquery.googleapis.com --project="$PROJECT"
bq --project_id="$PROJECT" --location="$REGION" mk --dataset "$PROJECT:counterparty"
sed "s/PROJECT_ID/$PROJECT/g" cloud/bigquery.sql | \
  bq --project_id="$PROJECT" --location="$REGION" query --use_legacy_sql=false
export BIGQUERY_CACHE_TABLE="$PROJECT.counterparty.batch_cache" BIGQUERY_LOCATION="$REGION"
```

```python
from backend.storage import get_cached_batch, put_cached_batch

key = "firm-a/estate/company-111/headcount-aggregate-v1"
put_cached_batch(key, [{"employees": 25}], as_of="2026-01-31", ttl_seconds=86400)
hit = get_cached_batch(key)
# {"mode": "CACHED", "as_of": "2026-01-31", "data": [{"employees": 25}]}
```

Cache minimized, authorized results. Include the permission scope and query version in each key. Reads enforce the entry TTL immediately. A local write sweeps expired SQLite entries. BigQuery expires storage partitions after 31 days for a maximum logical TTL of 30 days.

## Optional Rekor receipt

Every case receives a local salted SHA-256 commitment. To publish one selected case, use a trusted operator workstation or signer job with ledger access. Install a verified **Cosign 3** binary. Configure an organization signing key and its independently pinned public key. A local Cosign-encrypted key needs `COSIGN_PASSWORD` from the operator's secret store. A KMS URI can also be used with a KMS-capable Cosign build. Supply a Sigstore `trusted_root.json` authenticated through TUF or your organization's trusted distribution. Archive the matching public key and trust-root versions with the private receipt. [Cosign installation](https://docs.sigstore.dev/cosign/system_config/installation/) · [Trust roots and signing configuration](https://docs.sigstore.dev/cosign/system_config/custom_components/)

```bash
export REKOR_PUBLIC_KEY=/secure/trust/firm.pub
export REKOR_TRUSTED_ROOT=/secure/trust/trusted_root.json
export REKOR_SIGNING_KEY=/secure/signing/firm.key
export REKOR_ENABLED=1
python -m backend.receipts publish "$CASE_ID"
python -m backend.receipts verify "$CASE_ID" --require-rekor
```

`REKOR_COSIGN` can point to a specific executable. To use a private or staging installation, set `REKOR_SIGNING_CONFIG` to a trusted signing configuration containing that Rekor and an RFC 3161 timestamp authority, and configure their matching trust root. The default signing configuration comes from Sigstore. Verification runs offline and needs the public key, root and bundle. It requires the artifact signature, a logged entry with a signed checkpoint and inclusion proof, and a signed timestamp.

The only artifact Cosign receives is a 32-byte salted commitment. The log can disclose the signing public key, signature, time and an opaque hash. Keep the salt, original finding, identifiers and evidence inside the authorized case ledger. A signing timeout can follow a successful append. Retrying the stored receipt keeps the same commitment and may produce another public signature. The local decision acquires `REKOR_VERIFIED` only after successful verification and a conditional ledger write. [Signing blobs](https://docs.sigstore.dev/cosign/signing/signing_with_blobs/) · [Timestamp verification](https://docs.sigstore.dev/cosign/verifying/timestamps/)

To verify published receipts through the private case API, build the optional verifier image. Set `VERIFIER_IMAGE` to its own Artifact Registry tag. Supply the public key and authenticated root as versioned, read-only mounts accessible to `APP_SA`. The API only needs the verification materials. The signer retains the private key. The build accepts a verified image digest in `COSIGN_IMAGE` for a release-pinned deployment. [Cosign image and verification instructions](https://docs.sigstore.dev/cosign/system_config/installation/)

```bash
docker build --platform=linux/amd64 -f cloud/Dockerfile.receipts \
  --build-arg COUNTERPARTY_IMAGE="$IMAGE" -t "$VERIFIER_IMAGE" .
docker push "$VERIFIER_IMAGE"
gcloud run services update counterparty-app --project="$PROJECT" --region="$REGION" \
  --image="$VERIFIER_IMAGE" \
  --update-secrets=/var/run/cp-key/firm.pub=receipt-public-key:1,/var/run/cp-trust/root.json=sigstore-trusted-root:1 \
  --update-env-vars=REKOR_PUBLIC_KEY=/var/run/cp-key/firm.pub,REKOR_TRUSTED_ROOT=/var/run/cp-trust/root.json
```

## Local verification

```bash
python -m unittest discover -s cloud/tests -v
```

Set `REKOR_COSIGN` to run the offline signed-bundle and tamper checks with Cosign. The fixture contains synthetic data and public verification material from an ephemeral local log and timestamp authority. To exercise the same watch tests against a running **loopback** Firestore emulator, set `COUNTERPARTY_TEST_FIRESTORE=1` and `FIRESTORE_EMULATOR_HOST=127.0.0.1:8085`. The tests use fresh emulator project IDs, signed local Google-format tokens and a simulated Pub/Sub publisher.

On 2026-11-22 the infrastructure suite passed on Python 3.12. Separate local checks covered recovery from a fresh process, Firestore transaction retries, publishing and receiving the opaque ID through Google's Pub/Sub emulator, and Cosign 3.1.4 signing against a loopback log and timestamp authority. The BigQuery tests check SDK parameters and result decoding with a test client. Managed IAM, Cloud Run deployment and BigQuery query execution require validation in the target project.
