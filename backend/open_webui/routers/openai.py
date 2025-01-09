import asyncio
import hashlib
import json
import logging
from pathlib import Path
from typing import Literal, Optional, overload

import aiohttp
from aiocache import cached
import requests


from fastapi import Depends, FastAPI, HTTPException, Request, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask

from open_webui.models.models import Models
from open_webui.config import (
    CACHE_DIR,
)
from open_webui.env import (
    AIOHTTP_CLIENT_TIMEOUT,
    AIOHTTP_CLIENT_TIMEOUT_OPENAI_MODEL_LIST,
    ENABLE_FORWARD_USER_INFO_HEADERS,
    BYPASS_MODEL_ACCESS_CONTROL,
)

from open_webui.constants import ERROR_MESSAGES
from open_webui.env import ENV, SRC_LOG_LEVELS


from open_webui.utils.payload import (
    apply_model_params_to_body_openai,
    apply_model_system_prompt_to_body,
)

from open_webui.utils.auth import get_admin_user, get_verified_user
from open_webui.utils.access_control import has_access


log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["OPENAI"])


##########################################
#
# Utility functions
#
##########################################


async def send_get_request(url, key=None):
    """
    Send an asynchronous GET request to a specified URL with optional authorization.
    
    This function attempts to retrieve JSON data from a given URL, with an optional authorization key.
    It uses aiohttp for making the asynchronous HTTP request and includes a configurable timeout.
    
    Parameters:
        url (str): The target URL to send the GET request to
        key (str, optional): Authorization bearer token for the request. Defaults to None.
    
    Returns:
        dict or None: JSON response from the URL if successful, None if a connection error occurs
    
    Raises:
        No explicit exceptions are raised; connection errors are logged and return None
    
    Example:
        response = await send_get_request("https://api.example.com/models", key="my_api_key")
    """
    timeout = aiohttp.ClientTimeout(total=AIOHTTP_CLIENT_TIMEOUT_OPENAI_MODEL_LIST)
    try:
        async with aiohttp.ClientSession(timeout=timeout, trust_env=True) as session:
            async with session.get(
                url, headers={**({"Authorization": f"Bearer {key}"} if key else {})}
            ) as response:
                return await response.json()
    except Exception as e:
        # Handle connection error here
        log.error(f"Connection error: {e}")
        return None


async def cleanup_response(
    response: Optional[aiohttp.ClientResponse],
    session: Optional[aiohttp.ClientSession],
):
    """
    Asynchronously close an HTTP response and its associated client session.
    
    This utility function ensures proper cleanup of aiohttp resources by closing both the response and the session if they are provided.
    
    Parameters:
        response (Optional[aiohttp.ClientResponse]): The HTTP response to close. Can be None.
        session (Optional[aiohttp.ClientSession]): The client session to close. Can be None.
    
    Note:
        - If the response is not None, it will be closed immediately.
        - If the session is not None, it will be asynchronously closed.
        - Safe to call with None values for either parameter.
    """
    if response:
        response.close()
    if session:
        await session.close()


def openai_o1_handler(payload):
    """
    Modify payload parameters for OpenAI O1 model compatibility.
    
    This function prepares the payload for the O1 model by making two key adjustments:
    1. Converts "max_tokens" to "max_completion_tokens" to match O1 model specifications
    2. Transforms any initial system message to a user message, as O1 does not support system messages
    
    Parameters:
        payload (dict): The original request payload for the OpenAI API
    
    Returns:
        dict: Modified payload compatible with O1 model requirements
    """
    if "max_tokens" in payload:
        # Remove "max_tokens" from the payload
        payload["max_completion_tokens"] = payload["max_tokens"]
        del payload["max_tokens"]

    # Fix: O1 does not support the "system" parameter, Modify "system" to "user"
    if payload["messages"][0]["role"] == "system":
        payload["messages"][0]["role"] = "user"

    return payload


##########################################
#
# API routes
#
##########################################

router = APIRouter()


