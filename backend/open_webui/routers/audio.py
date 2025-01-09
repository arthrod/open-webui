import hashlib
import json
import logging
import os
import uuid
from functools import lru_cache
from pathlib import Path
from pydub import AudioSegment
from pydub.silence import split_on_silence

import aiohttp
import aiofiles
import requests

from fastapi import (
    Depends,
    FastAPI,
    File,
    HTTPException,
    Request,
    UploadFile,
    status,
    APIRouter,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel


from open_webui.utils.auth import get_admin_user, get_verified_user
from open_webui.config import (
    WHISPER_MODEL_AUTO_UPDATE,
    WHISPER_MODEL_DIR,
    CACHE_DIR,
)

from open_webui.constants import ERROR_MESSAGES
from open_webui.env import (
    ENV,
    SRC_LOG_LEVELS,
    DEVICE_TYPE,
    ENABLE_FORWARD_USER_INFO_HEADERS,
)


router = APIRouter()

# Constants
MAX_FILE_SIZE_MB = 25
MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024  # Convert MB to bytes

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["AUDIO"])

SPEECH_CACHE_DIR = Path(CACHE_DIR).joinpath("./audio/speech/")
SPEECH_CACHE_DIR.mkdir(parents=True, exist_ok=True)


##########################################
#
# Utility functions
#
##########################################

from pydub import AudioSegment
from pydub.utils import mediainfo


def is_mp4_audio(file_path):
    """
    Check if the given file is an MP4 audio file based on its codec information.
    
    This function verifies whether a file is an MP4 audio file by examining its media metadata using the mediainfo utility. It checks for specific codec characteristics typical of MP4 audio files.
    
    Parameters:
        file_path (str): The path to the file to be checked.
    
    Returns:
        bool: True if the file is an MP4 audio file, False otherwise.
    
    Raises:
        No explicit exceptions, but prints a message if the file is not found.
    
    Notes:
        - Checks for AAC codec
        - Verifies codec type is audio
        - Confirms codec tag string is 'mp4a'
        - Returns False for non-existent files
    """
    if not os.path.isfile(file_path):
        print(f"File not found: {file_path}")
        return False

    info = mediainfo(file_path)
    if (
        info.get("codec_name") == "aac"
        and info.get("codec_type") == "audio"
        and info.get("codec_tag_string") == "mp4a"
    ):
        return True
    return False


def convert_mp4_to_wav(file_path, output_path):
    """
    Convert an MP4 audio file to WAV format using pydub's AudioSegment.
    
    This function reads an MP4 audio file and exports it as a WAV file, allowing for audio format conversion.
    
    Parameters:
        file_path (str): Path to the source MP4 audio file to be converted
        output_path (str): Destination path where the converted WAV file will be saved
    
    Raises:
        FileNotFoundError: If the source file does not exist
        Exception: For any audio processing or export errors
    
    Side Effects:
        - Prints a conversion confirmation message to console
        - Creates a new WAV file at the specified output path
    """
    audio = AudioSegment.from_file(file_path, format="mp4")
    audio.export(output_path, format="wav")
    print(f"Converted {file_path} to {output_path}")


def set_faster_whisper_model(model: str, auto_update: bool = False):
    """
    Initialize a Faster Whisper model for speech-to-text transcription.
    
    This function sets up a WhisperModel with specified configuration, handling potential initialization errors and supporting optional model updates.
    
    Parameters:
        model (str): Path or name of the Whisper model to load.
        auto_update (bool, optional): Whether to allow automatic model updates. Defaults to False.
    
    Returns:
        WhisperModel or None: Configured Whisper model for speech transcription, or None if model initialization fails.
    
    Notes:
        - Uses CUDA device if available, otherwise falls back to CPU
        - Attempts to load model with local files first
        - Retries model initialization with forced download if initial attempt fails
        - Logs a warning if model initialization encounters issues
    """
    whisper_model = None
    if model:
        from faster_whisper import WhisperModel

        faster_whisper_kwargs = {
            "model_size_or_path": model,
            "device": DEVICE_TYPE if DEVICE_TYPE and DEVICE_TYPE == "cuda" else "cpu",
            "compute_type": "int8",
            "download_root": WHISPER_MODEL_DIR,
            "local_files_only": not auto_update,
        }

        try:
            whisper_model = WhisperModel(**faster_whisper_kwargs)
        except Exception:
            log.warning(
                "WhisperModel initialization failed, attempting download with local_files_only=False"
            )
            faster_whisper_kwargs["local_files_only"] = False
            whisper_model = WhisperModel(**faster_whisper_kwargs)
    return whisper_model


