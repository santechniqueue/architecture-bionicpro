CREATE TABLE IF NOT EXISTS customers (
    id           SERIAL PRIMARY KEY,
    user_id      VARCHAR(255) NOT NULL UNIQUE,
    full_name    VARCHAR(500) NOT NULL,
    email        VARCHAR(255),
    phone        VARCHAR(50),
    created_at   TIMESTAMP NOT NULL DEFAULT now(),
    updated_at   TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS orders (
    id           SERIAL PRIMARY KEY,
    customer_id  INTEGER NOT NULL REFERENCES customers(id),
    order_date   DATE NOT NULL,
    delivery_date DATE,
    status       VARCHAR(50) NOT NULL DEFAULT 'new',
    total_amount NUMERIC(12, 2),
    created_at   TIMESTAMP NOT NULL DEFAULT now(),
    updated_at   TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS prostheses (
    id              SERIAL PRIMARY KEY,
    order_id        INTEGER NOT NULL REFERENCES orders(id),
    prosthesis_id   VARCHAR(255) NOT NULL UNIQUE,
    model           VARCHAR(255) NOT NULL,
    type            VARCHAR(100) NOT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX idx_customers_user_id ON customers(user_id);
CREATE INDEX idx_customers_updated_at ON customers(updated_at);
CREATE INDEX idx_orders_customer_id ON orders(customer_id);
CREATE INDEX idx_orders_updated_at ON orders(updated_at);
CREATE INDEX idx_prostheses_order_id ON prostheses(order_id);
