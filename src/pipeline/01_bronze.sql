-- Bronze: land each raw source file set as-is with Auto Loader (streaming tables).
-- Each file is processed once, so rerunning the pipeline adds no duplicate rows.

CREATE OR REFRESH STREAMING TABLE bronze_core_customers
COMMENT 'Raw core banking customer records (CSV), as landed'
AS SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${raw_root}/core_banking/customers', format => 'csv', header => true);

CREATE OR REFRESH STREAMING TABLE bronze_deposit_accounts
COMMENT 'Raw core banking deposit accounts (CSV), as landed'
AS SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${raw_root}/core_banking/deposit_accounts', format => 'csv', header => true);

CREATE OR REFRESH STREAMING TABLE bronze_loan_customers
COMMENT 'Raw loan system customer records (CSV), as landed'
AS SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${raw_root}/loans/customers', format => 'csv', header => true);

CREATE OR REFRESH STREAMING TABLE bronze_loans
COMMENT 'Raw loan accounts (CSV), as landed'
AS SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${raw_root}/loans/loans', format => 'csv', header => true);

CREATE OR REFRESH STREAMING TABLE bronze_card_customers
COMMENT 'Raw card system customer records (JSON lines), as landed'
AS SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${raw_root}/cards/customers', format => 'json');

CREATE OR REFRESH STREAMING TABLE bronze_card_accounts
COMMENT 'Raw card accounts (JSON lines), as landed'
AS SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${raw_root}/cards/card_accounts', format => 'json');

CREATE OR REFRESH STREAMING TABLE bronze_card_transactions
COMMENT 'Raw card transactions (JSON lines), as landed'
AS SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${raw_root}/cards/card_transactions', format => 'json');

CREATE OR REFRESH STREAMING TABLE bronze_digital_users
COMMENT 'Raw digital banking users (JSON lines), as landed'
AS SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${raw_root}/digital/users', format => 'json');

CREATE OR REFRESH STREAMING TABLE bronze_digital_events
COMMENT 'Raw digital banking events (JSON lines), as landed'
AS SELECT *, _metadata.file_path AS _source_file, current_timestamp() AS _ingested_at
FROM STREAM read_files('${raw_root}/digital/events', format => 'json');
