import os
import json
import base64
import asyncio
import websockets
import urllib.parse
from fastapi import FastAPI, WebSocket, Request, WebSocketDisconnect, status, BackgroundTasks
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from typing import Optional
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Connect, Redirect, Dial, Stream
from dotenv import load_dotenv
from customgpt_client import CustomGPT
import uuid
import logging
import time
import redis

load_dotenv()

redis_url = urllib.parse.urlparse(os.environ.get("REDIS_URL"))
redis_client = redis.Redis(host=redis_url.hostname, port=redis_url.port, password=redis_url.password, ssl=True, ssl_cert_reqs=None)
current_dir = os.path.dirname(__file__)
mp3_file_path = os.path.join(current_dir, "static", "typing.wav")
account_sid = os.environ["TWILIO_ACCOUNT_SID"]
auth_token = os.environ["TWILIO_AUTH_TOKEN"]
client = Client(account_sid, auth_token)
CUSTOMGPT_API_KEY = os.getenv('CUSTOMGPT_API_KEY')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
PORT = int(os.getenv('PORT', 5050))
DEFAULT_INTRO = 'Hello! How can i assist you today'
SYSTEM_MESSAGE = """
# Core Purpose & Initialization
- Start session with {introduction}
- You are an AI assistant answering questions using ONLY the get_additional_context function which is your source of truth knowledge base.
- Never start session with get_additional_context
- PHONE_NUMBER for support: {phone_number}

# Query Processing Rules
1. Greeting Responses:
   - Only respond to greetings without function calls
   - Keep initial greeting natural and brief

2. Information Retrieval:
   - ALL user queries MUST use get_additional_context
   - No need to ask for clarifications.
   - User query may contain human names so interpret them correctly.
   - get_additional_context is your knowledge base if it says sorry you should say sorry.
   - Never use internal knowledge base
   - Enhance user query:
       * Function call to  get_additional_context function call arguments query must start with "A user asked: [include the exact transcription of the user's request]".
       * Expand on the intent and purpose behind the question, adding depth, specificity, and clarity.
       * Tailor the information as if the user were asking an expert in the relevant field, and include any relevant contextual details that would help make the request more comprehensive.
       * The goal is to enhance the user query, making it clearer and more informative while maintaining the original intent.

3. Response Guidelines:
   - You can answer everything the user asked via get_additional_context even regarding individuals/personal questions.
   - Do not say anything before get_additional_context
   - Use ONLY information from get_additional_context
   - Keep responses under 50 words unless necessary
   - Never justify or explain your answers
   - Never mention the get_additional_context process
   - Never repeat user queries.
   - Never mention anything regarding user_queries from your knowledge base

# Conversation Style
- Do not say anything before get_additional_context
- Use varied intonation
- Include natural pauses
- Employ occasional filler words (hmm, well, I see)
- Maintain context awareness
- Match caller's pace and tone
- Keep personality consistent
- Never repeat users query.
- Speak Faster

# Support Handoff Protocol
1. Track consecutive failures:
   - Monitor unsuccessful responses
   - Ask the user with handoff option after 5 failed attempts:
     * Instruct user to press 0 or says "Operator" or "Live Agent" and  Any of these must be pressed to trigger exceute call_support.

# Critical Rules
- NEVER start with get_additional_context
- NEVER use internal knowledge
- ONLY use get_additional_context as your knowledge base
- ALWAYS relay exactly what get_additional_context provides
- DO NOT elaborate beyond provided information
"""


VOICE = 'alloy'
LOG_EVENT_TYPES = [
    'response.content.done', 'response.done',
    'input_audio_buffer.committed', 'input_audio_buffer.speech_stopped',
    'input_audio_buffer.speech_started', 'session.created', 'response.audio.done',
    'conversation.item.input_audio_transcription.completed'
]

PERSONAL_PHONE_NUMBER = os.getenv("PERSONAL_PHONE_NUMBER")

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if not OPENAI_API_KEY:
    raise ValueError('Missing the OpenAI API key. Please set it in the .env file.')

@app.get("/", response_class=HTMLResponse)
async def index_page():
    return "<h1>Twilio Media Stream Server is running!</h1>"