@router.get("/config")
async def get_config(request: Request, user=Depends(get_admin_user)):
    """
    Retrieve the current OpenAI API configuration settings.
    
    This asynchronous function returns a dictionary containing the current configuration for OpenAI API integration. Access is restricted to admin users.
    
    Parameters:
        request (Request): The incoming HTTP request containing application state
        user (dict, optional): Admin user authentication dependency
    
    Returns:
        dict: A configuration dictionary with the following keys:
            - ENABLE_OPENAI_API (bool): Flag indicating if OpenAI API is enabled
            - OPENAI_API_BASE_URLS (list): List of configured OpenAI API base URLs
            - OPENAI_API_KEYS (list): List of configured OpenAI API keys
            - OPENAI_API_CONFIGS (dict): Additional OpenAI API configuration settings
    """
    return {
        "ENABLE_OPENAI_API": request.app.state.config.ENABLE_OPENAI_API,
        "OPENAI_API_BASE_URLS": request.app.state.config.OPENAI_API_BASE_URLS,
        "OPENAI_API_KEYS": request.app.state.config.OPENAI_API_KEYS,
        "OPENAI_API_CONFIGS": request.app.state.config.OPENAI_API_CONFIGS,
    }


class OpenAIConfigForm(BaseModel):
    ENABLE_OPENAI_API: Optional[bool] = None
    OPENAI_API_BASE_URLS: list[str]
    OPENAI_API_KEYS: list[str]
    OPENAI_API_CONFIGS: dict


@router.post("/config/update")
async def update_config(
    request: Request, form_data: OpenAIConfigForm, user=Depends(get_admin_user)
):
    """
    Update the configuration settings for OpenAI API integration.
    
    This asynchronous function allows an admin user to modify the OpenAI API configuration, including enabling/disabling the API, 
    setting base URLs, API keys, and additional configurations.
    
    Parameters:
        request (Request): The incoming HTTP request containing the application state.
        form_data (OpenAIConfigForm): A form containing the new configuration settings.
        user (dict, optional): The admin user performing the configuration update. Defaults to the result of get_admin_user dependency.
    
    Returns:
        dict: A dictionary containing the updated configuration settings, including:
            - ENABLE_OPENAI_API (bool): Flag to enable or disable OpenAI API
            - OPENAI_API_BASE_URLS (list): List of OpenAI API base URLs
            - OPENAI_API_KEYS (list): List of corresponding API keys
            - OPENAI_API_CONFIGS (dict): Additional API configurations
    
    Notes:
        - Ensures that the number of API keys matches the number of base URLs
        - Truncates or pads API keys list to match base URLs length
        - Removes any configuration entries for URLs no longer in the base URLs list
    """
    request.app.state.config.ENABLE_OPENAI_API = form_data.ENABLE_OPENAI_API
    request.app.state.config.OPENAI_API_BASE_URLS = form_data.OPENAI_API_BASE_URLS
    request.app.state.config.OPENAI_API_KEYS = form_data.OPENAI_API_KEYS

    # Check if API KEYS length is same than API URLS length
    if len(request.app.state.config.OPENAI_API_KEYS) != len(
        request.app.state.config.OPENAI_API_BASE_URLS
    ):
        if len(request.app.state.config.OPENAI_API_KEYS) > len(
            request.app.state.config.OPENAI_API_BASE_URLS
        ):
            request.app.state.config.OPENAI_API_KEYS = (
                request.app.state.config.OPENAI_API_KEYS[
                    : len(request.app.state.config.OPENAI_API_BASE_URLS)
                ]
            )
        else:
            request.app.state.config.OPENAI_API_KEYS += [""] * (
                len(request.app.state.config.OPENAI_API_BASE_URLS)
                - len(request.app.state.config.OPENAI_API_KEYS)
            )

    request.app.state.config.OPENAI_API_CONFIGS = form_data.OPENAI_API_CONFIGS

    # Remove any extra configs
    config_urls = request.app.state.config.OPENAI_API_CONFIGS.keys()
    for idx, url in enumerate(request.app.state.config.OPENAI_API_BASE_URLS):
        if url not in config_urls:
            request.app.state.config.OPENAI_API_CONFIGS.pop(url, None)

    return {
        "ENABLE_OPENAI_API": request.app.state.config.ENABLE_OPENAI_API,
        "OPENAI_API_BASE_URLS": request.app.state.config.OPENAI_API_BASE_URLS,
        "OPENAI_API_KEYS": request.app.state.config.OPENAI_API_KEYS,
        "OPENAI_API_CONFIGS": request.app.state.config.OPENAI_API_CONFIGS,
    }


