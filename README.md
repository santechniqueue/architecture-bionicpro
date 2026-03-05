# Задание 1. Повышение безопасности системы

[Схема C4](Task1/C4_Containers_To_Be.drawio)

# Задание 2. Разработка сервиса отчётов

[Схема C4](Task2/C4_Containers_To_Be.drawio)

## Проверка

```bash
docker compose up -d --build
```

Проверяем, что скрипт нагенерил данных:

**CRM:**
```bash
docker compose exec crm_db psql -U crm_user -d crm_db -c "SELECT user_id, full_name FROM customers;"
```

**OLTP:**
```bash
docker compose exec oltp_db psql -U oltp_user -d oltp_db -c "SELECT user_id, count(*) FROM telemetry_events GROUP BY user_id;"
```

Если не нагенерил, то вызываем вручную:
```bash
docker compose run --rm data-generator
```

Ожидаемый вывод:
```
Connecting to CRM database...
Connecting to OLTP database...
--- Populating CRM ---
CRM: inserted 4 customers with prostheses.
--- Populating OLTP (telemetry) ---
OLTP: inserted ~36000 telemetry events.
Done!
```

Зайти на http://localhost:8082 (admin/admin) - выбрать DAG, у всех Tasks должен быть статус "success":

![success](Task2/tasks_success01.png)


Ручной запуск DAG:
```bash
docker compose exec airflow airflow dags trigger bionicpro_etl_reports
```

Проверить статус:
```bash
docker compose exec airflow airflow dags list-runs -d bionicpro_etl_reports
```

Проверить витрину в ClickHouse

```bash
docker compose exec clickhouse clickhouse-client --query "SELECT user_id, prosthesis_id, report_date, total_events, avg_response_time_ms FROM bionicpro.report_mart ORDER BY report_date DESC LIMIT 10"
```

1. Открыть http://localhost:3000
2. Нажать **Login**, авторизоваться как `prothetic1`
3. Нажать **Download Report** - скачается CSV-файл с данными только этого пользователя 
4. Залогиниться как `prothetic2`, скачать отчет, в нём будут только данные `prothetic2`. Данные других пользователей недоступны.

# Задание 3. Снижение нагрузки на базу данных

## Проверка

1. Открыть http://localhost:3000
2. Войти как `prothetic1`
3. Нажать `Download Report` 
4. Браузер скачает CSV-файл через `CDN` (`localhost:8084`). В теле ответа будет "generated"
5. Нажать `Download Report` повторно. В теле ответа будет "cache"
6. Удалить кэш вручную:
   ```commandline
    curl -s http://localhost:8001/reports/cache -X DELETE
   ```
7. Скачать заново отчет. В теле ответа снова будет "generated"
8. Зайти на http://localhost:9001 (minioadmin/minioadmin). В бакете bionicpro-reports должны быть сгенерированные для пользователей отчеты.

# Задание 4. Повышение оперативности и стабильности работы CRM

## Проверка

```bash
docker exec architecture-bionicpro-crm_db-1 psql -U crm_user -d crm_db -c "SHOW wal_level;"
```
Ожидаемый результат: `logical`

```bash
docker exec architecture-bionicpro-crm_db-1 psql -U crm_user -d crm_db -c \
  "SELECT relname, relreplident FROM pg_class WHERE relname IN ('customers','orders','prostheses');"
```
Ожидаемый результат: `f` (full) для всех трёх таблиц.

```bash
docker exec architecture-bionicpro-kafka-1 kafka-topics --bootstrap-server localhost:9092 --list
```
Ожидаемый результат: в списке должны быть:
- `crm.public.customers`
- `crm.public.orders`
- `crm.public.prostheses`

Проверить, что данные есть в топиках:

```bash
docker exec architecture-bionicpro-kafka-1 kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic crm.public.customers \
  --from-beginning --max-messages 2
```
Ожидаемый результат: JSON-записи с полями `user_id`, `full_name`, `__op`, `__deleted` и т.д.


```bash
curl -s http://localhost:8083/connectors/crm-pg-connector/status | python3 -m json.tool
```
Ожидаемый результат: `"state": "RUNNING"` для коннектора и тасок.

```bash
docker exec architecture-bionicpro-clickhouse-1 clickhouse-client --query \
  "SELECT count() FROM bionicpro.cdc_customers"
```
Ожидаемый результат: число > 0 (по 4 пользователя из data-generator).

```bash
docker exec architecture-bionicpro-clickhouse-1 clickhouse-client --query \
  "SELECT count() FROM bionicpro.cdc_orders"
```

```bash
docker exec architecture-bionicpro-clickhouse-1 clickhouse-client --query \
  "SELECT count() FROM bionicpro.cdc_prostheses"
```

Проверить денормализованное представление:

```bash
docker exec architecture-bionicpro-clickhouse-1 clickhouse-client --query \
  "SELECT user_id, full_name, prosthesis_id, prosthesis_model, status
   FROM bionicpro.crm_customers_cdc
   ORDER BY user_id"
```
Ожидаемый результат: 

```
prothetic1      Prothetic One   BP-2025-0001    BionicHand Pro X1       maintenance
prothetic2      Prothetic Two   BP-2025-0002    BionicHand Pro X2       maintenance
prothetic3      Prothetic Three BP-2025-0003    BionicArm Advanced A3   in_use
prothetic3      Prothetic Three BP-2025-0004    BionicForearm F1        maintenance
```

### Проверка CDC

