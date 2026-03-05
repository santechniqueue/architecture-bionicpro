#!/bin/sh
set -e

echo "Waiting for Debezium Connect to be fully ready..."
until curl -s http://debezium-connect:8083/connectors | grep -q '\['; do
  sleep 2
done
echo "Debezium Connect is ready."

echo "Registering CRM CDC connector..."
curl -s -X POST http://debezium-connect:8083/connectors \
  -H "Content-Type: application/json" \
  -d '{
    "name": "crm-pg-connector",
    "config": {
        "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
        "database.hostname": "crm_db",
        "database.port": "5432",
        "database.user": "crm_user",
        "database.password": "crm_password",
        "database.dbname": "crm_db",
        "topic.prefix": "crm",
        "table.include.list": "public.customers,public.orders,public.prostheses",
        "plugin.name": "pgoutput",
        "slot.name": "crm_debezium_slot",
        "publication.name": "crm_publication",
        "publication.autocreate.mode": "filtered",
        "snapshot.mode": "initial",
        "tombstones.on.delete": "false",
        "key.converter": "org.apache.kafka.connect.json.JsonConverter",
        "key.converter.schemas.enable": "false",
        "value.converter": "org.apache.kafka.connect.json.JsonConverter",
        "value.converter.schemas.enable": "false",
        "transforms": "unwrap",
        "transforms.unwrap.type": "io.debezium.transforms.ExtractNewRecordState",
        "transforms.unwrap.drop.tombstones": "true",
        "transforms.unwrap.delete.handling.mode": "rewrite",
        "transforms.unwrap.add.fields": "op,source.ts_ms",
        "decimal.handling.mode": "string"
    }
}'

echo ""
echo "Connector registered. Checking status..."
sleep 3
curl -s http://debezium-connect:8083/connectors/crm-pg-connector/status
echo ""
echo "Done."
