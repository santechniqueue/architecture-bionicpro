"""
ETL DAG: Extract data from CRM (PostgreSQL) and OLTP (PostgreSQL),
transform and load into ClickHouse OLAP data mart.

Schedule: daily at 03:00 UTC
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.providers.http.hooks.http import HttpHook

import clickhouse_connect


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CLICKHOUSE_HOST = "clickhouse"
CLICKHOUSE_PORT = 8123

CRM_CONN_ID = "crm_postgres"          # Airflow Connection to CRM PostgreSQL
OLTP_CONN_ID = "oltp_postgres"        # Airflow Connection to OLTP PostgreSQL


default_args = {
    "owner": "bionicpro",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "start_date": datetime(2026, 1, 1),
}


def _get_ch_client():
    return clickhouse_connect.get_client(host=CLICKHOUSE_HOST, port=CLICKHOUSE_PORT)


# ---------------------------------------------------------------------------
# Extract: CRM customers
# ---------------------------------------------------------------------------

def extract_crm_customers(**context):
    """Extract customer + prosthesis data from CRM database."""
    hook = PostgresHook(postgres_conn_id=CRM_CONN_ID)

    sql = """
        SELECT
            c.user_id,
            c.full_name,
            c.email,
            c.phone,
            p.prosthesis_id,
            p.model          AS prosthesis_model,
            o.order_date,
            o.delivery_date,
            o.status
        FROM customers c
        JOIN orders o      ON o.customer_id = c.id
        JOIN prostheses p  ON p.order_id    = o.id
        WHERE o.updated_at >= %(since)s
           OR c.updated_at >= %(since)s
    """

    execution_date = context["ds"]
    since = (
        datetime.strptime(execution_date, "%Y-%m-%d") - timedelta(days=1)
    ).strftime("%Y-%m-%d")

    rows = hook.get_records(sql, parameters={"since": since})

    ch = _get_ch_client()
    if rows:
        ch.insert(
            "bionicpro.crm_customers",
            rows,
            column_names=[
                "user_id", "full_name", "email", "phone",
                "prosthesis_id", "prosthesis_model",
                "order_date", "delivery_date", "status",
            ],
        )

    return len(rows)


# ---------------------------------------------------------------------------
# Extract: OLTP telemetry
# ---------------------------------------------------------------------------

def extract_telemetry(**context):
    """Extract telemetry events from the OLTP PostgreSQL database."""
    hook = PostgresHook(postgres_conn_id=OLTP_CONN_ID)

    sql = """
        SELECT
            event_id::text,
            user_id,
            prosthesis_id,
            event_type,
            signal_value,
            battery_level,
            response_time_ms,
            event_ts
        FROM telemetry_events
        WHERE event_ts >= %(since)s
          AND event_ts <  %(until)s
    """

    execution_date = context["ds"]
    since = (
        datetime.strptime(execution_date, "%Y-%m-%d") - timedelta(days=1)
    ).strftime("%Y-%m-%d")
    until = execution_date

    rows = hook.get_records(sql, parameters={"since": since, "until": until})

    ch = _get_ch_client()
    if rows:
        ch.insert(
            "bionicpro.telemetry_raw",
            rows,
            column_names=[
                "event_id", "user_id", "prosthesis_id", "event_type",
                "signal_value", "battery_level", "response_time_ms", "event_ts",
            ],
        )

    return len(rows)


# ---------------------------------------------------------------------------
# Transform + Load: build the report data mart
# ---------------------------------------------------------------------------

def build_report_mart(**context):
    """
    Aggregate telemetry data per user/prosthesis/day and join with CRM data.
    Inserts into the report_mart ReplacingMergeTree — duplicates are handled
    automatically by ClickHouse on merge.
    """
    execution_date = context["ds"]
    since = (
        datetime.strptime(execution_date, "%Y-%m-%d") - timedelta(days=1)
    ).strftime("%Y-%m-%d")

    ch = _get_ch_client()

    sql = f"""
        INSERT INTO bionicpro.report_mart (
            user_id, prosthesis_id, report_date,
            full_name, email, prosthesis_model,
            total_events, avg_signal_value, min_signal_value, max_signal_value,
            avg_battery_level, min_battery_level,
            avg_response_time_ms, max_response_time_ms,
            events_over_100ms, unique_event_types,
            first_event_ts, last_event_ts
        )
        SELECT
            t.user_id,
            t.prosthesis_id,
            toDate(t.event_ts)                             AS report_date,
            coalesce(c.full_name, '')                      AS full_name,
            coalesce(c.email, '')                          AS email,
            coalesce(c.prosthesis_model, '')                AS prosthesis_model,
            count()                                        AS total_events,
            avg(t.signal_value)                            AS avg_signal_value,
            min(t.signal_value)                            AS min_signal_value,
            max(t.signal_value)                            AS max_signal_value,
            avg(t.battery_level)                           AS avg_battery_level,
            min(t.battery_level)                           AS min_battery_level,
            avg(t.response_time_ms)                        AS avg_response_time_ms,
            max(t.response_time_ms)                        AS max_response_time_ms,
            countIf(t.response_time_ms > 100)              AS events_over_100ms,
            uniqExact(t.event_type)                        AS unique_event_types,
            min(t.event_ts)                                AS first_event_ts,
            max(t.event_ts)                                AS last_event_ts
        FROM bionicpro.telemetry_raw AS t
        LEFT JOIN (
            SELECT user_id, prosthesis_id, full_name, email, prosthesis_model
            FROM bionicpro.crm_customers
            FINAL
        ) AS c ON c.user_id = t.user_id AND c.prosthesis_id = t.prosthesis_id
        WHERE toDate(t.event_ts) = toDate('{since}')
        GROUP BY
            t.user_id, t.prosthesis_id, report_date,
            full_name, email, prosthesis_model
    """

    ch.command(sql)


# ---------------------------------------------------------------------------
# DAG definition
# ---------------------------------------------------------------------------

with DAG(
    dag_id="bionicpro_etl_reports",
    default_args=default_args,
    description="ETL: CRM + Telemetry -> ClickHouse report mart",
    schedule_interval="0 3 * * *",   # daily at 03:00 UTC
    catchup=False,
    tags=["bionicpro", "etl", "reports"],
) as dag:

    task_extract_crm = PythonOperator(
        task_id="extract_crm_customers",
        python_callable=extract_crm_customers,
    )

    task_extract_telemetry = PythonOperator(
        task_id="extract_telemetry",
        python_callable=extract_telemetry,
    )

    task_build_mart = PythonOperator(
        task_id="build_report_mart",
        python_callable=build_report_mart,
    )

    # Extract tasks run in parallel, then mart is built
    [task_extract_crm, task_extract_telemetry] >> task_build_mart