@app.api_route("/incoming-message", methods=["GET", "POST"])
async def handle_incoming_message(
    request: Request,
    background_tasks: BackgroundTasks,
    project_id: int,
    api_key: Optional[str] = CUSTOMGPT_API_KEY,
    phone_number: Optional[str] = None
):
    form_data = await request.form() if request.method == "POST" else request.query_params
    caller_number = form_data.get('From', 'Unknown')
    twilio_number = form_data.get('To', 'Unknown')
    logger.info(f"Sender: {caller_number}")
    message = form_data.get('Body', 'Unknown')
    logger.info(f"Message: {message}")
    session_id = create_session(api_key, project_id, caller_number)
    logger.info(f"Project::{project_id}")

    async def process_and_respond():
        CustomGPT.api_key = api_key
        logger.info(f"CustomGPT query sent:: {message}")
        instructions = "NOTE: Ensure the response is less than 1600 characters keep the answer short and concise."
        conversation = CustomGPT.Conversation.send(
            project_id=project_id,
            session_id=session_id,
            prompt=message,
            custom_persona=instructions
        )
        response = conversation.parsed.data.openai_response
        
        client.messages.create(
            body=response,
            from_=twilio_number,
            to=caller_number
        )

    background_tasks.add_task(process_and_respond)
    return {"message": "Processing your message"}

@app.api_route("/incoming-call", methods=["GET", "POST"])
async def handle_incoming_call(
    request: Request,
    background_tasks: BackgroundTasks,
    project_id: int,
    api_key: Optional[str] = CUSTOMGPT_API_KEY,
    phone_number: Optional[str] = None,
    introduction: Optional[str] = DEFAULT_INTRO
):
    logger.info(f"Introduction: {introduction}")
    form_data = await request.form() if request.method == "POST" else request.query_params
    caller_number = form_data.get('From', 'Unknown')
    logger.info(f"Caller: {caller_number}")
    session_id = create_session(api_key, project_id, caller_number)
    logger.info(f"Project::{project_id}")
    logger.info(f"Incoming call handled. Session ID: {session_id}")
    host = request.url.hostname
    call_id = form_data.get("CallSid")
    response = VoiceResponse()
    response.pause(length=1)
    connect = Connect()
    encoded_phone_number = urllib.parse.quote_plus(phone_number)
    encoded_introduction = urllib.parse.quote_plus(introduction)
    stream = Stream(url=f'wss://{host}/media-stream/project/{project_id}/session/{session_id}/{encoded_phone_number}/{encoded_introduction}')
    stream.parameter(name='api_key', value=api_key)
    connect.append(stream)
    response.append(connect)
    if phone_number:
        phone_number = urllib.parse.quote_plus(phone_number)
    response.redirect(url=f"https://{host}/end-stream/{session_id}?phone_number={phone_number}")
    background_tasks.add_task(start_recording, call_id, session_id, host)
    return HTMLResponse(content=str(response), media_type="application/xml")

@app.post("/log-recording/{session_id}")
async def log_recording(session_id: str, request: Request):
    form_data = await request.form()
    recording_url = form_data.get("RecordingUrl")
    if recording_url:
        logger.info(f"Recording for session {session_id}: {recording_url}")
    else:
        logger.warning(f"No recording URL received for session {session_id}")
    return {"status": "Recording logged"}


@app.api_route("/end-stream/{session_id}", methods=["GET", "POST"])
async def handle_end_call(request: Request, session_id: Optional[str] = None, phone_number: Optional[str] = None):
    state = redis_client.get(session_id)
    if state:
        state = state.decode('utf-8') 
    logger.info(f"Ending Stream with state: {state}")
    response = VoiceResponse()
    if state == "transfer":
        dial = Dial()
        dial.number(phone_number)
        response.append(dial)
    else:
        response.hangup()

    return HTMLResponse(content=str(response), media_type="application/xml")