##########################################
#
# Audio API
#
##########################################


class TTSConfigForm(BaseModel):
    OPENAI_API_BASE_URL: str
    OPENAI_API_KEY: str
    API_KEY: str
    ENGINE: str
    MODEL: str
    VOICE: str
    SPLIT_ON: str
    AZURE_SPEECH_REGION: str
    AZURE_SPEECH_OUTPUT_FORMAT: str


class STTConfigForm(BaseModel):
    OPENAI_API_BASE_URL: str
    OPENAI_API_KEY: str
    ENGINE: str
    MODEL: str
    WHISPER_MODEL: str


class AudioConfigUpdateForm(BaseModel):
    tts: TTSConfigForm
    stt: STTConfigForm


@router.get("/config")
async def get_audio_config(request: Request, user=Depends(get_admin_user)):
    """
    Retrieve the current audio configuration for text-to-speech (TTS) and speech-to-text (STT) settings.
    
    This asynchronous function returns a comprehensive configuration dictionary containing settings for various TTS and STT engines. Access is restricted to admin users.
    
    Parameters:
        request (Request): The FastAPI request object containing application state configuration
        user (dict, optional): Admin user authentication, automatically validated by the get_admin_user dependency
    
    Returns:
        dict: A nested dictionary with two main keys 'tts' and 'stt', each containing multiple configuration parameters:
            - TTS configuration includes API URLs, keys, engine, model, voice, and Azure-specific settings
            - STT configuration includes API URLs, keys, engine, model, and Whisper model settings
    
    Raises:
        HTTPException: If the user is not authenticated as an admin
    """
    return {
        "tts": {
            "OPENAI_API_BASE_URL": request.app.state.config.TTS_OPENAI_API_BASE_URL,
            "OPENAI_API_KEY": request.app.state.config.TTS_OPENAI_API_KEY,
            "API_KEY": request.app.state.config.TTS_API_KEY,
            "ENGINE": request.app.state.config.TTS_ENGINE,
            "MODEL": request.app.state.config.TTS_MODEL,
            "VOICE": request.app.state.config.TTS_VOICE,
            "SPLIT_ON": request.app.state.config.TTS_SPLIT_ON,
            "AZURE_SPEECH_REGION": request.app.state.config.TTS_AZURE_SPEECH_REGION,
            "AZURE_SPEECH_OUTPUT_FORMAT": request.app.state.config.TTS_AZURE_SPEECH_OUTPUT_FORMAT,
        },
        "stt": {
            "OPENAI_API_BASE_URL": request.app.state.config.STT_OPENAI_API_BASE_URL,
            "OPENAI_API_KEY": request.app.state.config.STT_OPENAI_API_KEY,
            "ENGINE": request.app.state.config.STT_ENGINE,
            "MODEL": request.app.state.config.STT_MODEL,
            "WHISPER_MODEL": request.app.state.config.WHISPER_MODEL,
        },
    }


