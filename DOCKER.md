# Docker Instructions

This document provides step-by-step instructions on how to build and run the Docker container for the OpenAI Realtime with Custom GPT POC project.

## Prerequisites

- Docker installed on your machine
- Git (to clone the repository)
- An ngrok account and authtoken (sign up at https://ngrok.com if you haven't already)

## Building the Docker Image

1. Clone the repository (if you haven't already):
   ```
   git clone https://github.com/adorosario/openai-realtime-with-customgpt-poc.git
   cd openai-realtime-with-customgpt-poc
   ```

2. Build the Docker image:
   ```
   docker build -t openai-realtime-customgpt .
   ```
   This command builds the Docker image and tags it as `openai-realtime-customgpt`.

## Running the Docker Container

1. Run the Docker container:
   ```
   docker run -d -p 8000:8000 -e NGROK_AUTHTOKEN=your_ngrok_auth_token --name openai-realtime-customgpt-container openai-realtime-customgpt
   ```
   Replace `your_ngrok_auth_token` with your actual ngrok authtoken.

   This command:
   - Runs the container in detached mode (`-d`)
   - Maps port 8000 from the container to port 8000 on your host (`-p 8000:8000`)
   - Sets the NGROK_AUTHTOKEN environment variable
   - Names the container `openai-realtime-customgpt-container`

2. Check if the container is running:
   ```
   docker ps
   ```
   You should see your container listed in the output.

3. View the container logs to get the ngrok URL:
   ```
   docker logs openai-realtime-customgpt-container
   ```
   Look for a line that says something like "Forwarding http://xxxx.ngrok.io -> http://localhost:8000". This is your public URL.

## Stopping and Removing the Container

1. Stop the container:
   ```
   docker stop openai-realtime-customgpt-container
   ```

2. Remove the container:
   ```
   docker rm openai-realtime-customgpt-container
   ```

## Troubleshooting

- If you can't access the application through the ngrok URL, ensure that your application is actually listening on `0.0.0.0` inside the container, not just `localhost`.
- If you need to make changes to the code, rebuild the Docker image and run a new container.
- For any persistent data or configurations, consider using Docker volumes.

## Additional Notes

- The free version of ngrok will generate a new URL each time you restart the container. If you need a stable URL, consider upgrading to a paid ngrok plan.
- Always keep your ngrok authtoken private and never commit it to version control.
- If you're deploying this in a production environment, consider using Docker Compose or Kubernetes for more robust orchestration.
