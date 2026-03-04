#!/usr/bin/env python3
"""
Generates realistic test data for CRM and OLTP PostgreSQL databases.

Usage:
    pip install psycopg2-binary
    python generate_data.py

Or via Docker:
    docker compose run --rm data-generator
"""

import os
import random
import uuid
from datetime import datetime, timedelta

import psycopg2

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CRM_DSN = os.getenv(
    "CRM_DATABASE_URL",
    "postgresql://crm_user:crm_password@localhost:5434/crm_db",
)
OLTP_DSN = os.getenv(
    "OLTP_DATABASE_URL",
    "postgresql://oltp_user:oltp_password@localhost:5435/oltp_db",
)

# Users matching Keycloak realm (prothetic_user role)
USERS = [
    {
        "user_id": "prothetic1",
        "full_name": "Иванов Алексей Петрович",
        "email": "prothetic1@bionicpro.ru",
        "phone": "+7-900-111-1111",
    },
    {
        "user_id": "prothetic2",
        "full_name": "Сидорова Мария Ивановна",
        "email": "prothetic2@bionicpro.ru",
        "phone": "+7-900-222-2222",
    },
    {
        "user_id": "alex.johnson",
        "full_name": "Alex Johnson",
        "email": "alex.johnson@example.com",
        "phone": "+7-900-333-3333",
    },
    {
        "user_id": "john.doe",
        "full_name": "John Doe",
        "email": "john.doe@example.com",
        "phone": "+7-900-444-4444",
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

# How many days of telemetry to generate
TELEMETRY_DAYS = 30
# Events per prosthesis per day
EVENTS_PER_DAY = 200


# ---------------------------------------------------------------------------
# CRM data generation
# ---------------------------------------------------------------------------

def populate_crm(conn):
    cur = conn.cursor()

    # Check if data already exists
    cur.execute("SELECT count(*) FROM customers")
    if cur.fetchone()[0] > 0:
        print("CRM: data already exists, skipping.")
        return

    prosthesis_counter = 0

    for user in USERS:
        # Insert customer
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

        # Each user has 1-2 prostheses (orders)
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


# ---------------------------------------------------------------------------
# OLTP telemetry data generation
# ---------------------------------------------------------------------------

def populate_oltp(conn, crm_conn):
    cur = conn.cursor()

    # Check if data already exists
    cur.execute("SELECT count(*) FROM telemetry_events")
    if cur.fetchone()[0] > 0:
        print("OLTP: data already exists, skipping.")
        return

    # Get prosthesis assignments from CRM
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
                    seconds=random.randint(0, 16 * 3600)  # 7:00 - 23:00
                )
                event_type = random.choice(EVENT_TYPES)

                # Simulate realistic signal values
                signal_value = random.gauss(0.5, 0.15)
                signal_value = max(0.0, min(1.0, signal_value))

                # Battery drains through the day
                hours_since_start = (event_ts - day_start).total_seconds() / 3600
                battery_level = max(0.1, 1.0 - (hours_since_start / 20) + random.gauss(0, 0.05))
                battery_level = max(0.0, min(1.0, battery_level))

                # Response time: mostly <100ms, some spikes
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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

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