@router.post("/config/update")
async def update_audio_config(
    request: Request, form_data: AudioConfigUpdateForm, user=Depends(get_admin_user)
):
    """
    Update the application's audio configuration for text-to-speech (TTS) and speech-to-text (STT) settings.
    
    This asynchronous function allows an admin user to modify various configuration parameters for audio processing engines. It updates both TTS and STT settings in the application's state, including API keys, engine selection, models, and additional engine-specific parameters.
    
    Parameters:
        request (Request): The FastAPI request object containing the application state.
        form_data (AudioConfigUpdateForm): A form containing the new configuration settings for TTS and STT.
        user (dict, optional): The admin user, automatically validated by the get_admin_user dependency.
    
    Returns:
        dict: A dictionary containing the updated configuration settings for both TTS and STT, including:
            - TTS settings: API URLs, keys, engine, model, voice, split settings, Azure-specific parameters
            - STT settings: API URLs, keys, engine, model, Whisper model
    
    Notes:
        - Requires admin user authentication
        - If STT engine is empty, initializes a Whisper model with the specified configuration
        - Directly modifies the application's state configuration
    """
    request.app.state.config.TTS_OPENAI_API_BASE_URL = form_data.tts.OPENAI_API_BASE_URL
    request.app.state.config.TTS_OPENAI_API_KEY = form_data.tts.OPENAI_API_KEY
    request.app.state.config.TTS_API_KEY = form_data.tts.API_KEY
    request.app.state.config.TTS_ENGINE = form_data.tts.ENGINE
    request.app.state.config.TTS_MODEL = form_data.tts.MODEL
    request.app.state.config.TTS_VOICE = form_data.tts.VOICE
    request.app.state.config.TTS_SPLIT_ON = form_data.tts.SPLIT_ON
    request.app.state.config.TTS_AZURE_SPEECH_REGION = form_data.tts.AZURE_SPEECH_REGION
    request.app.state.config.TTS_AZURE_SPEECH_OUTPUT_FORMAT = (
        form_data.tts.AZURE_SPEECH_OUTPUT_FORMAT
    )

    request.app.state.config.STT_OPENAI_API_BASE_URL = form_data.stt.OPENAI_API_BASE_URL
    request.app.state.config.STT_OPENAI_API_KEY = form_data.stt.OPENAI_API_KEY
    request.app.state.config.STT_ENGINE = form_data.stt.ENGINE
    request.app.state.config.STT_MODEL = form_data.stt.MODEL
    request.app.state.config.WHISPER_MODEL = form_data.stt.WHISPER_MODEL

    if request.app.state.config.STT_ENGINE == "":
        request.app.state.faster_whisper_model = set_faster_whisper_model(
            form_data.stt.WHISPER_MODEL, WHISPER_MODEL_AUTO_UPDATE
        )

    return {
        "tts": {
            "OPENAI_API_BASE_URL": request.app.state.config.TTS_OPENAI_API_BASE_URL,
            "OPENAI_API_KEY": request.app.state.config.TTS_OPENAI_API_KEY,
            "API_KEY": request.app.state.config.TTS_API_KEY,
            "ENGINE": request.app.state.config.TTS_ENGINE,
            "MODEL": request.app.state.config.TTS_MODEL,
            "VOICE": request.app.state.config.TTS_VOICE,
            "SPLIT_ON": request.app.state.config.TTS_SPLIT_ON,
            "AZURE_SPEECH_REGION": request.app.state.config.TTS_AZURE_SPEECH_REGION,
            "AZURE_SPEECH_OUTPUT_FORMAT": request.app.state.config.TTS_AZURE_SPEECH_OUTPUT_FORMAT,
        },
        "stt": {
            "OPENAI_API_BASE_URL": request.app.state.config.STT_OPENAI_API_BASE_URL,
            "OPENAI_API_KEY": request.app.state.config.STT_OPENAI_API_KEY,
            "ENGINE": request.app.state.config.STT_ENGINE,
            "MODEL": request.app.state.config.STT_MODEL,
            "WHISPER_MODEL": request.app.state.config.WHISPER_MODEL,
        },
    }


def load_speech_pipeline(request):
    """
    Load and initialize the speech synthesis pipeline and speaker embeddings dataset.
    
    This function sets up the text-to-speech (TTS) pipeline using the Microsoft SpeechT5 model 
    and loads speaker embeddings from the CMU Arctic dataset. It ensures that the pipeline 
    and dataset are only loaded once and cached in the application state.
    
    Parameters:
        request (Request): The FastAPI request object containing the application state.
    
    Side Effects:
        - Initializes `request.app.state.speech_synthesiser` with a Hugging Face text-to-speech pipeline
        - Initializes `request.app.state.speech_speaker_embeddings_dataset` with speaker embeddings dataset
    
    Notes:
        - Uses the 'microsoft/speecht5_tts' model for text-to-speech synthesis
        - Loads speaker embeddings from the 'Matthijs/cmu-arctic-xvectors' dataset
        - Lazy loading is implemented to avoid redundant model and dataset loading
    """
    from transformers import pipeline
    from datasets import load_dataset

    if request.app.state.speech_synthesiser is None:
        request.app.state.speech_synthesiser = pipeline(
            "text-to-speech", "microsoft/speecht5_tts"
        )

    if request.app.state.speech_speaker_embeddings_dataset is None:
        request.app.state.speech_speaker_embeddings_dataset = load_dataset(
            "Matthijs/cmu-arctic-xvectors", split="validation"
        )


