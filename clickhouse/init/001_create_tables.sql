CREATE DATABASE IF NOT EXISTS bionicpro;

-- Staging: raw telemetry data from OLTP PostgreSQL
CREATE TABLE IF NOT EXISTS bionicpro.telemetry_raw (
    event_id      String,
    user_id       String,
    prosthesis_id String,
    event_type    String,
    signal_value  Float64,
    battery_level Float32,
    response_time_ms UInt32,
    event_ts      DateTime,
    ingested_at   DateTime DEFAULT now()
) ENGINE = MergeTree()
ORDER BY (user_id, prosthesis_id, event_ts);

-- Staging: CRM customer data
CREATE TABLE IF NOT EXISTS bionicpro.crm_customers (
    user_id        String,
    full_name      String,
    email          String,
    phone          String,
    prosthesis_id  String,
    prosthesis_model String,
    order_date     Date,
    delivery_date  Date,
    status         String,
    ingested_at    DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(ingested_at)
ORDER BY (user_id, prosthesis_id);

-- Data mart: pre-aggregated report per user per prosthesis per day
CREATE TABLE IF NOT EXISTS bionicpro.report_mart (
    user_id              String,
    prosthesis_id        String,
    report_date          Date,
    full_name            String,
    email                String,
    prosthesis_model     String,
    total_events         UInt64,
    avg_signal_value     Float64,
    min_signal_value     Float64,
    max_signal_value     Float64,
    avg_battery_level    Float32,
    min_battery_level    Float32,
    avg_response_time_ms Float64,
    max_response_time_ms UInt32,
    events_over_100ms    UInt64,
    unique_event_types   UInt32,
    first_event_ts       DateTime,
    last_event_ts        DateTime,
    updated_at           DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (user_id, prosthesis_id, report_date);
