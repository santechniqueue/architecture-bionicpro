CREATE TABLE IF NOT EXISTS bionicpro.kafka_cdc_customers (
    id             Int32,
    user_id        String,
    full_name      String,
    email          Nullable(String),
    phone          Nullable(String),
    created_at     Int64,
    updated_at     Int64,
    __op           String,
    __source_ts_ms Int64,
    __deleted      String
) ENGINE = Kafka()
SETTINGS
    kafka_broker_list = 'kafka:9092',
    kafka_topic_list = 'crm.public.customers',
    kafka_group_name = 'clickhouse_customers_consumer',
    kafka_format = 'JSONEachRow',
    kafka_num_consumers = 1,
    kafka_max_block_size = 65536,
    kafka_skip_broken_messages = 10;

CREATE TABLE IF NOT EXISTS bionicpro.cdc_customers (
    id            Int32,
    user_id       String,
    full_name     String,
    email         String DEFAULT '',
    phone         String DEFAULT '',
    created_at    DateTime64(6),
    updated_at    DateTime64(6),
    cdc_op        String,
    cdc_source_ts DateTime64(3),
    is_deleted    UInt8,
    ingested_at   DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(cdc_source_ts)
ORDER BY (id)
SETTINGS index_granularity = 8192;

CREATE MATERIALIZED VIEW IF NOT EXISTS bionicpro.mv_cdc_customers
TO bionicpro.cdc_customers AS
SELECT
    id,
    user_id,
    full_name,
    coalesce(email, '')                          AS email,
    coalesce(phone, '')                          AS phone,
    fromUnixTimestamp64Micro(created_at)          AS created_at,
    fromUnixTimestamp64Micro(updated_at)          AS updated_at,
    __op                                         AS cdc_op,
    fromUnixTimestamp64Milli(__source_ts_ms)      AS cdc_source_ts,
    if(__deleted = 'true', 1, 0)                 AS is_deleted,
    now()                                        AS ingested_at
FROM bionicpro.kafka_cdc_customers;

CREATE TABLE IF NOT EXISTS bionicpro.kafka_cdc_orders (
    id             Int32,
    customer_id    Int32,
    order_date     Int32,
    delivery_date  Nullable(Int32),
    status         String,
    total_amount   Nullable(String),
    created_at     Int64,
    updated_at     Int64,
    __op           String,
    __source_ts_ms Int64,
    __deleted      String
) ENGINE = Kafka()
SETTINGS
    kafka_broker_list = 'kafka:9092',
    kafka_topic_list = 'crm.public.orders',
    kafka_group_name = 'clickhouse_orders_consumer',
    kafka_format = 'JSONEachRow',
    kafka_num_consumers = 1,
    kafka_max_block_size = 65536,
    kafka_skip_broken_messages = 10;

CREATE TABLE IF NOT EXISTS bionicpro.cdc_orders (
    id            Int32,
    customer_id   Int32,
    order_date    Date,
    delivery_date Nullable(Date),
    status        String,
    total_amount  Decimal(12, 2) DEFAULT 0,
    created_at    DateTime64(6),
    updated_at    DateTime64(6),
    cdc_op        String,
    cdc_source_ts DateTime64(3),
    is_deleted    UInt8,
    ingested_at   DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(cdc_source_ts)
ORDER BY (id)
SETTINGS index_granularity = 8192;

CREATE MATERIALIZED VIEW IF NOT EXISTS bionicpro.mv_cdc_orders
TO bionicpro.cdc_orders AS
SELECT
    id,
    customer_id,
    addDays(toDate('1970-01-01'), order_date)    AS order_date,
    if(isNotNull(delivery_date),
       toNullable(addDays(toDate('1970-01-01'), assumeNotNull(delivery_date))),
       toNullable(toDate('1970-01-01')))         AS delivery_date,
    status,
    toDecimal64(coalesce(total_amount, '0'), 2)  AS total_amount,
    fromUnixTimestamp64Micro(created_at)          AS created_at,
    fromUnixTimestamp64Micro(updated_at)          AS updated_at,
    __op                                         AS cdc_op,
    fromUnixTimestamp64Milli(__source_ts_ms)      AS cdc_source_ts,
    if(__deleted = 'true', 1, 0)                 AS is_deleted,
    now()                                        AS ingested_at
FROM bionicpro.kafka_cdc_orders;

CREATE TABLE IF NOT EXISTS bionicpro.kafka_cdc_prostheses (
    id             Int32,
    order_id       Int32,
    prosthesis_id  String,
    model          String,
    type           String,
    created_at     Int64,
    __op           String,
    __source_ts_ms Int64,
    __deleted      String
) ENGINE = Kafka()
SETTINGS
    kafka_broker_list = 'kafka:9092',
    kafka_topic_list = 'crm.public.prostheses',
    kafka_group_name = 'clickhouse_prostheses_consumer',
    kafka_format = 'JSONEachRow',
    kafka_num_consumers = 1,
    kafka_max_block_size = 65536,
    kafka_skip_broken_messages = 10;

CREATE TABLE IF NOT EXISTS bionicpro.cdc_prostheses (
    id            Int32,
    order_id      Int32,
    prosthesis_id String,
    model         String,
    type          String,
    created_at    DateTime64(6),
    cdc_op        String,
    cdc_source_ts DateTime64(3),
    is_deleted    UInt8,
    ingested_at   DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(cdc_source_ts)
ORDER BY (id)
SETTINGS index_granularity = 8192;

CREATE MATERIALIZED VIEW IF NOT EXISTS bionicpro.mv_cdc_prostheses
TO bionicpro.cdc_prostheses AS
SELECT
    id,
    order_id,
    prosthesis_id,
    model,
    type,
    fromUnixTimestamp64Micro(created_at)          AS created_at,
    __op                                          AS cdc_op,
    fromUnixTimestamp64Milli(__source_ts_ms)       AS cdc_source_ts,
    if(__deleted = 'true', 1, 0)                  AS is_deleted,
    now()                                         AS ingested_at
FROM bionicpro.kafka_cdc_prostheses;

CREATE OR REPLACE VIEW bionicpro.crm_customers_cdc AS
SELECT
    c.user_id                                               AS user_id,
    c.full_name                                             AS full_name,
    c.email                                                 AS email,
    c.phone                                                 AS phone,
    p.prosthesis_id                                         AS prosthesis_id,
    p.model                                                 AS prosthesis_model,
    o.order_date                                            AS order_date,
    o.delivery_date                                         AS delivery_date,
    o.status                                                AS status,
    greatest(c.ingested_at, o.ingested_at, p.ingested_at)   AS ingested_at
FROM (SELECT * FROM bionicpro.cdc_customers FINAL WHERE is_deleted = 0) AS c
INNER JOIN (SELECT * FROM bionicpro.cdc_orders FINAL WHERE is_deleted = 0) AS o
    ON o.customer_id = c.id
INNER JOIN (SELECT * FROM bionicpro.cdc_prostheses FINAL WHERE is_deleted = 0) AS p
    ON p.order_id = o.id;