@router.post("/speech")
async def speech(request: Request, user=Depends(get_verified_user)):
    """
    Asynchronously generate speech using the configured Text-to-Speech (TTS) engine.
    
    This function supports multiple TTS engines including OpenAI, ElevenLabs, Azure, and Transformers. It handles caching of generated speech files to improve performance and reduce redundant API calls.
    
    Parameters:
        request (Request): The incoming HTTP request containing TTS configuration and payload
        user (User, optional): The verified user making the request, obtained via dependency injection
    
    Returns:
        FileResponse: An MP3 audio file containing the synthesized speech
    
    Raises:
        HTTPException: For various error conditions such as invalid payload, unsupported voice, or external service errors
    
    Notes:
        - Supports caching of generated speech files using a hash of the input text and TTS configuration
        - Handles different API requirements for each supported TTS engine
        - Logs exceptions and provides detailed error messages
        - Optionally forwards user information headers for external API calls
    """
    body = await request.body()
    name = hashlib.sha256(
        body
        + str(request.app.state.config.TTS_ENGINE).encode("utf-8")
        + str(request.app.state.config.TTS_MODEL).encode("utf-8")
    ).hexdigest()

    file_path = SPEECH_CACHE_DIR.joinpath(f"{name}.mp3")
    file_body_path = SPEECH_CACHE_DIR.joinpath(f"{name}.json")

    # Check if the file already exists in the cache
    if file_path.is_file():
        return FileResponse(file_path)

    payload = None
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception as e:
        log.exception(e)
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    if request.app.state.config.TTS_ENGINE == "openai":
        payload["model"] = request.app.state.config.TTS_MODEL

        try:
            # print(payload)
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url=f"{request.app.state.config.TTS_OPENAI_API_BASE_URL}/audio/speech",
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {request.app.state.config.TTS_OPENAI_API_KEY}",
                        **(
                            {
                                "X-OpenWebUI-User-Name": user.name,
                                "X-OpenWebUI-User-Id": user.id,
                                "X-OpenWebUI-User-Email": user.email,
                                "X-OpenWebUI-User-Role": user.role,
                            }
                            if ENABLE_FORWARD_USER_INFO_HEADERS
                            else {}
                        ),
                    },
                ) as r:
                    r.raise_for_status()

                    async with aiofiles.open(file_path, "wb") as f:
                        await f.write(await r.read())

                    async with aiofiles.open(file_body_path, "w") as f:
                        await f.write(json.dumps(payload))

            return FileResponse(file_path)

        except Exception as e:
            log.exception(e)
            detail = None

            try:
                if r.status != 200:
                    res = await r.json()

                    if "error" in res:
                        detail = f"External: {res['error'].get('message', '')}"
            except Exception:
                detail = f"External: {e}"

            raise HTTPException(
                status_code=getattr(r, "status", 500),
                detail=detail if detail else "Open WebUI: Server Connection Error",
            )

    elif request.app.state.config.TTS_ENGINE == "elevenlabs":
        voice_id = payload.get("voice", "")

        if voice_id not in get_available_voices(request):
            raise HTTPException(
                status_code=400,
                detail="Invalid voice id",
            )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                    json={
                        "text": payload["input"],
                        "model_id": request.app.state.config.TTS_MODEL,
                        "voice_settings": {"stability": 0.5, "similarity_boost": 0.5},
                    },
                    headers={
                        "Accept": "audio/mpeg",
                        "Content-Type": "application/json",
                        "xi-api-key": request.app.state.config.TTS_API_KEY,
                    },
                ) as r:
                    r.raise_for_status()

                    async with aiofiles.open(file_path, "wb") as f:
                        await f.write(await r.read())

                    async with aiofiles.open(file_body_path, "w") as f:
                        await f.write(json.dumps(payload))

            return FileResponse(file_path)

        except Exception as e:
            log.exception(e)
            detail = None

            try:
                if r.status != 200:
                    res = await r.json()
                    if "error" in res:
                        detail = f"External: {res['error'].get('message', '')}"
            except Exception:
                detail = f"External: {e}"

            raise HTTPException(
                status_code=getattr(r, "status", 500),
                detail=detail if detail else "Open WebUI: Server Connection Error",
            )

    elif request.app.state.config.TTS_ENGINE == "azure":
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception as e:
            log.exception(e)
            raise HTTPException(status_code=400, detail="Invalid JSON payload")

        region = request.app.state.config.TTS_AZURE_SPEECH_REGION
        language = request.app.state.config.TTS_VOICE
        locale = "-".join(request.app.state.config.TTS_VOICE.split("-")[:1])
        output_format = request.app.state.config.TTS_AZURE_SPEECH_OUTPUT_FORMAT

        try:
            data = f"""<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{locale}">
                <voice name="{language}">{payload["input"]}</voice>
            </speak>"""
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1",
                    headers={
                        "Ocp-Apim-Subscription-Key": request.app.state.config.TTS_API_KEY,
                        "Content-Type": "application/ssml+xml",
                        "X-Microsoft-OutputFormat": output_format,
                    },
                    data=data,
                ) as r:
                    r.raise_for_status()

                    async with aiofiles.open(file_path, "wb") as f:
                        await f.write(await r.read())

                    async with aiofiles.open(file_body_path, "w") as f:
                        await f.write(json.dumps(payload))

                    return FileResponse(file_path)

        except Exception as e:
            log.exception(e)
            detail = None

            try:
                if r.status != 200:
                    res = await r.json()
                    if "error" in res:
                        detail = f"External: {res['error'].get('message', '')}"
            except Exception:
                detail = f"External: {e}"

            raise HTTPException(
                status_code=getattr(r, "status", 500),
                detail=detail if detail else "Open WebUI: Server Connection Error",
            )

    elif request.app.state.config.TTS_ENGINE == "transformers":
        payload = None
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception as e:
            log.exception(e)
            raise HTTPException(status_code=400, detail="Invalid JSON payload")

        import torch
        import soundfile as sf

        load_speech_pipeline(request)

        embeddings_dataset = request.app.state.speech_speaker_embeddings_dataset

        speaker_index = 6799
        try:
            speaker_index = embeddings_dataset["filename"].index(
                request.app.state.config.TTS_MODEL
            )
        except Exception:
            pass

        speaker_embedding = torch.tensor(
            embeddings_dataset[speaker_index]["xvector"]
        ).unsqueeze(0)

        speech = request.app.state.speech_synthesiser(
            payload["input"],
            forward_params={"speaker_embeddings": speaker_embedding},
        )

        sf.write(file_path, speech["audio"], samplerate=speech["sampling_rate"])

        async with aiofiles.open(file_body_path, "w") as f:
            await f.write(json.dumps(payload))

        return FileResponse(file_path)


