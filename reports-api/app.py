import base64
import csv
import io
import json
import logging
import os

import boto3
import clickhouse_connect
from botocore.exceptions import ClientError
from fastapi import FastAPI, Header, HTTPException, Response, status
from fastapi.responses import JSONResponse

app = FastAPI(title="reports-api")
logger = logging.getLogger("reports-api")

CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "clickhouse")
CLICKHOUSE_PORT = int(os.getenv("CLICKHOUSE_PORT", "8123"))

S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "http://minio:9000")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY", "minioadmin")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY", "minioadmin")
S3_BUCKET = os.getenv("S3_BUCKET", "bionicpro-reports")

CDN_BASE_URL = os.getenv("CDN_BASE_URL", "http://localhost:8084")


def _get_ch_client():
    return clickhouse_connect.get_client(host=CLICKHOUSE_HOST, port=CLICKHOUSE_PORT)


def _get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT_URL,
        aws_access_key_id=S3_ACCESS_KEY,
        aws_secret_access_key=S3_SECRET_KEY,
        region_name="us-east-1",
    )


def _ensure_bucket(s3):
    try:
        s3.head_bucket(Bucket=S3_BUCKET)
    except ClientError:
        s3.create_bucket(Bucket=S3_BUCKET)
        policy = json.dumps({
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {"AWS": ["*"]},
                "Action": ["s3:GetObject"],
                "Resource": [f"arn:aws:s3:::{S3_BUCKET}/*"],
            }],
        })
        s3.put_bucket_policy(Bucket=S3_BUCKET, Policy=policy)


def _decode_jwt_payload(token: str) -> dict:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid JWT format")
    payload = parts[1]
    padding = "=" * (-len(payload) % 4)
    decoded = base64.urlsafe_b64decode(payload + padding)
    return json.loads(decoded.decode("utf-8"))


def _extract_user_id(authorization: str) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )
    token = authorization.removeprefix("Bearer ")
    try:
        claims = _decode_jwt_payload(token)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        ) from exc

    user_id = claims.get("preferred_username") or claims.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token does not contain user identity",
        )
    return user_id


def _s3_key(user_id: str) -> str:
    return f"reports/{user_id}/report-{user_id}.csv"


def _cdn_url(user_id: str) -> str:
    return f"{CDN_BASE_URL}/{_s3_key(user_id)}"


def _report_exists_in_s3(s3, user_id: str) -> bool:
    try:
        s3.head_object(Bucket=S3_BUCKET, Key=_s3_key(user_id))
        return True
    except ClientError:
        return False


CSV_COLUMNS = [
    "report_date",
    "prosthesis_id",
    "prosthesis_model",
    "total_events",
    "avg_signal_value",
    "min_signal_value",
    "max_signal_value",
    "avg_battery_level",
    "min_battery_level",
    "avg_response_time_ms",
    "max_response_time_ms",
    "events_over_100ms",
    "unique_event_types",
    "first_event_ts",
    "last_event_ts",
]


def _generate_report_csv(user_id: str) -> bytes:
    ch = _get_ch_client()
    result = ch.query(
        """
        SELECT
            report_date,
            prosthesis_id,
            prosthesis_model,
            total_events,
            avg_signal_value,
            min_signal_value,
            max_signal_value,
            avg_battery_level,
            min_battery_level,
            avg_response_time_ms,
            max_response_time_ms,
            events_over_100ms,
            unique_event_types,
            first_event_ts,
            last_event_ts
        FROM bionicpro.report_mart FINAL
        WHERE user_id = %(user_id)s
        ORDER BY report_date DESC, prosthesis_id
        LIMIT 1000
        """,
        parameters={"user_id": user_id},
    )

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(CSV_COLUMNS)
    for row in result.result_rows:
        writer.writerow(row)

    return buf.getvalue().encode("utf-8")


def _upload_to_s3(s3, user_id: str, csv_bytes: bytes) -> None:
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=_s3_key(user_id),
        Body=csv_bytes,
        ContentType="text/csv",
        ContentDisposition=f'attachment; filename="report-{user_id}.csv"',
    )


@app.on_event("startup")
async def on_startup():
    s3 = _get_s3_client()
    _ensure_bucket(s3)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "reports-api"}


@app.get("/reports")
async def get_report(authorization: str | None = Header(default=None)):
    user_id = _extract_user_id(authorization)

    s3 = _get_s3_client()
    _ensure_bucket(s3)

    if _report_exists_in_s3(s3, user_id):
        logger.info("Report for %s found in S3, returning CDN link", user_id)
        return JSONResponse(content={
            "source": "cache",
            "report_url": _cdn_url(user_id),
        })

    logger.info("Report for %s not in S3, generating from ClickHouse", user_id)
    csv_bytes = _generate_report_csv(user_id)

    _upload_to_s3(s3, user_id, csv_bytes)
    logger.info("Report for %s uploaded to S3", user_id)

    return JSONResponse(content={
        "source": "generated",
        "report_url": _cdn_url(user_id),
    })


@app.delete("/reports/cache")
async def invalidate_cache(authorization: str | None = Header(default=None)):
    s3 = _get_s3_client()

    paginator = s3.get_paginator("list_objects_v2")
    objects_to_delete = []

    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix="reports/"):
        for obj in page.get("Contents", []):
            objects_to_delete.append({"Key": obj["Key"]})

    if objects_to_delete:
        for i in range(0, len(objects_to_delete), 1000):
            batch = objects_to_delete[i : i + 1000]
            s3.delete_objects(
                Bucket=S3_BUCKET,
                Delete={"Objects": batch},
            )

    deleted_count = len(objects_to_delete)
    logger.info("Cache invalidated: deleted %d report(s) from S3", deleted_count)

    return {"status": "ok", "deleted": deleted_count}
