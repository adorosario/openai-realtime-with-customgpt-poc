import os
import json
import base64
import asyncio
import websockets
from fastapi import FastAPI, WebSocket, Request, WebSocketDisconnect, status
from fastapi.responses import HTMLResponse
from twilio.twiml.voice_response import VoiceResponse, Connect
from dotenv import load_dotenv
from customgpt_client import CustomGPT
import uuid
import logging
import time

load_dotenv()

project_id = 43538
CustomGPT.api_key = os.getenv('CUSTOMGPT_API_KEY')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
PORT = int(os.getenv('PORT', 5050))
SYSTEM_MESSAGE_2 = (
    "You are a helpful AI assistant designed to answer questions using only the additional context provided only respond to greeting without function call."
    "For every user query, evaluate the user_query clearly, clean it of any vocablary issues and elaborate it than pass detailed user_query immediately to get_additional_context function to obtain information. "
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
    'response.content.done', 'response.done',
    'input_audio_buffer.committed', 'input_audio_buffer.speech_stopped',
    'input_audio_buffer.speech_started', 'session.created', 'response.audio.done',
    'conversation.item.truncated'
]

app = FastAPI()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if not OPENAI_API_KEY:
    raise ValueError('Missing the OpenAI API key. Please set it in the .env file.')

@app.get("/", response_class=HTMLResponse)
async def index_page():
    return "<h1>Twilio Media Stream Server is running!</h1>"

@app.api_route("/incoming-call", methods=["GET", "POST"])
async def handle_incoming_call(request: Request):
    session_id = str(uuid.uuid4())
    logger.info(f"Incoming call handled. Session ID: {session_id}")
    response = VoiceResponse()
    response.pause(length=1)
    host = request.url.hostname
    connect = Connect()
    connect.stream(url=f'wss://{host}/media-stream/{session_id}')
    response.append(connect)
    return HTMLResponse(content=str(response), media_type="application/xml")

@app.websocket("/media-stream/{session_id}")
async def handle_media_stream(websocket: WebSocket, session_id: str):
    logger.info(f"WebSocket connection attempt. Session ID: {session_id}")
    await websocket.accept()
    logger.info(f"WebSocket connection accepted. Session ID: {session_id}")
    try:
        async with websockets.connect(
            'wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01',
            extra_headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "OpenAI-Beta": "realtime=v1"
            }
        ) as openai_ws:
            await send_session_update(openai_ws)
            stream_sid = None
            done_response = {"event_id": None}
            
            async def receive_from_twilio():
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
                            logger.info(f"Incoming stream has started {stream_sid}")
                except WebSocketDisconnect:
                    logger.info(f"Twilio WebSocket disconnected. Session ID: {session_id}")
                except Exception as e:
                    logger.error(f"Error in receive_from_twilio: {e}")
                finally:
                    if openai_ws.open:
                        await openai_ws.close()

            async def send_to_twilio():
                nonlocal stream_sid
                nonlocal done_response
                try:
                    async for openai_message in openai_ws:
                        response = json.loads(openai_message)
                        if response['type'] in LOG_EVENT_TYPES:
                            logger.info(f"Received event: {response['type']}::{response}")
                        if response['type'] == 'session.updated':
                            logger.info(f"Session updated successfully: {response}")
                        if response['type'] == "input_audio_buffer.speech_started":
                            logger.info(f"Input Audio Detected::{response}")
                            audio_delta = {
                              'streamSid': stream_sid,
                              'event': 'clear',
                            }
                            await websocket.send_json(audio_delta)
                            await openai_ws.send(json.dumps({"type": "response.create"}))
                        if response['type'] == 'response.audio.delta' and response.get('delta'):
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
                            except asyncio.TimeoutError:
                                logger.error("Timeout while sending audio data to Twilio")
                            except Exception as e:
                                logger.error(f"Error processing audio data: {e}")

                        elif response['type'] == 'response.function_call_arguments.done':
                            function_name = response['name']
                            call_id = response['call_id']
                            arguments = json.loads(response['arguments'])
                            if function_name == 'get_additional_context':
                                result = get_additional_context(arguments['query'], session_id)
                                logger.info(f"CustomGPT response: {result}")
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

                except WebSocketDisconnect:
                    logger.info(f"OpenAI WebSocket disconnected. Session ID: {session_id}")
                except Exception as e:
                    logger.error(f"Error in send_to_twilio: {e}")

            await asyncio.gather(receive_from_twilio(), send_to_twilio())
    except websockets.exceptions.ConnectionClosed:
        logger.error(f"WebSocket connection closed unexpectedly. Session ID: {session_id}")
    except Exception as e:
        logger.error(f"Unexpected error in handle_media_stream: {e}")
    finally:
        try:
            await websocket.close()
        except RuntimeError:
            logger.info(f"WebSocket connection closed. Session ID: {session_id}")

def get_additional_context(query, session_id):
    conversation = CustomGPT.Conversation.send(project_id=project_id, session_id=session_id, prompt=query, custom_persona="Do try your best to answer if you think user query feels similar to something you have in knowledge base. Match similar words to your knowledge base and answer as the user_query is audio transcript there can be mistakes in transcription process.")
    return f"{conversation.parsed.data.openai_response}"

async def send_session_update(openai_ws):
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
                                "description": "The elaborated user query payload should fully describe the users question"
                            }
                        },
                        "required": ["query"]
                    }
                }
            ]
        }
    }
    logger.info('Sending session update: %s', json.dumps(session_update))
    await openai_ws.send(json.dumps(session_update))
    initial_response = {
        "type": "conversation.item.create",
        "item": {
            "type": "message",
            "role": "assistant",
            "content": [
              {
                "type": "text",
                "text": "Hello, how can I assist you today?"
              }
            ]
        }
    }
    await openai_ws.send(json.dumps(initial_response))
    await openai_ws.send(json.dumps({"type": "response.create"}))