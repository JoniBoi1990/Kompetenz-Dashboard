FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Logo must be mounted as volume at /app/static/logo.png
RUN mkdir -p /app/static

CMD ["python", "app.py"]
