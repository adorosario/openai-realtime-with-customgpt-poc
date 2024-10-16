# OpenAI Realtime API with CustomGPT RAG and Twilio Voice

This application demonstrates how to use [Twilio Voice](https://www.twilio.com/docs/voice) and [Media Streams](https://www.twilio.com/docs/voice/media-streams), and [OpenAI's Realtime API](https://platform.openai.com/docs/) to make a phone call to speak with an [CustomGPT RAG](https://customgpt.ai/) Knowledgebase. 

The application opens websockets with the OpenAI Realtime API and Twilio, and sends voice audio from one to the other to enable a two-way conversation. It uses OpenAI's function calling to call CustomGPT to get the ground-truth information from the RAG (retrieval augmented generation). 

See [here](https://www.twilio.com/en-us/voice-ai-assistant-openai-realtime-api-python) for a tutorial overview of the code.

This application uses the following Twilio products in conjuction with OpenAI's Realtime API:
- Voice (and TwiML, Media Streams)
- Phone Numbers

## Demo Video

[![Watch the video](https://cdn.loom.com/sessions/thumbnails/d0d4f4490a4349cdab860febce26d1bc-aa0a9773bdb9dca7-full-play.gif)](https://www.loom.com/share/d0d4f4490a4349cdab860febce26d1bc)

[Click here to watch the full demo video](https://www.loom.com/share/d0d4f4490a4349cdab860febce26d1bc)

## Prerequisites

To use the app, you will  need:

- **A Twilio account.** You can sign up for a free trial [here](https://www.twilio.com/try-twilio) and [buy a number](https://help.twilio.com/articles/223135247-How-to-Search-for-and-Buy-a-Twilio-Phone-Number-from-Console) to purchase a phone number.
- **An OpenAI account and an OpenAI API Key.** You can sign up [here](https://platform.openai.com/).
- **A CustomGPT API Key** You can sign up [here](https://app.customgpt.ai) 

## Docker Setup
The easiest way to setup is using Docker. Please see [step-by-step instructions](./DOCKER.md). 

## Local Setup

There are 4 required steps and 1 optional step to get the app up-and-running locally for development and testing:
1. Run ngrok or another tunneling solution to expose your local server to the internet for testing. Download ngrok [here](https://ngrok.com/).
2. (optional) Create and use a virtual environment
3. Install the packages
4. Twilio setup
5. Update the .env file

### Open an ngrok tunnel
When developing & testing locally, you'll need to open a tunnel to forward requests to your local development server. These instructions use ngrok.

Open a Terminal and run:
```
ngrok http 5050
```

Once the tunnel has been opened, copy the `Forwarding` URL. It will look something like: `https://[your-ngrok-subdomain].ngrok.app`. You will need this when configuring your Twilio number setup.

Note that the `ngrok` command above forwards to a development server running on port `5050`, which is the default port configured in this application. If you override the `PORT`, you will need to update the `ngrok` command accordingly.

Keep in mind that each time you run the `ngrok http` command, a new URL will be created, and you'll need to update it everywhere it is referenced below. It is recommended to set a static domain in ngrok. 

### (Optional) Create and use a virtual environment

To reduce cluttering your global Python environment on your machine, you can create a virtual environment. On your command line, enter:

```
python3 -m venv env
source env/bin/activate
```

### Install required packages

In the terminal (with the virtual environment, if you set it up) run:
```
pip install -r requirements.txt
```

### Twilio setup

#### Point a Phone Number to your ngrok URL
In the [Twilio Console](https://console.twilio.com/), go to **Phone Numbers** > **Manage** > **Active Numbers** and click on the additional phone number you purchased for this app in the **Prerequisites**.

In your Phone Number configuration settings, update the first **A call comes in** dropdown to **Webhook**, and paste your ngrok forwarding URL (referenced above), followed by `/incoming-call?project_id={customgpt_project_id}`. For example, `https://[your-ngrok-subdomain].ngrok.app/incoming-call?project_id={customgpt_project_id}`. Then, click **Save configuration**.

### Update the .env file

Copy the `.env.example` file to `.env`:

```
cp .env.example .env
```

In the .env file, update the various keys from the **Prerequisites**.

## Run the app
Once ngrok is running, dependencies are installed, Twilio is configured properly, and the `.env` is set up, run the dev server with the following command:
```
gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app
```

## Test the app
With the development server running, call the phone number you purchased in the **Prerequisites**. After the introduction, you should be able to talk to the AI Assistant. Have fun!
