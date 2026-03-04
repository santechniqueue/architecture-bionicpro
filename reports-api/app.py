import base64
import csv
import io
import json
import os

import clickhouse_connect
from fastapi import FastAPI, Header, HTTPException, Response, status

app = FastAPI(title="reports-api")

CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "clickhouse")
CLICKHOUSE_PORT = int(os.getenv("CLICKHOUSE_PORT", "8123"))


def _get_ch_client():
    return clickhouse_connect.get_client(host=CLICKHOUSE_HOST, port=CLICKHOUSE_PORT)


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


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "reports-api"}


@app.get("/reports")
async def get_report(authorization: str | None = Header(default=None)):
    user_id = _extract_user_id(authorization)

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
    writer.writerow([
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
    ])
    for row in result.result_rows:
        writer.writerow(row)

    csv_bytes = buf.getvalue().encode("utf-8")

    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="report-{user_id}.csv"',
        },
    )