def transcribe(request: Request, file_path):
    """
    Transcribe an audio file using the configured speech-to-text (STT) engine.
    
    This function supports two STT engines: a local Whisper model and OpenAI's transcription service.
    For the local Whisper model, it uses the faster-whisper library to generate a transcript.
    For OpenAI, it sends the audio file to the OpenAI API for transcription.
    
    Parameters:
        request (Request): The FastAPI request object containing application state and configuration.
        file_path (str): The path to the audio file to be transcribed.
    
    Returns:
        dict: A dictionary containing the transcribed text with the key 'text'.
    
    Raises:
        Exception: If there are issues with transcription, such as API connection errors or file processing problems.
    
    Side Effects:
        - Saves the transcript as a JSON file in the same directory as the input audio file.
        - Logs the detected language and transcription details.
        - May convert MP4 audio files to WAV format for OpenAI transcription.
    """
    print("transcribe", file_path)
    filename = os.path.basename(file_path)
    file_dir = os.path.dirname(file_path)
    id = filename.split(".")[0]

    if request.app.state.config.STT_ENGINE == "":
        if request.app.state.faster_whisper_model is None:
            request.app.state.faster_whisper_model = set_faster_whisper_model(
                request.app.state.config.WHISPER_MODEL
            )

        model = request.app.state.faster_whisper_model
        segments, info = model.transcribe(file_path, beam_size=5)
        log.info(
            "Detected language '%s' with probability %f"
            % (info.language, info.language_probability)
        )

        transcript = "".join([segment.text for segment in list(segments)])
        data = {"text": transcript.strip()}

        # save the transcript to a json file
        transcript_file = f"{file_dir}/{id}.json"
        with open(transcript_file, "w") as f:
            json.dump(data, f)

        log.debug(data)
        return data
    elif request.app.state.config.STT_ENGINE == "openai":
        if is_mp4_audio(file_path):
            os.rename(file_path, file_path.replace(".wav", ".mp4"))
            # Convert MP4 audio file to WAV format
            convert_mp4_to_wav(file_path.replace(".wav", ".mp4"), file_path)

        r = None
        try:
            r = requests.post(
                url=f"{request.app.state.config.STT_OPENAI_API_BASE_URL}/audio/transcriptions",
                headers={
                    "Authorization": f"Bearer {request.app.state.config.STT_OPENAI_API_KEY}"
                },
                files={"file": (filename, open(file_path, "rb"))},
                data={"model": request.app.state.config.STT_MODEL},
            )

            r.raise_for_status()
            data = r.json()

            # save the transcript to a json file
            transcript_file = f"{file_dir}/{id}.json"
            with open(transcript_file, "w") as f:
                json.dump(data, f)

            return data
        except Exception as e:
            log.exception(e)

            detail = None
            if r is not None:
                try:
                    res = r.json()
                    if "error" in res:
                        detail = f"External: {res['error'].get('message', '')}"
                except Exception:
                    detail = f"External: {e}"

            raise Exception(detail if detail else "Open WebUI: Server Connection Error")


