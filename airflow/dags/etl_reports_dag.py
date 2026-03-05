from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook

import boto3
import clickhouse_connect


CLICKHOUSE_HOST = "clickhouse"
CLICKHOUSE_PORT = 8123

OLTP_CONN_ID = "oltp_postgres"

S3_ENDPOINT_URL = "http://minio:9000"
S3_ACCESS_KEY = "minioadmin"
S3_SECRET_KEY = "minioadmin"
S3_BUCKET = "bionicpro-reports"

CDN_PURGE_URL = "http://cdn:8084/purge-cache"


default_args = {
    "owner": "bionicpro",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "start_date": datetime(2026, 1, 1),
}


def _get_ch_client():
    return clickhouse_connect.get_client(host=CLICKHOUSE_HOST, port=CLICKHOUSE_PORT)


def extract_telemetry(**context):
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


def build_report_mart(**context):
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
            coalesce(c.prosthesis_model, '')               AS prosthesis_model,
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
        LEFT JOIN bionicpro.crm_customers_cdc AS c
            ON c.user_id = t.user_id AND c.prosthesis_id = t.prosthesis_id
        WHERE toDate(t.event_ts) = toDate('{since}')
        GROUP BY
            t.user_id, t.prosthesis_id, report_date,
            full_name, email, prosthesis_model
    """

    ch.command(sql)


def invalidate_report_cache(**context):
    import urllib.request

    s3 = boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT_URL,
        aws_access_key_id=S3_ACCESS_KEY,
        aws_secret_access_key=S3_SECRET_KEY,
        region_name="us-east-1",
    )

    deleted = 0
    paginator = s3.get_paginator("list_objects_v2")
    try:
        for page in paginator.paginate(Bucket=S3_BUCKET, Prefix="reports/"):
            objects = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
            if objects:
                s3.delete_objects(
                    Bucket=S3_BUCKET,
                    Delete={"Objects": objects},
                )
                deleted += len(objects)
    except Exception as exc:
        print(f"S3 cleanup note: {exc}")

    print(f"Deleted {deleted} cached report(s) from S3")

    try:
        req = urllib.request.Request(CDN_PURGE_URL, method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            print(f"CDN purge response: {resp.status} {resp.read().decode()}")
    except Exception as exc:
        print(f"CDN purge note (non-critical): {exc}")

    return deleted


with DAG(
    dag_id="bionicpro_etl_reports",
    default_args=default_args,
    description="ETL: Telemetry batch + CDC CRM -> ClickHouse report mart",
    schedule_interval="0 3 * * *",
    catchup=False,
    tags=["bionicpro", "etl", "reports"],
) as dag:

    task_extract_telemetry = PythonOperator(
        task_id="extract_telemetry",
        python_callable=extract_telemetry,
    )

    task_build_mart = PythonOperator(
        task_id="build_report_mart",
        python_callable=build_report_mart,
    )

    task_invalidate_cache = PythonOperator(
        task_id="invalidate_report_cache",
        python_callable=invalidate_report_cache,
    )

    task_extract_telemetry >> task_build_mart >> task_invalidate_cache
