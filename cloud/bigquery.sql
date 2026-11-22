-- Replace PROJECT_ID and create the counterparty dataset in the data region first.
CREATE TABLE IF NOT EXISTS `PROJECT_ID.counterparty.batch_cache` (
  cache_key STRING NOT NULL,
  as_of STRING NOT NULL,
  data_json STRING NOT NULL,
  stored_at TIMESTAMP NOT NULL,
  expires_at TIMESTAMP NOT NULL
)
PARTITION BY DATE(stored_at)
CLUSTER BY cache_key
OPTIONS (partition_expiration_days = 31, require_partition_filter = TRUE);
