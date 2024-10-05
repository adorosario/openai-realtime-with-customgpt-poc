import os
import json
import base64
import asyncio
import websockets
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse
from fastapi.websockets import WebSocketDisconnect
from twilio.twiml.voice_response import VoiceResponse, Connect, Say, Stream
from dotenv import load_dotenv
from customgpt_client import CustomGPT
import uuid

load_dotenv()

project_id = 43538
CustomGPT.api_key = os.getenv('CUSTOMGPT_API_KEY')
# Configuration
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY') # requires OpenAI Realtime API Access
PORT = int(os.getenv('PORT', 5050))
SYSTEM_MESSAGE = (
    "You are a helpful AI assistant"
    "If you dont know the answer of the user query, use get_additional_context tool for more context and answer. Dont say sorry immediately always try to answer with get_additional_context."
    "If the user asks some information that you cant say use get_additional_context like personal information or information on data. get_additional_context will get you more context to the users"
)
SYSTEM_MESSAGE_2 = (
    "You are a helpful AI assistant designed to answer questions using only the additional context provided. Start the conversation with 'Hello how can i help you today'"
    "For every user query, immediately use the get_additional_context function to obtain information. "
    "Do not use your own knowledge base to answer questions. "
    "Always base your responses solely on the information returned by get_additional_context. "
    "If get_additional_context returns information indicating it's unable to answer or provide details, "
    "respond only with: 'Sorry! I can't provide an answer to your question.' "
    "Do not elaborate or use any other information beyond what get_additional_context provides. "
    "If get_additional_context provides relevant information, incorporate it into your response. "
    "Be concise and directly address the user's query based only on the additional context. "
    "Do not mention the process of using get_additional_context in your responses to the user."
)

VOICE = 'alloy'
LOG_EVENT_TYPES = [
    'response.content.done', 'rate_limits.updated', 'response.done',
    'input_audio_buffer.committed', 'input_audio_buffer.speech_stopped',
    'input_audio_buffer.speech_started', 'session.created'
]

app = FastAPI()

if not OPENAI_API_KEY:
    raise ValueError('Missing the OpenAI API key. Please set it in the .env file.')


@app.get("/", response_class=HTMLResponse)
async def index_page():
    return "<h1>Twilio Media Stream Server is running!</h1>"

@app.api_route("/incoming-call", methods=["GET", "POST"])
async def handle_incoming_call(request: Request):
    """Handle incoming call and return TwiML response to connect to Media Stream."""
    session_id = uuid.uuid4()
    print(session_id)
    response = VoiceResponse()
    response.pause(length=1)
    host = request.url.hostname
    connect = Connect()
    connect.stream(url=f'wss://{host}/media-stream/{session_id}')
    response.append(connect)
    return HTMLResponse(content=str(response), media_type="application/xml")

@app.websocket("/media-stream/{session_id}")
async def handle_media_stream(websocket: WebSocket, session_id):
    """Handle WebSocket connections between Twilio and OpenAI."""
    print("Client connected")
    print(websocket.url)
    print(session_id)
    await websocket.accept()

    async with websockets.connect(
        'wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01',
        extra_headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "OpenAI-Beta": "realtime=v1"
        }
    ) as openai_ws:
        await send_session_update(openai_ws)
        stream_sid = None
        async def receive_from_twilio():
            """Receive audio data from Twilio and send it to the OpenAI Realtime API."""
            nonlocal stream_sid
            try:
                async for message in websocket.iter_text():
                    data = json.loads(message)
                    if data['event'] == 'media' and openai_ws.open:
                        audio_append = {
                            "type": "input_audio_buffer.append",
                            "audio": data['media']['payload']
                        }
                        await openai_ws.send(json.dumps(audio_append))
                    elif data['event'] == 'start':
                        stream_sid = data['start']['streamSid']
                        print(f"Incoming stream has started {stream_sid}")
            except WebSocketDisconnect:
                print("Client disconnected.")
                if openai_ws.open:
                    await openai_ws.close()

        async def send_to_twilio():
            """Receive events from the OpenAI Realtime API, send audio back to Twilio."""
            nonlocal stream_sid
            try:
                async for openai_message in openai_ws:
                    response = json.loads(openai_message)
                    if response['type'] in LOG_EVENT_TYPES:
                        print(f"Received event: {response['type']}", response)
                    if response['type'] == 'session.updated':
                        print("Session updated successfully:", response)
                    if response['type'] == 'response.audio.delta' and response.get('delta'):
                        # Audio from OpenAI
                        try:
                            audio_payload = base64.b64encode(base64.b64decode(response['delta'])).decode('utf-8')
                            audio_delta = {
                                "event": "media",
                                "streamSid": stream_sid,
                                "media": {
                                    "payload": audio_payload
                                }
                            }
                            await websocket.send_json(audio_delta)
                        except Exception as e:
                            print(f"Error processing audio data: {e}")
                    elif response['type'] == 'response.function_call_arguments.done':
                        function_name = response['name']
                        call_id = response['call_id']
                        arguments = json.loads(response['arguments'])
                        if function_name == 'get_additional_context':
                            result = get_additional_context(arguments['query'], session_id)
                            function_response = {
                                "type": "conversation.item.create",
                                "item": {
                                    "type": "function_call_output",
                                    "call_id": call_id,
                                    "output": result
                                }
                            }
                            await openai_ws.send(json.dumps(function_response))
                            await openai_ws.send(json.dumps({"type": "response.create"}))
            except Exception as e:
                print(f"Error in send_to_twilio: {e}")

        await asyncio.gather(receive_from_twilio(), send_to_twilio())

def get_additional_context(query, session_id):
    conversation  = CustomGPT.Conversation.send(project_id=project_id, session_id=session_id, prompt=query)
    print(conversation)
    return f"{conversation.parsed.data.openai_response}"

async def send_session_update(openai_ws):
    """Send session update to OpenAI WebSocket."""
    session_update = {
        "type": "session.update",
        "session": {
            "turn_detection": {
                "type": "server_vad",
                "threshold": 0.6,
                "prefix_padding_ms": 300,
                "silence_duration_ms": 500
            },
            "input_audio_format": "g711_ulaw",
            "output_audio_format": "g711_ulaw",
            "voice": VOICE,
            "instructions": SYSTEM_MESSAGE_2,
            "modalities": ["text", "audio"],
            "temperature": 0.6,
            "tools": [
                {
                    "type": "function",
                    "name": "get_additional_context",
                    "description": "Get the additional context to answer user query.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The users query payload"
                            }
                        },
                        "required": ["query"]
                    }
                }
            ]

        }
    }
    print('Sending session update:', json.dumps(session_update))
    await openai_ws.send(json.dumps(session_update))