@router.post("/audio/speech")
async def speech(request: Request, user=Depends(get_verified_user)):
    """
    Generate text-to-speech audio from input text using OpenAI's speech API.
    
    Generates an MP3 audio file from text input by sending a request to the OpenAI speech API. 
    Implements caching to avoid regenerating identical audio files and supports multiple API configurations.
    
    Parameters:
        request (Request): The incoming HTTP request containing the text-to-speech payload
        user (User, optional): Verified user making the request, used for optional user info headers
    
    Returns:
        FileResponse: An MP3 audio file generated from the input text
    
    Raises:
        HTTPException: If there are connection issues, API errors, or configuration problems
            - 401: If OpenAI API configuration is not found
            - 500: If server connection fails or external API returns an error
    
    Notes:
        - Caches generated audio files using SHA256 hash of request body
        - Supports optional user information headers
        - Handles streaming response from OpenAI API
        - Saves both audio file and original request body for reference
    """
    idx = None
    try:
        idx = request.app.state.config.OPENAI_API_BASE_URLS.index(
            "https://api.openai.com/v1"
        )

        body = await request.body()
        name = hashlib.sha256(body).hexdigest()

        SPEECH_CACHE_DIR = Path(CACHE_DIR).joinpath("./audio/speech/")
        SPEECH_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        file_path = SPEECH_CACHE_DIR.joinpath(f"{name}.mp3")
        file_body_path = SPEECH_CACHE_DIR.joinpath(f"{name}.json")

        # Check if the file already exists in the cache
        if file_path.is_file():
            return FileResponse(file_path)

        url = request.app.state.config.OPENAI_API_BASE_URLS[idx]

        r = None
        try:
            r = requests.post(
                url=f"{url}/audio/speech",
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {request.app.state.config.OPENAI_API_KEYS[idx]}",
                    **(
                        {
                            "HTTP-Referer": "https://openwebui.com/",
                            "X-Title": "Open WebUI",
                        }
                        if "openrouter.ai" in url
                        else {}
                    ),
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
                stream=True,
            )

            r.raise_for_status()

            # Save the streaming content to a file
            with open(file_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)

            with open(file_body_path, "w") as f:
                json.dump(json.loads(body.decode("utf-8")), f)

            # Return the saved file
            return FileResponse(file_path)

        except Exception as e:
            log.exception(e)

            detail = None
            if r is not None:
                try:
                    res = r.json()
                    if "error" in res:
                        detail = f"External: {res['error']}"
                except Exception:
                    detail = f"External: {e}"

            raise HTTPException(
                status_code=r.status_code if r else 500,
                detail=detail if detail else "Open WebUI: Server Connection Error",
            )

    except ValueError:
        raise HTTPException(status_code=401, detail=ERROR_MESSAGES.OPENAI_NOT_FOUND)


