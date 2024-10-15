# Docker Instructions for CustomGPT with Twilio Voice and OpenAI Realtime API

This document provides step-by-step instructions on how to build and run the Docker container for the CustomGPT with Twilio Voice and OpenAI Realtime API project.

## Prerequisites

- Docker installed on your machine
- Git (to clone the repository)
- A Twilio account with a phone number that has Voice capabilities
- An OpenAI account with an API key and Realtime API access
- A CustomGPT API key
- ngrok authtoken (this will be used within the container)

## Building the Docker Image

1. Clone the repository:
   ```
   git clone https://github.com/adorosario/openai-realtime-with-customgpt-poc.git
   cd openai-realtime-with-customgpt-poc
   ```

2. Create a `.env` file in the project root:
   ```
   cp .env.example .env
   ```
   Edit the `.env` file and add your API keys and other configuration:
   ```
   OPENAI_API_KEY=your_openai_api_key
   CUSTOMGPT_API_KEY=your_customgpt_api_key
   NGROK_AUTHTOKEN=your_ngrok_authtoken
   NGROK_DOMAIN=your_ngrok_static_domain
   ```

3. Build the Docker image:
   ```
   docker build -t customgpt-twilio-openai .
   ```

## Running the Docker Container

1. Run the Docker container:
   ```
   sudo docker run -d \
      -p 5050:5050 \
      --env-file .env \
      -v "$(pwd):/app" \
      --name customgpt-twilio-openai-container \
      customgpt-twilio-openai \
      /bin/bash -c "chmod +x /app/start.sh && /app/start.sh"
   ```

   This command:
   - Runs the container in detached mode (`-d`)
   - Maps port 5050 from the container to port 5050 on your host (`-p 5050:5050`)
   - Uses the environment variables from the `.env` file
   - Names the container `customgpt-twilio-openai-container`

2. Get the ngrok URL:
   The container automatically starts ngrok. To get the ngrok URL, check the container logs:
   ```
   docker logs customgpt-twilio-openai-container
   ```
   Look for a line that says something like "Forwarding http://xxxx.ngrok.io -> http://localhost:5050". This is your public URL. 
   
   Quick tip: It is recommended that you create a [static domain](https://dashboard.ngrok.com/domains) in ngrok and set `NGROK_DOMAIN` in your `.env` file to prevent it from changing on each run.  

## Configuring Twilio

1. Log in to your [Twilio Console](https://console.twilio.com/).

2. Go to **Phone Numbers** > **Manage** > **Active Numbers** and click on the phone number you want to use for this project.

3. In the Phone Number configuration settings:
   - Set the first **A call comes in** dropdown to **Webhook**
   - Paste your ngrok Forwarding URL (obtained from the container logs) followed by `/incoming-call?project_id={customgpt_project_id}`
   - The full URL should look like: `https://xxxx.ngrok.io/incoming-call?project_id={customgpt_project_id}`
   - Replace `{customgpt_project_id}` with your actual CustomGPT project ID
   - Click **Save configuration**

## Testing the Application

1. Ensure your Docker container is running.

2. Call the Twilio phone number you configured.

3. After the introduction, you should be able to talk to the AI Assistant.

## Stopping and Removing the Container

1. Stop the container:
   ```
   docker stop customgpt-twilio-openai-container
   ```

2. Remove the container:
   ```
   docker rm customgpt-twilio-openai-container
   ```

## Troubleshooting

- If you can't access the application through the ngrok URL, ensure that your Docker container is running and check the logs for any error messages:
  ```
  docker logs customgpt-twilio-openai-container
  ```
- If you need to make changes to the code, rebuild the Docker image and run a new container.
- If the ngrok URL changes (which can happen if the container restarts), you'll need to update your Twilio configuration with the new URL.

## Additional Notes

- The ngrok URL will change each time the container is restarted. Always check the container logs for the current URL.
- Always keep your API keys and tokens private and never commit them to version control.
- For production deployment, consider using a more permanent solution for exposing your application to the internet, such as a cloud-hosted solution or a reverse proxy.
- This application does not require direct use of Twilio API credentials (ACCOUNT_SID and AUTH_TOKEN) within the container. All Twilio integration is handled through the webhook URL configured in the Twilio Console.