@app.websocket("/media-stream/project/{project_id}/session/{session_id}/{phone_number}/{introduction}")
async def handle_media_stream(websocket: WebSocket, project_id: int, session_id: str, phone_number: str, introduction: str):
    logger.info(f"WebSocket connection attempt. Session ID: {session_id}")
    await websocket.accept()
    logger.info(f"WebSocket connection accepted. Session ID: {session_id}")
    api_key = None
    # Create task termination event
    termination_event = asyncio.Event()

    async with websockets.connect(
        'wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-12-17',
        extra_headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "OpenAI-Beta": "realtime=v1"
        }
    ) as openai_ws:
        try:
            handle_first_response = time.time()
            start_time = time.time()
            stream_sid = None
            await send_session_update(openai_ws, phone_number, introduction)
            async def check_timeout():
                logger.info(f"Checking inactivity. Session ID: {session_id}")
                try:
                    while not termination_event.is_set():
                        current_time = time.time()
                        diff = current_time - start_time
                        if diff > 300:
                            logger.info(f"Session timeout after 30 seconds of inactivity. Session ID: {session_id}")
                            termination_event.set()
                            await clear_buffer(websocket, openai_ws, stream_sid)
                            await websocket.close()
                            break
                        await asyncio.sleep(5)
                except Exception as e:
                    raise e

            asyncio.create_task(check_timeout())
            async def receive_from_twilio():
                nonlocal stream_sid, start_time, api_key
                while not termination_event.is_set():
                    try:
                        message = await websocket.receive_text()
                        data = json.loads(message)
                        if data['event'] == 'media' and openai_ws.open:
                            audio_append = {
                                "type": "input_audio_buffer.append",
                                "audio": data['media']['payload']
                            }
                            await openai_ws.send(json.dumps(audio_append))
                        elif data['event'] == 'start':
                            api_key = data['start']['customParameters']['api_key']
                            stream_sid = data['start']['streamSid']
                            start_time = time.time()
                            logger.info(f"Incoming stream has started {stream_sid}")
                        elif data['event'] == 'dtmf':
                            digit = data['dtmf']['digit']
                            logger.info(f"DTMF received: {digit}")
                            if digit == "0":
                                redis_client.set(session_id, "transfer")
                                logger.info("DTMF '0' detected, redirecting call...")
                                termination_event.set()
                                await websocket.close()
                                break
                    except WebSocketDisconnect:
                        logger.info(f"Twilio WebSocket disconnected. Session ID: {session_id}")
                        break
                    except RuntimeError as e:
                        if "WebSocket is not connected" in str(e):
                            logger.info(f"WebSocket connection lost. Session ID: {session_id}")
                            break
                        logger.error(f"Runtime error in receive_from_twilio: {e}")
                        break
                    except Exception as e:
                        logger.error(f"Error in receive_from_twilio: {e}")
                        break

            async def send_to_twilio():
                nonlocal stream_sid, start_time
                try:
                    async for openai_message in openai_ws:
                        try:
                            response = json.loads(openai_message)
                            start_time = time.time()
                            if response['type'] in LOG_EVENT_TYPES:
                                logger.info(f"Received event: {response['type']}::{response}")
                            if response['type'] == 'session.updated':
                                logger.info(f"Session updated successfully: {response}")
                            if response['type'] == "input_audio_buffer.speech_started":
                                logger.info(f"Input Audio Detected::{response}")
                                await clear_buffer(websocket, openai_ws, stream_sid)

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
                                    start_time = time.time()
                                except asyncio.TimeoutError:
                                    logger.error("Timeout while sending audio data to Twilio")
                                except Exception as e:
                                    logger.error(f"Error processing audio data: {e}")                            
                            if response['type'] == 'response.function_call_arguments.done':
                                try:
                                    function_name = response['name']
                                    call_id = response['call_id']
                                    arguments = json.loads(response['arguments'])
                                    if function_name == 'get_additional_context':
                                        await play_typing(websocket, stream_sid)
                                        logger.info("CustomGPT Started")
                                        start_time = time.time()
                                        result = get_additional_context(arguments['query'], api_key, project_id, session_id)
                                        logger.info(f"Clear Audio::Additional Context gained")
                                        await clear_buffer(websocket, openai_ws, stream_sid)
                                        end_time = time.time()
                                        elapsed_time = end_time - start_time
                                        logger.info(f"get_additional_context execution time: {elapsed_time:.4f} seconds")
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
                                    elif function_name == 'call_support':
                                        logger.info("Detected Term for calling support...")
                                        redis_client.set(session_id, "transfer")
                                        termination_event.set()
                                        raise Exception("Close Stream")

                                except json.JSONDecodeError as e:
                                    logger.error(f"Error in json decode in function_call: {e}::{response}")
                                except Exception as e:
                                    logger.error(f"Error in function_call.done: {e}")
                                    raise Exception("Close Stream")


                        except json.JSONDecodeError as e:
                            logger.error(f"Error in json decode of response: {e}::{openai_message}")

                except WebSocketDisconnect:
                    logger.info(f"OpenAI WebSocket disconnected. Session ID: {session_id}")
                except Exception as e:
                    logger.error(f"Error in send_to_twilio: {e}")
                    raise Exception("Close Stream")

            await asyncio.gather(receive_from_twilio(), send_to_twilio())
        except websockets.exceptions.ConnectionClosed:
            logger.error(f"WebSocket connection closed unexpectedly. Session ID: {session_id}")
        except Exception as e:
            logger.error(f"Unexpected error in handle_media_stream: {e}")

        finally:
            try:
                await clear_buffer(websocket, openai_ws, stream_sid)
                await openai_ws.close()
                await websocket.close()
            except Exception:
                logger.info(f"WebSocket connection closed. Session ID: {session_id}")