async def get_all_models_responses(request: Request) -> list:
    """
    Asynchronously retrieve model responses from configured OpenAI API URLs.
    
    This function handles fetching model information from multiple OpenAI API endpoints, with support for custom configurations and API key management.
    
    Parameters:
        request (Request): The incoming HTTP request containing application state configuration.
    
    Returns:
        list: A list of model responses from each configured API URL. Each response can be a list of models or a dictionary containing model data.
    
    Behavior:
        - Checks if OpenAI API is enabled
        - Synchronizes the number of API keys and URLs
        - Supports custom model configurations per URL
        - Handles cases with predefined model lists or dynamic model fetching
        - Applies optional prefix to model IDs
        - Returns empty list if OpenAI API is disabled
    
    Raises:
        No explicit exceptions, but may raise network-related errors during API requests.
    
    Notes:
        - Uses asynchronous tasks to fetch models concurrently
        - Supports skipping model fetching for disabled API configurations
        - Logs debug information about retrieved model responses
    """
    if not request.app.state.config.ENABLE_OPENAI_API:
        return []

    # Check if API KEYS length is same than API URLS length
    num_urls = len(request.app.state.config.OPENAI_API_BASE_URLS)
    num_keys = len(request.app.state.config.OPENAI_API_KEYS)

    if num_keys != num_urls:
        # if there are more keys than urls, remove the extra keys
        if num_keys > num_urls:
            new_keys = request.app.state.config.OPENAI_API_KEYS[:num_urls]
            request.app.state.config.OPENAI_API_KEYS = new_keys
        # if there are more urls than keys, add empty keys
        else:
            request.app.state.config.OPENAI_API_KEYS += [""] * (num_urls - num_keys)

    request_tasks = []
    for idx, url in enumerate(request.app.state.config.OPENAI_API_BASE_URLS):
        if url not in request.app.state.config.OPENAI_API_CONFIGS:
            request_tasks.append(
                send_get_request(
                    f"{url}/models", request.app.state.config.OPENAI_API_KEYS[idx]
                )
            )
        else:
            api_config = request.app.state.config.OPENAI_API_CONFIGS.get(url, {})

            enable = api_config.get("enable", True)
            model_ids = api_config.get("model_ids", [])

            if enable:
                if len(model_ids) == 0:
                    request_tasks.append(
                        send_get_request(
                            f"{url}/models",
                            request.app.state.config.OPENAI_API_KEYS[idx],
                        )
                    )
                else:
                    model_list = {
                        "object": "list",
                        "data": [
                            {
                                "id": model_id,
                                "name": model_id,
                                "owned_by": "openai",
                                "openai": {"id": model_id},
                                "urlIdx": idx,
                            }
                            for model_id in model_ids
                        ],
                    }

                    request_tasks.append(
                        asyncio.ensure_future(asyncio.sleep(0, model_list))
                    )
            else:
                request_tasks.append(asyncio.ensure_future(asyncio.sleep(0, None)))

    responses = await asyncio.gather(*request_tasks)

    for idx, response in enumerate(responses):
        if response:
            url = request.app.state.config.OPENAI_API_BASE_URLS[idx]
            api_config = request.app.state.config.OPENAI_API_CONFIGS.get(url, {})

            prefix_id = api_config.get("prefix_id", None)

            if prefix_id:
                for model in (
                    response if isinstance(response, list) else response.get("data", [])
                ):
                    model["id"] = f"{prefix_id}.{model['id']}"

    log.debug(f"get_all_models:responses() {responses}")
    return responses


async def get_filtered_models(models, user):
    # Filter models based on user access control
    """
    Filter models based on user access control.
    
    This function filters a list of models to return only those that the user has permission to access. 
    It checks each model against the user's access rights, considering both model ownership and explicit access control settings.
    
    Parameters:
        models (dict): A dictionary containing a list of models under the 'data' key.
        user (User): The user object attempting to access the models.
    
    Returns:
        list: A filtered list of models that the user is authorized to view.
    
    Notes:
        - Models are filtered based on two criteria:
          1. The user is the owner of the model (model_info.user_id matches user.id)
          2. The user has been granted read access through the model's access control settings
        - Uses the Models.get_model_by_id() method to retrieve model information
        - Utilizes the has_access() function to check specific access permissions
    """
    filtered_models = []
    for model in models.get("data", []):
        model_info = Models.get_model_by_id(model["id"])
        if model_info:
            if user.id == model_info.user_id or has_access(
                user.id, type="read", access_control=model_info.access_control
            ):
                filtered_models.append(model)
    return filtered_models


