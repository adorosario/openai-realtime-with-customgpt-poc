FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

ENV PORT=8000

CMD gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app -b "0.0.0.0:${PORT}"