def compress_audio(file_path):
    """
    Compress an audio file if it exceeds the maximum allowed file size.
    
    This function reduces the audio file's size by:
    - Downsampling to 16kHz
    - Converting to mono channel
    - Exporting as low-bitrate OPUS format
    
    Parameters:
        file_path (str): Path to the input audio file to be compressed
    
    Returns:
        str: Path to the compressed audio file or original file if no compression was needed
    
    Raises:
        Exception: If the compressed file still exceeds the maximum file size
    
    Side Effects:
        - Creates a new compressed audio file in the same directory as the original
        - Logs debug information about compression
    """
    if os.path.getsize(file_path) > MAX_FILE_SIZE:
        file_dir = os.path.dirname(file_path)
        audio = AudioSegment.from_file(file_path)
        audio = audio.set_frame_rate(16000).set_channels(1)  # Compress audio
        compressed_path = f"{file_dir}/{id}_compressed.opus"
        audio.export(compressed_path, format="opus", bitrate="32k")
        log.debug(f"Compressed audio to {compressed_path}")

        if (
            os.path.getsize(compressed_path) > MAX_FILE_SIZE
        ):  # Still larger than MAX_FILE_SIZE after compression
            raise Exception(ERROR_MESSAGES.FILE_TOO_LARGE(size=f"{MAX_FILE_SIZE_MB}MB"))
        return compressed_path
    else:
        return file_path


