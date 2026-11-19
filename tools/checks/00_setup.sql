-- title: Schemas in c360_bank and what they hold (Lakeflow internal __materialization tables excluded)
SELECT table_schema, COUNT(*) AS tables, SUM(IF(table_type = 'STREAMING_TABLE', 1, 0)) AS streaming_tables,
       SUM(IF(table_type = 'MATERIALIZED_VIEW', 1, 0)) AS materialized_views, SUM(IF(table_type = 'MANAGED', 1, 0)) AS managed_tables,
       SUM(IF(table_type = 'FOREIGN', 1, 0)) AS lakebase_synced
FROM c360_bank.information_schema.tables
WHERE table_schema NOT IN ('information_schema') AND table_name NOT LIKE '\_\_materialization%'
GROUP BY table_schema ORDER BY table_schema
;
-- title: Volumes
SELECT volume_schema, volume_name, volume_type FROM c360_bank.information_schema.volumes ORDER BY 1, 2
