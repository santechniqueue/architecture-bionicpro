CREATE TABLE IF NOT EXISTS telemetry_events (
    event_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          VARCHAR(255) NOT NULL,
    prosthesis_id    VARCHAR(255) NOT NULL,
    event_type       VARCHAR(100) NOT NULL,
    signal_value     DOUBLE PRECISION NOT NULL,
    battery_level    REAL NOT NULL,
    response_time_ms INTEGER NOT NULL,
    event_ts         TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX idx_telemetry_user_id ON telemetry_events(user_id);
CREATE INDEX idx_telemetry_prosthesis_id ON telemetry_events(prosthesis_id);
CREATE INDEX idx_telemetry_event_ts ON telemetry_events(event_ts);
CREATE INDEX idx_telemetry_user_ts ON telemetry_events(user_id, event_ts);
