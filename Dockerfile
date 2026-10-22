FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
ENV PORT=8000
EXPOSE 8000
CMD ["gunicorn", "-w", "1", "--threads", "8", "-t", "0", "-b", "0.0.0.0:8000", "app:app"]
