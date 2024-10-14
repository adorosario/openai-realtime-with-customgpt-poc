#!/bin/bash

# Start your application
gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app -b "0.0.0.0:${PORT}" &

# Start ngrok
ngrok http ${PORT} &

# Keep the container running
tail -f /dev/null