@router.post("/transcriptions")
def transcription(
    request: Request,
    file: UploadFile = File(...),
    user=Depends(get_verified_user),
):
    """
    Transcribe an uploaded audio file to text using the configured speech-to-text (STT) engine.
    
    This endpoint handles audio file uploads, validates the file type, compresses the audio if necessary, 
    and generates a text transcription using the specified STT engine.
    
    Parameters:
        request (Request): The FastAPI request object containing configuration context
        file (UploadFile): The uploaded audio file to be transcribed
        user (dict, optional): Verified user information, obtained through dependency injection
    
    Returns:
        dict: A dictionary containing the transcription data and the filename
            - 'text': Transcribed text from the audio file
            - 'filename': Name of the processed audio file
    
    Raises:
        HTTPException: 
            - 400 Bad Request if the file type is not supported
            - 400 Bad Request if audio compression or transcription fails
    
    Notes:
        - Supports audio file types: MP3, WAV, OGG, M4A
        - Generates a unique filename for each uploaded file
        - Stores uploaded files temporarily in the cache directory
        - Compresses audio files before transcription
        - Logs any exceptions during processing
    """
    log.info(f"file.content_type: {file.content_type}")

    if file.content_type not in ["audio/mpeg", "audio/wav", "audio/ogg", "audio/x-m4a"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.FILE_NOT_SUPPORTED,
        )

    try:
        ext = file.filename.split(".")[-1]
        id = uuid.uuid4()

        filename = f"{id}.{ext}"
        contents = file.file.read()

        file_dir = f"{CACHE_DIR}/audio/transcriptions"
        os.makedirs(file_dir, exist_ok=True)
        file_path = f"{file_dir}/{filename}"

        with open(file_path, "wb") as f:
            f.write(contents)

        try:
            try:
                file_path = compress_audio(file_path)
            except Exception as e:
                log.exception(e)

                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ERROR_MESSAGES.DEFAULT(e),
                )

            data = transcribe(request, file_path)
            file_path = file_path.split("/")[-1]
            return {**data, "filename": file_path}
        except Exception as e:
            log.exception(e)

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.DEFAULT(e),
            )

    except Exception as e:
        log.exception(e)

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DEFAULT(e),
        )


def get_available_models(request: Request) -> list[dict]:
    """
    Retrieve available TTS models based on the configured TTS engine.
    
    This function fetches available text-to-speech models from either OpenAI or ElevenLabs 
    depending on the current TTS engine configuration.
    
    Parameters:
        request (Request): The FastAPI request object containing application state and configuration.
    
    Returns:
        list[dict]: A list of available TTS models, where each model is represented as a dictionary 
                   with 'id' or 'name' and 'id' keys. Returns an empty list if no models are found 
                   or an error occurs during retrieval.
    
    Raises:
        Logs an error if there's a problem fetching models from the ElevenLabs API, but does not 
        raise an exception to the caller.
    
    Notes:
        - For OpenAI, returns hardcoded models: 'tts-1' and 'tts-1-hd'
        - For ElevenLabs, makes an API call to fetch available models using the configured API key
        - Handles potential network or API request errors gracefully
    """
    available_models = []
    if request.app.state.config.TTS_ENGINE == "openai":
        available_models = [{"id": "tts-1"}, {"id": "tts-1-hd"}]
    elif request.app.state.config.TTS_ENGINE == "elevenlabs":
        try:
            response = requests.get(
                "https://api.elevenlabs.io/v1/models",
                headers={
                    "xi-api-key": request.app.state.config.TTS_API_KEY,
                    "Content-Type": "application/json",
                },
                timeout=5,
            )
            response.raise_for_status()
            models = response.json()

            available_models = [
                {"name": model["name"], "id": model["model_id"]} for model in models
            ]
        except requests.RequestException as e:
            log.error(f"Error fetching voices: {str(e)}")
    return available_models


@router.get("/models")
async def get_models(request: Request, user=Depends(get_verified_user)):
    """
    Retrieve available text-to-speech (TTS) models for the configured TTS engine.
    
    This asynchronous endpoint allows authenticated users to fetch a list of available TTS models based on the current configuration.
    
    Parameters:
        request (Request): The FastAPI request object containing application context
        user (dict, optional): Verified user information obtained through dependency injection
    
    Returns:
        dict: A dictionary containing a list of available TTS models under the 'models' key
    
    Raises:
        HTTPException: If there's an error retrieving models from the configured TTS engine
    """
    return {"models": get_available_models(request)}