@cached(ttl=3)
async def get_all_models(request: Request) -> dict[str, list]:
    """
    Retrieves and merges OpenAI models from configured API endpoints.
    
    This asynchronous function fetches models from multiple OpenAI API URLs, filters and transforms the model data, and caches the results. It supports configuration-based model retrieval and filtering.
    
    Parameters:
        request (Request): The FastAPI request object containing application state and configuration.
    
    Returns:
        dict[str, list]: A dictionary containing a list of processed OpenAI models with additional metadata.
            Each model includes:
            - name: Model name (defaults to model ID)
            - owned_by: Set to "openai"
            - openai: Original model data
            - urlIdx: Index of the source API URL
    
    Raises:
        No explicit exceptions, but logs potential errors during model retrieval.
    
    Notes:
        - Skips model retrieval if OpenAI API is disabled in configuration
        - Filters out certain models based on predefined criteria
        - Caches retrieved models in application state for subsequent access
    """
    log.info("get_all_models()")

    if not request.app.state.config.ENABLE_OPENAI_API:
        return {"data": []}

    responses = await get_all_models_responses(request)

    def extract_data(response):
        """
        Extracts and returns data from a response object or list.
        
        This utility function handles different response formats by attempting to retrieve the 'data' key or returning the input directly if it's a list.
        
        Parameters:
            response (dict or list): The response object to extract data from
        
        Returns:
            list or None: The extracted data list, or None if no data could be extracted
        """
        if response and "data" in response:
            return response["data"]
        if isinstance(response, list):
            return response
        return None

    def merge_models_lists(model_lists):
        """
        Merge lists of models from different sources, filtering and enriching model information.
        
        This function consolidates model lists from multiple sources, applying specific filtering criteria
        and adding metadata to each model entry. It ensures that only relevant models are included
        and enhances each model with additional context.
        
        Parameters:
            model_lists (list): A list of model lists from different API sources.
        
        Returns:
            list: A merged and filtered list of models, each augmented with additional metadata.
        
        Key Filtering Criteria:
            - Excludes models from OpenAI's base URLs that match certain deprecated or specific model names
            - Adds URL index, ownership information, and ensures each model has a name
            - Handles potential None or error-containing model lists
        
        Example:
            input_lists = [
                [{"id": "gpt-3.5-turbo", "object": "model"}, ...],
                [{"id": "claude-2", "object": "model"}, ...]
            ]
            result = merge_models_lists(input_lists)
        """
        log.debug(f"merge_models_lists {model_lists}")
        merged_list = []

        for idx, models in enumerate(model_lists):
            if models is not None and "error" not in models:
                merged_list.extend(
                    [
                        {
                            **model,
                            "name": model.get("name", model["id"]),
                            "owned_by": "openai",
                            "openai": model,
                            "urlIdx": idx,
                        }
                        for model in models
                        if "api.openai.com"
                        not in request.app.state.config.OPENAI_API_BASE_URLS[idx]
                        or not any(
                            name in model["id"]
                            for name in [
                                "babbage",
                                "dall-e",
                                "davinci",
                                "embedding",
                                "tts",
                                "whisper",
                            ]
                        )
                    ]
                )

        return merged_list

    models = {"data": merge_models_lists(map(extract_data, responses))}
    log.debug(f"models: {models}")

    request.app.state.OPENAI_MODELS = {model["id"]: model for model in models["data"]}
    return models