def start_recording(call_id: str, session_id: str, host: str):
    # Delay the recording by 3 seconds
    time.sleep(2)
    # Start the recording
    try:
        recording = client.calls(call_id).recordings.create(
            recording_status_callback=f"https://{host}/log-recording/{session_id}",
            recording_status_callback_event=["in-progress", "completed"],
            recording_channels="dual",
        )
        logger.info(f"Recording started for Call SID: {call_id} with Recording SID: {recording.sid}")
    except Exception as e:
        logger.error(f"Failed to start recording for Call SID: {call_id}. Error: {e}")

def get_additional_context(query, api_key, project_id, session_id):
    custom_persona = """
    You are an AI assistant tasked with answering user queries based on a knowledge base. The user query is transcribed from voice audio, so there may be transcription errors.

    When responding to the user query, follow these guidelines:
    1. Match the query to the knowledge base using both phonetic and semantic similarity.
    2. Attempt to answer even if the match isn't perfect, as long as it seems reasonably close.

    Provide a concise answer, limited to three sentences.
    """

    tries = 0
    max_retries = 2
    while tries <= max_retries:
        try:
            CustomGPT.api_key = api_key
            logger.info(f"CustomGPT query sent:: {query}")
            conversation = CustomGPT.Conversation.send(
                project_id=project_id, 
                session_id=session_id, 
                prompt=query, 
                custom_persona=custom_persona
            )
            logger.info(f"CustomGPT response: {conversation}")
            return conversation.parsed.data.openai_response  # Correct f-string is unnecessary
        except Exception as e:
            logger.error(f"Get Additional Context failed::Try {tries}::Error: {conversation}")
            time.sleep(2)
        tries += 1

    return "Sorry, I didn't get your query."

def create_session(api_key, project_id, caller_number):
    tries = 0
    max_retries = 2
    while tries <= max_retries:
        try:
            CustomGPT.api_key = api_key
            session = CustomGPT.Conversation.create(project_id=project_id, name=caller_number)
            logger.info(f"CustomGPT Session Created::{session.parsed.data}");
            return session.parsed.data.session_id
        except Exception as e:
            logger.error(f"Error in create_session::Try {tries}::Error: {e}")
        tries += 1

    session_id = uuid.uuid4()
    return session_id

async def send_session_update(openai_ws, phone_number, introduction):
    introduction = introduction.replace('+', ' ')
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
            "instructions": SYSTEM_MESSAGE.format(phone_number=phone_number, introduction=introduction),
            "modalities": ["text", "audio"],
            "temperature": 0.8,
            "tools": [
                {
                  "type": "function",
                  "name": "get_additional_context",
                  "description": "Elaborate on the user's original query, providing additional context, specificity, and clarity to create a more detailed, expert-level question. The function should transform a simple query into a richer and more informative version that is suitable for an expert to answer.",
                  "parameters": {
                    "type": "object",
                    "properties": {
                      "query": {
                        "type": "string",
                        "description": "The elaborated user query. This should fully describe the user's original question, adding depth, context, and clarity. Tailor the expanded query as if the user were asking an expert in the relevant field, providing necessary background or related subtopics that may help inform the response. Start with 'Please use your knowledge base'"
                      }
                    },
                    "required": ["query"]
                  }
                },
                {
                  "type": "function",
                  "name": "call_support",
                  "description": "The purpose of the call_support function is to help user when the agent is unable to answer query multiple times and they request transfer to a live agent or support but do not provide enough detail for effective assistance."
                }
            ]
        }
    }
    logger.info('Sending session update: %s', json.dumps(session_update))
    await openai_ws.send(json.dumps(session_update))
    time.sleep(1)
    initial_response = {
        "type": "conversation.item.create",
        "item": {
            "type": "message",
            "role": "user",
            "content": [
              {
                "type": "text",
                "text": "Introduce yourself"
              }
            ]
        }
    }
    await openai_ws.send(json.dumps(initial_response))
    await openai_ws.send(json.dumps({"type": "response.create", "response": { "instructions": f"Introduce yourself as {introduction}"} }))

async def play_typing(websocket, stream_sid):
    with open(mp3_file_path, "rb") as mp3_file:
        mp3_data = mp3_file.read()
        base64_audio = base64.b64encode(mp3_data).decode('utf-8')

    audio_delta = {
        "event": "media",
        "streamSid": stream_sid,
        "media": {
            "payload": base64_audio
        }
    }
    await websocket.send_json(audio_delta)

async def clear_buffer(websocket, openai_ws, stream_sid):
    audio_delta = {
      'streamSid': stream_sid,
      'event': 'clear',
    }
    await openai_ws.send(json.dumps({"type": "response.cancel"}))
    await websocket.send_json(audio_delta)
