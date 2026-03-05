#!/usr/bin/env python3

import os
import random
import uuid
from datetime import datetime, timedelta

import psycopg2

CRM_DSN = os.getenv(
    "CRM_DATABASE_URL",
    "postgresql://crm_user:crm_password@localhost:5434/crm_db",
)
OLTP_DSN = os.getenv(
    "OLTP_DATABASE_URL",
    "postgresql://oltp_user:oltp_password@localhost:5435/oltp_db",
)

USERS = [
    {
        "user_id": "prothetic1",
        "full_name": "Prothetic One",
        "email": "prothetic1@example.com",
        "phone": "+7-900-111-1111",
    },
    {
        "user_id": "prothetic2",
        "full_name": "Prothetic Two",
        "email": "prothetic2@example.com",
        "phone": "+7-900-222-2222",
    },
    {
        "user_id": "prothetic3",
        "full_name": "Prothetic Three",
        "email": "prothetic3@example.com",
        "phone": "+7-900-333-3333",
    },
]

PROSTHESIS_MODELS = [
    "BionicHand Pro X1",
    "BionicHand Pro X2",
    "BionicArm Lite A1",
    "BionicArm Advanced A3",
    "BionicForearm F1",
]

PROSTHESIS_TYPES = ["hand", "forearm", "arm"]

EVENT_TYPES = ["grip", "release", "rotate", "flex", "extend", "calibration", "idle"]

ORDER_STATUSES = ["delivered", "in_use", "maintenance"]

TELEMETRY_DAYS = 30
EVENTS_PER_DAY = 200


def populate_crm(conn):
    cur = conn.cursor()

    cur.execute("SELECT count(*) FROM customers")
    if cur.fetchone()[0] > 0:
        print("CRM: data already exists, skipping.")
        return

    prosthesis_counter = 0

    for user in USERS:
        cur.execute(
            """
            INSERT INTO customers (user_id, full_name, email, phone, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                user["user_id"],
                user["full_name"],
                user["email"],
                user["phone"],
                datetime(2025, 1, 1) + timedelta(days=random.randint(0, 60)),
                datetime.now(),
            ),
        )
        customer_id = cur.fetchone()[0]

        num_prostheses = random.randint(1, 2)
        for j in range(num_prostheses):
            prosthesis_counter += 1
            order_date = datetime(2025, 2, 1) + timedelta(days=random.randint(0, 90))
            delivery_date = order_date + timedelta(days=random.randint(30, 60))

            cur.execute(
                """
                INSERT INTO orders (customer_id, order_date, delivery_date, status,
                                    total_amount, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    customer_id,
                    order_date.date(),
                    delivery_date.date(),
                    random.choice(ORDER_STATUSES),
                    round(random.uniform(500000, 2000000), 2),
                    order_date,
                    datetime.now(),
                ),
            )
            order_id = cur.fetchone()[0]

            prosthesis_id = f"BP-{2025}-{prosthesis_counter:04d}"
            model = random.choice(PROSTHESIS_MODELS)
            ptype = random.choice(PROSTHESIS_TYPES)

            cur.execute(
                """
                INSERT INTO prostheses (order_id, prosthesis_id, model, type, created_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (order_id, prosthesis_id, model, ptype, delivery_date),
            )

    conn.commit()
    print(f"CRM: inserted {len(USERS)} customers with prostheses.")


def populate_oltp(conn, crm_conn):
    cur = conn.cursor()

    cur.execute("SELECT count(*) FROM telemetry_events")
    if cur.fetchone()[0] > 0:
        print("OLTP: data already exists, skipping.")
        return

    crm_cur = crm_conn.cursor()
    crm_cur.execute(
        """
        SELECT c.user_id, p.prosthesis_id
        FROM customers c
        JOIN orders o ON o.customer_id = c.id
        JOIN prostheses p ON p.order_id = o.id
        """
    )
    assignments = crm_cur.fetchall()

    if not assignments:
        print("OLTP: no prosthesis assignments found in CRM. Run CRM generation first.")
        return

    now = datetime.now()
    total_events = 0
    batch = []
    batch_size = 1000

    for user_id, prosthesis_id in assignments:
        for day_offset in range(TELEMETRY_DAYS):
            day_start = now - timedelta(days=TELEMETRY_DAYS - day_offset)
            day_start = day_start.replace(hour=7, minute=0, second=0, microsecond=0)

            for _ in range(EVENTS_PER_DAY):
                event_ts = day_start + timedelta(
                    seconds=random.randint(0, 16 * 3600)
                )
                event_type = random.choice(EVENT_TYPES)

                signal_value = random.gauss(0.5, 0.15)
                signal_value = max(0.0, min(1.0, signal_value))

                hours_since_start = (event_ts - day_start).total_seconds() / 3600
                battery_level = max(0.1, 1.0 - (hours_since_start / 20) + random.gauss(0, 0.05))
                battery_level = max(0.0, min(1.0, battery_level))

                if random.random() < 0.9:
                    response_time_ms = random.randint(20, 95)
                else:
                    response_time_ms = random.randint(100, 300)

                batch.append((
                    str(uuid.uuid4()),
                    user_id,
                    prosthesis_id,
                    event_type,
                    round(signal_value, 6),
                    round(battery_level, 4),
                    response_time_ms,
                    event_ts,
                ))
                total_events += 1

                if len(batch) >= batch_size:
                    _insert_telemetry_batch(cur, batch)
                    batch = []

    if batch:
        _insert_telemetry_batch(cur, batch)

    conn.commit()
    print(f"OLTP: inserted {total_events} telemetry events.")


def _insert_telemetry_batch(cur, batch):
    args_str = ",".join(
        cur.mogrify(
            "(%s, %s, %s, %s, %s, %s, %s, %s)", row
        ).decode("utf-8")
        for row in batch
    )
    cur.execute(
        f"""
        INSERT INTO telemetry_events
            (event_id, user_id, prosthesis_id, event_type,
             signal_value, battery_level, response_time_ms, event_ts)
        VALUES {args_str}
        """
    )


def main():
    print("Connecting to CRM database...")
    crm_conn = psycopg2.connect(CRM_DSN)
    print("Connecting to OLTP database...")
    oltp_conn = psycopg2.connect(OLTP_DSN)

    try:
        print("\n--- Populating CRM ---")
        populate_crm(crm_conn)

        print("\n--- Populating OLTP (telemetry) ---")
        populate_oltp(oltp_conn, crm_conn)

        print("\nDone!")
    finally:
        crm_conn.close()
        oltp_conn.close()


if __name__ == "__main__":
    main()