def get_available_voices(request) -> dict:
    """
    Retrieve available voices for the configured text-to-speech (TTS) engine.
    
    This function dynamically fetches available voices based on the current TTS engine configuration. Supported engines include OpenAI, ElevenLabs, and Azure.
    
    Parameters:
        request (Request): The FastAPI request object containing application state and configuration.
    
    Returns:
        dict: A dictionary mapping voice IDs to voice names. The structure varies by TTS engine:
        - OpenAI: Static predefined voices
        - ElevenLabs: Dynamically fetched voices from API
        - Azure: Voices retrieved from Microsoft Cognitive Services
    
    Raises:
        Handles potential API request exceptions silently, logging errors for Azure voice retrieval.
    
    Notes:
        - For OpenAI, returns a fixed set of predefined voices
        - For ElevenLabs, uses get_elevenlabs_voices() to fetch voices
        - For Azure, makes a direct API call to list available voices
        - Gracefully handles potential API or configuration errors
    """
    available_voices = {}
    if request.app.state.config.TTS_ENGINE == "openai":
        available_voices = {
            "alloy": "alloy",
            "echo": "echo",
            "fable": "fable",
            "onyx": "onyx",
            "nova": "nova",
            "shimmer": "shimmer",
        }
    elif request.app.state.config.TTS_ENGINE == "elevenlabs":
        try:
            available_voices = get_elevenlabs_voices(
                api_key=request.app.state.config.TTS_API_KEY
            )
        except Exception:
            # Avoided @lru_cache with exception
            pass
    elif request.app.state.config.TTS_ENGINE == "azure":
        try:
            region = request.app.state.config.TTS_AZURE_SPEECH_REGION
            url = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/voices/list"
            headers = {
                "Ocp-Apim-Subscription-Key": request.app.state.config.TTS_API_KEY
            }

            response = requests.get(url, headers=headers)
            response.raise_for_status()
            voices = response.json()

            for voice in voices:
                available_voices[voice["ShortName"]] = (
                    f"{voice['DisplayName']} ({voice['ShortName']})"
                )
        except requests.RequestException as e:
            log.error(f"Error fetching voices: {str(e)}")

    return available_voices


@lru_cache
def get_elevenlabs_voices(api_key: str) -> dict:
    """
    Fetches available voices from the ElevenLabs TTS API.
    
    This function retrieves a list of voices from the ElevenLabs API using the provided API key.
    
    Parameters:
        api_key (str): ElevenLabs API key for authentication
    
    Returns:
        dict: A dictionary mapping voice IDs to voice names, where:
            - Keys are unique voice identifiers
            - Values are human-readable voice names
    
    Raises:
        RuntimeError: If there is an error connecting to or retrieving voices from the ElevenLabs API
    
    Example:
        voices = get_elevenlabs_voices('your_api_key')
        # Returns: {'voice_id1': 'Voice Name 1', 'voice_id2': 'Voice Name 2'}
    """

    try:
        # TODO: Add retries
        response = requests.get(
            "https://api.elevenlabs.io/v1/voices",
            headers={
                "xi-api-key": api_key,
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()
        voices_data = response.json()

        voices = {}
        for voice in voices_data.get("voices", []):
            voices[voice["voice_id"]] = voice["name"]
    except requests.RequestException as e:
        # Avoid @lru_cache with exception
        log.error(f"Error fetching voices: {str(e)}")
        raise RuntimeError(f"Error fetching voices: {str(e)}")

    return voices


@router.get("/voices")
async def get_voices(request: Request, user=Depends(get_verified_user)):
    """
    Retrieve available voices for the configured text-to-speech (TTS) engine.
    
    This asynchronous endpoint fetches the list of available voices based on the current TTS configuration and returns them in a structured format.
    
    Parameters:
        request (Request): The FastAPI request object containing configuration context
        user (dict, optional): Verified user information, obtained through dependency injection
    
    Returns:
        dict: A dictionary containing a list of voices, where each voice is represented by:
            - 'id': Unique identifier for the voice
            - 'name': Human-readable name of the voice
    
    Raises:
        HTTPException: If there's an error retrieving voices from the TTS engine
    """
    return {
        "voices": [
            {"id": k, "name": v} for k, v in get_available_voices(request).items()
        ]
    }
