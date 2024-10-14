FROM python:3.9-slim

# Install necessary packages
RUN apt-get update && apt-get install -y wget unzip

# Install ngrok
RUN wget https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz && \
    tar xvzf ngrok-v3-stable-linux-amd64.tgz -C /usr/local/bin && \
    rm ngrok-v3-stable-linux-amd64.tgz

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
ENV PORT=8000

# Copy the startup script
COPY start.sh /start.sh
RUN chmod +x /start.sh

CMD ["/start.sh"]
