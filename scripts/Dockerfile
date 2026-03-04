FROM python:3.13-slim

WORKDIR /app

RUN pip install --no-cache-dir psycopg2-binary==2.9.10

COPY generate_data.py .

CMD ["python", "generate_data.py"]
