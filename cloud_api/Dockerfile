FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py .
# one worker (pictures pass through its memory) with many threads: each live stream holds one open
CMD exec gunicorn --bind :$PORT --workers 1 --threads 64 --timeout 0 main:app