@router.get("/models")
@router.get("/models/{url_idx}")
async def get_models(
    request: Request, url_idx: Optional[int] = None, user=Depends(get_verified_user)
):
    """
    Retrieve available AI models from a specified OpenAI API endpoint.
    
    This asynchronous function fetches a list of AI models, with optional filtering based on the provided URL index and user role.
    
    Parameters:
        request (Request): The incoming HTTP request containing application state and configuration.
        url_idx (int, optional): Index of the OpenAI API URL to retrieve models from. If None, retrieves models from all configured URLs.
        user (User): Authenticated user making the request, obtained through dependency injection.
    
    Returns:
        dict: A dictionary containing a list of available AI models, potentially filtered based on user role.
    
    Raises:
        HTTPException: If there are connection issues or unexpected errors during model retrieval.
        - 500 status code for server connection errors or unexpected exceptions
    
    Notes:
        - For OpenAI API, filters out certain model types like babbage, dall-e, davinci, etc.
        - Supports user role-based model access control when BYPASS_MODEL_ACCESS_CONTROL is False.
        - Includes optional user information headers when ENABLE_FORWARD_USER_INFO_HEADERS is True.
    """
    models = {
        "data": [],
    }

    if url_idx is None:
        models = await get_all_models(request)
    else:
        url = request.app.state.config.OPENAI_API_BASE_URLS[url_idx]
        key = request.app.state.config.OPENAI_API_KEYS[url_idx]

        r = None
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(
                total=AIOHTTP_CLIENT_TIMEOUT_OPENAI_MODEL_LIST
            )
        ) as session:
            try:
                async with session.get(
                    f"{url}/models",
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
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
                    if r.status != 200:
                        # Extract response error details if available
                        error_detail = f"HTTP Error: {r.status}"
                        res = await r.json()
                        if "error" in res:
                            error_detail = f"External Error: {res['error']}"
                        raise Exception(error_detail)

                    response_data = await r.json()

                    # Check if we're calling OpenAI API based on the URL
                    if "api.openai.com" in url:
                        # Filter models according to the specified conditions
                        response_data["data"] = [
                            model
                            for model in response_data.get("data", [])
                            if not any(
                                name in model["id"]
                                for name in [
                                    "babbage",
                                    "dall-e",
                                    "davinci",
                                    "embedding",
                                    "tts",
                                    "whisper",
                                ]
                            )
                        ]

                    models = response_data
            except aiohttp.ClientError as e:
                # ClientError covers all aiohttp requests issues
                log.exception(f"Client error: {str(e)}")
                raise HTTPException(
                    status_code=500, detail="Open WebUI: Server Connection Error"
                )
            except Exception as e:
                log.exception(f"Unexpected error: {e}")
                error_detail = f"Unexpected error: {str(e)}"
                raise HTTPException(status_code=500, detail=error_detail)

    if user.role == "user" and not BYPASS_MODEL_ACCESS_CONTROL:
        models["data"] = get_filtered_models(models, user)

    return models


class ConnectionVerificationForm(BaseModel):
    url: str
    key: str


@router.post("/verify")
async def verify_connection(
    form_data: ConnectionVerificationForm, user=Depends(get_admin_user)
):
    """
    Verify the connection to an OpenAI-compatible API endpoint.
    
    Attempts to establish a connection to the specified API URL using the provided authentication key by making a GET request to the '/models' endpoint.
    
    Parameters:
        form_data (ConnectionVerificationForm): Contains the API URL and authentication key
        user (dict, optional): Admin user performing the connection verification
    
    Returns:
        dict: JSON response containing available models from the API endpoint
    
    Raises:
        HTTPException: 
            - 500 status code if connection fails due to client errors or unexpected issues
            - Includes detailed error messages from the API or connection process
    
    Notes:
        - Uses aiohttp for asynchronous HTTP requests
        - Sets a timeout for the connection attempt
        - Logs any exceptions encountered during the connection verification
        - Requires admin user authentication
    """
    url = form_data.url
    key = form_data.key

    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=AIOHTTP_CLIENT_TIMEOUT_OPENAI_MODEL_LIST)
    ) as session:
        try:
            async with session.get(
                f"{url}/models",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
            ) as r:
                if r.status != 200:
                    # Extract response error details if available
                    error_detail = f"HTTP Error: {r.status}"
                    res = await r.json()
                    if "error" in res:
                        error_detail = f"External Error: {res['error']}"
                    raise Exception(error_detail)

                response_data = await r.json()
                return response_data

        except aiohttp.ClientError as e:
            # ClientError covers all aiohttp requests issues
            log.exception(f"Client error: {str(e)}")
            raise HTTPException(
                status_code=500, detail="Open WebUI: Server Connection Error"
            )
        except Exception as e:
            log.exception(f"Unexpected error: {e}")
            error_detail = f"Unexpected error: {str(e)}"
            raise HTTPException(status_code=500, detail=error_detail)


