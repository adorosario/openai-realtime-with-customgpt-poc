#!/bin/bash

# Check if NGROK_AUTHTOKEN is set
if [ -z "$NGROK_AUTHTOKEN" ]; then
    echo "Error: NGROK_AUTHTOKEN is not set. Please make sure it's in your .env file."
    exit 1
fi

# Configure ngrok
ngrok config add-authtoken $NGROK_AUTHTOKEN

# Start your application
gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app -b "0.0.0.0:${PORT}" &

# Start ngrok

if [ -z "$NGROK_DOMAIN" ]; then
  ngrok http "${PORT}" --log=stdout > ngrok.log &
else
  ngrok http --url=$NGROK_DOMAIN "${PORT}" --log=stdout > ngrok.log &
fi

# Display ngrok logs and keep the container running
tail -f ngrok.log