1. Запомнить текущее состояние:
   ```bash
   docker exec architecture-bionicpro-clickhouse-1 clickhouse-client --query \
     "SELECT user_id, full_name FROM bionicpro.cdc_customers FINAL ORDER BY user_id"
   ```

2. `UPDATE`
   ```bash
   docker exec architecture-bionicpro-crm_db-1 psql -U crm_user -d crm_db -c \
     "UPDATE customers SET full_name = 'Prothetic One UPDATED', updated_at = now() WHERE user_id = 'prothetic1';"
   ```

   Подождать 5–10 секунд и проверить ClickHouse:

   ```bash
   docker exec architecture-bionicpro-clickhouse-1 clickhouse-client --query \
     "SELECT user_id, full_name, cdc_op, cdc_source_ts
      FROM bionicpro.cdc_customers FINAL
      WHERE user_id = 'prothetic1'"
   ```
   Ожидаемый результат: `prothetic1      Prothetic One UPDATED   u       2026-03-05 16:05:17.140`.

   Проверить, что обновление видно в денормализованном представлении:

   ```bash
   docker exec architecture-bionicpro-clickhouse-1 clickhouse-client --query \
     "SELECT user_id, full_name, prosthesis_model
      FROM bionicpro.crm_customers_cdc
      WHERE user_id = 'prothetic1'"
   ```
   Ожидаемый результат: `prothetic1      Prothetic One UPDATED   BionicHand Pro X1`.

3. `INSERT`

   ```bash
   docker exec architecture-bionicpro-crm_db-1 psql -U crm_user -d crm_db -c \
     "INSERT INTO customers (user_id, full_name, email, phone) VALUES ('test.cdc', 'CDC Test User', 'cdc@test.com', '+7-000-000-0000');"
   ```

   Через 5–10 секунд:

   ```bash
   docker exec architecture-bionicpro-clickhouse-1 clickhouse-client --query \
     "SELECT * FROM bionicpro.cdc_customers FINAL WHERE user_id = 'test.cdc'"
   ```
   Ожидаемый результат - новая запись вида
   ```
   4       test.cdc        CDC Test User   cdc@test.com    +7-000-000-0000 2026-03-05 16:07:53.093361      2026-03-05 16:07:53.093361      c       2026-03-05 16:07:53.094 0       2026-03-05 16:07:56
   ```

4. `DELETE` как `soft-delete`

   ```bash
   docker exec architecture-bionicpro-crm_db-1 psql -U crm_user -d crm_db -c \
     "DELETE FROM customers WHERE user_id = 'test.cdc';"
   ```

   Через 5–10 секунд:
   
   ```bash
   docker exec architecture-bionicpro-clickhouse-1 clickhouse-client --query \
     "SELECT user_id, is_deleted, cdc_op FROM bionicpro.cdc_customers FINAL WHERE user_id = 'test.cdc'"
   ```
   Ожидаемый результат: `is_deleted = 1`, `cdc_op = 'd'`.

   Запись не появится в `crm_customers_cdc`:
   
   ```bash
   docker exec architecture-bionicpro-clickhouse-1 clickhouse-client --query \
     "SELECT count() FROM bionicpro.crm_customers_cdc WHERE user_id = 'test.cdc'"
   ```
   Ожидаемый результат: `0`.

docker exec architecture-bionicpro-keycloak-1 \
  /opt/keycloak/bin/kc.sh export \
  --dir ./tmp/export --realm reports-realm

### Airflow DAG работает с CDC-витриной

Триггерим DAG:
   ```bash
   docker exec $(docker ps -qf "ancestor=apache/airflow:2.10.4-python3.11") \
     airflow dags trigger bionicpro_etl_reports
   ```

Ждём 1–2 минуты и проверяем:

   ```bash
   docker exec architecture-bionicpro-clickhouse-1 clickhouse-client --query \
     "SELECT user_id, prosthesis_id, report_date, total_events, prosthesis_model
      FROM bionicpro.report_mart FINAL
      ORDER BY user_id, report_date DESC
      LIMIT 10"
   ```
Ожидаемый результат: строки с заполненными `prosthesis_model` (данные из CDC, не batch).

### Разделение потоков операций

Проверить, что Airflow больше НЕ обращается к CRM:

   ```bash
   docker exec $(docker ps -qf "ancestor=apache/airflow:2.10.4-python3.11") \
     airflow dags list-import-errors
   ```
   Не должно быть ошибок.

   ```bash
   docker exec $(docker ps -qf "ancestor=apache/airflow:2.10.4-python3.11") \
     env | grep CRM
   ```
   Ожидаемый результат: пусто (переменная `AIRFLOW_CONN_CRM_POSTGRES` удалена).

Проверить, что в DAG нет задачи extract_crm_customers:
   
   ```bash
   docker exec $(docker ps -qf "ancestor=apache/airflow:2.10.4-python3.11") \
     airflow tasks list bionicpro_etl_reports
   ```

   Ожидаемый результат: только 3 задачи:
   - `extract_telemetry`
  - `build_report_mart`
  - `invalidate_report_cache`

   Задачи `extract_crm_customers` нет.

Проверить активные соединения к CRM:

   ```bash
   docker exec architecture-bionicpro-crm_db-1 psql -U crm_user -d crm_db -c \
     "SELECT usename, application_name, state, query
      FROM pg_stat_activity
      WHERE datname = 'crm_db' AND pid <> pg_backend_pid();"
   ```
   Ожидаемый результат: единственное подключение - от `debezium`.