@router.post("/chat/completions")
async def generate_chat_completion(
    request: Request,
    form_data: dict,
    user=Depends(get_verified_user),
    bypass_filter: Optional[bool] = False,
):
    """
    Generate a chat completion by sending a request to the OpenAI API with the specified payload and user context.
    
    This function handles complex chat completion generation with support for:
    - Model-specific parameter overrides
    - User access control
    - Streaming and non-streaming responses
    - Different API configurations
    - Error handling and logging
    
    Parameters:
        request (Request): The FastAPI request object containing application state
        form_data (dict): The payload containing chat completion parameters
        user (User, optional): The authenticated user making the request
        bypass_filter (bool, optional): Flag to bypass model access control checks
    
    Returns:
        Union[dict, StreamingResponse]: The chat completion response or a streaming response
    
    Raises:
        HTTPException: If there are issues with model access, API connection, or request processing
    """
    if BYPASS_MODEL_ACCESS_CONTROL:
        bypass_filter = True

    idx = 0
    payload = {**form_data}
    if "metadata" in payload:
        del payload["metadata"]

    model_id = form_data.get("model")
    model_info = Models.get_model_by_id(model_id)

    # Check model info and override the payload
    if model_info:
        if model_info.base_model_id:
            payload["model"] = model_info.base_model_id
            model_id = model_info.base_model_id

        params = model_info.params.model_dump()
        payload = apply_model_params_to_body_openai(params, payload)
        payload = apply_model_system_prompt_to_body(params, payload, user)

        # Check if user has access to the model
        if not bypass_filter and user.role == "user":
            if not (
                user.id == model_info.user_id
                or has_access(
                    user.id, type="read", access_control=model_info.access_control
                )
            ):
                raise HTTPException(
                    status_code=403,
                    detail="Model not found",
                )
    elif not bypass_filter:
        if user.role != "admin":
            raise HTTPException(
                status_code=403,
                detail="Model not found",
            )

    model = request.app.state.OPENAI_MODELS.get(model_id)
    if model:
        idx = model["urlIdx"]
    else:
        raise HTTPException(
            status_code=404,
            detail="Model not found",
        )

    # Get the API config for the model
    api_config = request.app.state.config.OPENAI_API_CONFIGS.get(
        request.app.state.config.OPENAI_API_BASE_URLS[idx], {}
    )

    prefix_id = api_config.get("prefix_id", None)
    if prefix_id:
        payload["model"] = payload["model"].replace(f"{prefix_id}.", "")

    # Add user info to the payload if the model is a pipeline
    if "pipeline" in model and model.get("pipeline"):
        payload["user"] = {
            "name": user.name,
            "id": user.id,
            "email": user.email,
            "role": user.role,
        }

    url = request.app.state.config.OPENAI_API_BASE_URLS[idx]
    key = request.app.state.config.OPENAI_API_KEYS[idx]

    # Fix: O1 does not support the "max_tokens" parameter, Modify "max_tokens" to "max_completion_tokens"
    is_o1 = payload["model"].lower().startswith("o1-")
    if is_o1:
        payload = openai_o1_handler(payload)
    elif "api.openai.com" not in url:
        # Remove "max_completion_tokens" from the payload for backward compatibility
        if "max_completion_tokens" in payload:
            payload["max_tokens"] = payload["max_completion_tokens"]
            del payload["max_completion_tokens"]

    if "max_tokens" in payload and "max_completion_tokens" in payload:
        del payload["max_tokens"]

    # Convert the modified body back to JSON
    payload = json.dumps(payload)

    r = None
    session = None
    streaming = False
    response = None

    try:
        session = aiohttp.ClientSession(
            trust_env=True, timeout=aiohttp.ClientTimeout(total=AIOHTTP_CLIENT_TIMEOUT)
        )

        r = await session.request(
            method="POST",
            url=f"{url}/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                **(
                    {
                        "HTTP-Referer": "https://openwebui.com/",
                        "X-Title": "Open WebUI",
                    }
                    if "openrouter.ai" in url
                    else {}
                ),
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
        )

        # Check if response is SSE
        if "text/event-stream" in r.headers.get("Content-Type", ""):
            streaming = True
            return StreamingResponse(
                r.content,
                status_code=r.status,
                headers=dict(r.headers),
                background=BackgroundTask(
                    cleanup_response, response=r, session=session
                ),
            )
        else:
            try:
                response = await r.json()
            except Exception as e:
                log.error(e)
                response = await r.text()

            r.raise_for_status()
            return response
    except Exception as e:
        log.exception(e)

        detail = None
        if isinstance(response, dict):
            if "error" in response:
                detail = f"{response['error']['message'] if 'message' in response['error'] else response['error']}"
        elif isinstance(response, str):
            detail = response

        raise HTTPException(
            status_code=r.status if r else 500,
            detail=detail if detail else "Open WebUI: Server Connection Error",
        )
    finally:
        if not streaming and session:
            if r:
                r.close()
            await session.close()


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy(path: str, request: Request, user=Depends(get_verified_user)):
    """
    Proxy endpoint for forwarding requests to OpenAI API with user authentication and streaming support.
    
    This method is deprecated and serves as a pass-through for API requests to OpenAI, handling both streaming and non-streaming responses.
    
    Parameters:
        path (str): The API endpoint path to be proxied
        request (Request): The incoming HTTP request containing method, body, and headers
        user (User, optional): Authenticated user making the request, retrieved via dependency injection
    
    Returns:
        Union[dict, StreamingResponse]: JSON response for non-streaming requests or a streaming response for event-stream content
    
    Raises:
        HTTPException: If there's an error connecting to the external API or processing the request
    
    Notes:
        - Supports forwarding user information via headers if ENABLE_FORWARD_USER_INFO_HEADERS is True
        - Handles both streaming (SSE) and non-streaming API responses
        - Automatically manages client session and response cleanup
        - Logs any exceptions during the proxy request
    """

    body = await request.body()

    idx = 0
    url = request.app.state.config.OPENAI_API_BASE_URLS[idx]
    key = request.app.state.config.OPENAI_API_KEYS[idx]

    r = None
    session = None
    streaming = False

    try:
        session = aiohttp.ClientSession(trust_env=True)
        r = await session.request(
            method=request.method,
            url=f"{url}/{path}",
            data=body,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
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
        )
        r.raise_for_status()

        # Check if response is SSE
        if "text/event-stream" in r.headers.get("Content-Type", ""):
            streaming = True
            return StreamingResponse(
                r.content,
                status_code=r.status,
                headers=dict(r.headers),
                background=BackgroundTask(
                    cleanup_response, response=r, session=session
                ),
            )
        else:
            response_data = await r.json()
            return response_data

    except Exception as e:
        log.exception(e)

        detail = None
        if r is not None:
            try:
                res = await r.json()
                print(res)
                if "error" in res:
                    detail = f"External: {res['error']['message'] if 'message' in res['error'] else res['error']}"
            except Exception:
                detail = f"External: {e}"
        raise HTTPException(
            status_code=r.status if r else 500,
            detail=detail if detail else "Open WebUI: Server Connection Error",
        )
    finally:
        if not streaming and session:
            if r:
                r.close()
            await session.close()
