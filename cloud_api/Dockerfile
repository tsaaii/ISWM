FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py .
# one worker with many threads: the live stream holds a connection open per viewer
CMD exec gunicorn --bind :$PORT --workers 1 --threads 16 --timeout 0 main:app
