# TODO: Implement a more intelligent load balancing mechanism for distributing requests among multiple backend instances.
# Current implementation uses a simple round-robin approach (random.choice). Consider incorporating algorithms like weighted round-robin,
# least connections, or least response time for better resource utilization and performance optimization.

import asyncio
import json
import logging
import os
import random
import re
import time
from typing import Optional, Union
from urllib.parse import urlparse

import aiohttp
from aiocache import cached

import requests

from fastapi import (
    Depends,
    FastAPI,
    File,
    HTTPException,
    Request,
    UploadFile,
    APIRouter,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
from starlette.background import BackgroundTask


from open_webui.models.models import Models
from open_webui.utils.misc import (
    calculate_sha256,
)
from open_webui.utils.payload import (
    apply_model_params_to_body_ollama,
    apply_model_params_to_body_openai,
    apply_model_system_prompt_to_body,
)
from open_webui.utils.auth import get_admin_user, get_verified_user
from open_webui.utils.access_control import has_access


from open_webui.config import (
    UPLOAD_DIR,
)
from open_webui.env import (
    ENV,
    SRC_LOG_LEVELS,
    AIOHTTP_CLIENT_TIMEOUT,
    AIOHTTP_CLIENT_TIMEOUT_OPENAI_MODEL_LIST,
    BYPASS_MODEL_ACCESS_CONTROL,
)
from open_webui.constants import ERROR_MESSAGES

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["OLLAMA"])


##########################################
#
# Utility functions
#
##########################################


async def send_get_request(url, key=None):
    """
    Send an asynchronous GET request to the specified URL with optional authorization.
    
    This function attempts to retrieve JSON data from a given URL using an HTTP GET request.
    It supports optional API key authentication and has a configurable timeout.
    
    Parameters:
        url (str): The target URL to send the GET request to
        key (str, optional): Authorization bearer token for the request. Defaults to None.
    
    Returns:
        dict or None: JSON response from the server if successful, None if an error occurs
    
    Raises:
        No explicit exceptions, but logs connection errors internally
    
    Notes:
        - Uses aiohttp for asynchronous HTTP requests
        - Sets a predefined timeout to prevent indefinite waiting
        - Automatically handles API key injection if provided
        - Logs any connection errors without interrupting the application flow
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
    if response:
        response.close()
    if session:
        await session.close()


async def send_post_request(
    url: str,
    payload: Union[str, bytes],
    stream: bool = True,
    key: Optional[str] = None,
    content_type: Optional[str] = None,
):

    """
    Send an asynchronous HTTP POST request to a specified URL with optional streaming and authentication.
    
    Sends a POST request with a payload, supporting streaming responses and optional API key authentication. 
    Handles various response types and provides robust error handling.
    
    Parameters:
        url (str): The target URL to send the POST request.
        payload (Union[str, bytes]): The request payload to be sent.
        stream (bool, optional): Whether to stream the response. Defaults to True.
        key (Optional[str], optional): API authorization key. Defaults to None.
        content_type (Optional[str], optional): Override the response content type. Defaults to None.
    
    Returns:
        Union[StreamingResponse, dict]: 
        - If stream is True: A streaming HTTP response 
        - If stream is False: A JSON-parsed response dictionary
    
    Raises:
        HTTPException: For connection errors, authentication issues, or server-side problems.
        - Status code reflects the nature of the error
        - Detailed error message provided when possible
    
    Notes:
        - Uses aiohttp for asynchronous HTTP requests
        - Automatically handles response cleanup
        - Supports custom timeout configuration via AIOHTTP_CLIENT_TIMEOUT
        - Extracts and formats error messages from Ollama API responses
    """
    r = None
    try:
        session = aiohttp.ClientSession(
            trust_env=True, timeout=aiohttp.ClientTimeout(total=AIOHTTP_CLIENT_TIMEOUT)
        )

        r = await session.post(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {key}"} if key else {}),
            },
        )
        r.raise_for_status()

        if stream:
            response_headers = dict(r.headers)

            if content_type:
                response_headers["Content-Type"] = content_type

            return StreamingResponse(
                r.content,
                status_code=r.status,
                headers=response_headers,
                background=BackgroundTask(
                    cleanup_response, response=r, session=session
                ),
            )
        else:
            res = await r.json()
            await cleanup_response(r, session)
            return res

    except Exception as e:
        detail = None

        if r is not None:
            try:
                res = await r.json()
                if "error" in res:
                    detail = f"Ollama: {res.get('error', 'Unknown error')}"
            except Exception:
                detail = f"Ollama: {e}"

        raise HTTPException(
            status_code=r.status if r else 500,
            detail=detail if detail else "Open WebUI: Server Connection Error",
        )


def get_api_key(url, configs):
    """
    Retrieve the API key for a given URL from the provided configurations.
    
    Parameters:
        url (str): The full URL to extract the API key for
        configs (dict): A dictionary of configuration settings containing URL-to-API-key mappings
    
    Returns:
        str or None: The API key associated with the base URL, or None if no key is found
    
    Description:
        Extracts the base URL (scheme + netloc) from the given URL and looks up the corresponding 
        API key in the configurations. This allows for flexible API key management across different 
        base URLs.
    
    Example:
        >>> configs = {
        ...     "https://example.com": {"key": "my_secret_key"},
        ...     "http://localhost:8000": {"key": "local_key"}
        ... }
        >>> get_api_key("https://example.com/api/v1", configs)
        'my_secret_key'
        >>> get_api_key("https://unknown.com/path", configs)
        None
    """
    parsed_url = urlparse(url)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
    return configs.get(base_url, {}).get("key", None)


##########################################
#
# API routes
#
##########################################

router = APIRouter()


@router.head("/")
@router.get("/")
async def get_status():
    """
    Return the service status.
    
    Returns:
        dict: A dictionary with a boolean status indicating the service is operational.
    """
    return {"status": True}


class ConnectionVerificationForm(BaseModel):
    url: str
    key: Optional[str] = None


@router.post("/verify")
async def verify_connection(
    form_data: ConnectionVerificationForm, user=Depends(get_admin_user)
):
    """
    Verify the connection to an Ollama server by checking its version endpoint.
    
    This asynchronous function attempts to establish a connection to a specified URL and retrieve the server's version information. It supports optional authentication via an API key.
    
    Parameters:
        form_data (ConnectionVerificationForm): Contains connection details
            - url (str): The base URL of the Ollama server to verify
            - key (str, optional): Authentication key for the server
    
    Returns:
        dict: Server version information if the connection is successful
    
    Raises:
        HTTPException: 
            - 500 status code for connection errors or unexpected issues
            - Includes detailed error message explaining the connection failure
    
    Notes:
        - Uses aiohttp for asynchronous HTTP requests
        - Applies a timeout to prevent indefinite waiting
        - Logs any exceptions for debugging purposes
        - Requires admin user authentication
    """
    url = form_data.url
    key = form_data.key

    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=AIOHTTP_CLIENT_TIMEOUT_OPENAI_MODEL_LIST)
    ) as session:
        try:
            async with session.get(
                f"{url}/api/version",
                headers={**({"Authorization": f"Bearer {key}"} if key else {})},
            ) as r:
                if r.status != 200:
                    detail = f"HTTP Error: {r.status}"
                    res = await r.json()

                    if "error" in res:
                        detail = f"External Error: {res['error']}"
                    raise Exception(detail)

                data = await r.json()
                return data
        except aiohttp.ClientError as e:
            log.exception(f"Client error: {str(e)}")
            raise HTTPException(
                status_code=500, detail="Open WebUI: Server Connection Error"
            )
        except Exception as e:
            log.exception(f"Unexpected error: {e}")
            error_detail = f"Unexpected error: {str(e)}"
            raise HTTPException(status_code=500, detail=error_detail)


@router.get("/config")
async def get_config(request: Request, user=Depends(get_admin_user)):
    """
    Retrieve the Ollama configuration settings for the application.
    
    This function returns a dictionary containing key configuration parameters related to Ollama API settings, 
    accessible only by administrative users.
    
    Parameters:
        request (Request): The FastAPI request object containing the application state
        user (dict, optional): The authenticated admin user, obtained through dependency injection
    
    Returns:
        dict: A configuration dictionary with the following keys:
            - ENABLE_OLLAMA_API (bool): Flag indicating whether Ollama API is enabled
            - OLLAMA_BASE_URLS (list): List of base URLs for Ollama instances
            - OLLAMA_API_CONFIGS (dict): Configuration details for Ollama API connections
    
    Raises:
        HTTPException: If the user is not authenticated with admin privileges
    """
    return {
        "ENABLE_OLLAMA_API": request.app.state.config.ENABLE_OLLAMA_API,
        "OLLAMA_BASE_URLS": request.app.state.config.OLLAMA_BASE_URLS,
        "OLLAMA_API_CONFIGS": request.app.state.config.OLLAMA_API_CONFIGS,
    }


class OllamaConfigForm(BaseModel):
    ENABLE_OLLAMA_API: Optional[bool] = None
    OLLAMA_BASE_URLS: list[str]
    OLLAMA_API_CONFIGS: dict


@router.post("/config/update")
async def update_config(
    request: Request, form_data: OllamaConfigForm, user=Depends(get_admin_user)
):
    """
    Update the Ollama configuration settings for the application.
    
    This asynchronous function allows an admin user to modify Ollama API configuration parameters, including enabling/disabling the Ollama API and configuring base URLs and API configurations.
    
    Parameters:
        request (Request): The FastAPI request object containing application state
        form_data (OllamaConfigForm): Form data with configuration parameters
        user (dict, optional): Admin user authentication dependency
    
    Returns:
        dict: Updated configuration settings, including:
            - ENABLE_OLLAMA_API (bool): Flag to enable/disable Ollama API
            - OLLAMA_BASE_URLS (list): List of Ollama base URLs
            - OLLAMA_API_CONFIGS (dict): API configurations for each URL
    
    Notes:
        - Requires admin user privileges
        - Removes API configurations for URLs that are no longer in the base URLs list
    """
    request.app.state.config.ENABLE_OLLAMA_API = form_data.ENABLE_OLLAMA_API

    request.app.state.config.OLLAMA_BASE_URLS = form_data.OLLAMA_BASE_URLS
    request.app.state.config.OLLAMA_API_CONFIGS = form_data.OLLAMA_API_CONFIGS

    # Remove any extra configs
    config_urls = request.app.state.config.OLLAMA_API_CONFIGS.keys()
    for url in list(request.app.state.config.OLLAMA_BASE_URLS):
        if url not in config_urls:
            request.app.state.config.OLLAMA_API_CONFIGS.pop(url, None)

    return {
        "ENABLE_OLLAMA_API": request.app.state.config.ENABLE_OLLAMA_API,
        "OLLAMA_BASE_URLS": request.app.state.config.OLLAMA_BASE_URLS,
        "OLLAMA_API_CONFIGS": request.app.state.config.OLLAMA_API_CONFIGS,
    }


@cached(ttl=3)
async def get_all_models(request: Request):
    """
    Retrieve all available Ollama models from configured base URLs.
    
    This asynchronous function fetches model tags from multiple Ollama API endpoints, with support for API key authentication, model filtering, and prefix customization.
    
    Parameters:
        request (Request): The FastAPI request object containing application state and configuration.
    
    Returns:
        dict: A dictionary containing a list of models with their details, including:
            - model: Model name/identifier
            - urls: List of URL indices where the model is available
            - details like size, modified timestamp, etc.
    
    Notes:
        - Respects ENABLE_OLLAMA_API configuration flag
        - Supports per-URL API configurations (enable/disable, API keys)
        - Allows model filtering via model_ids configuration
        - Supports adding prefix to model names
        - Caches retrieved models in request.app.state.OLLAMA_MODELS
    
    Raises:
        Potential network-related exceptions during API requests
    """
    log.info("get_all_models()")
    if request.app.state.config.ENABLE_OLLAMA_API:
        request_tasks = []

        for idx, url in enumerate(request.app.state.config.OLLAMA_BASE_URLS):
            if url not in request.app.state.config.OLLAMA_API_CONFIGS:
                request_tasks.append(send_get_request(f"{url}/api/tags"))
            else:
                api_config = request.app.state.config.OLLAMA_API_CONFIGS.get(url, {})
                enable = api_config.get("enable", True)
                key = api_config.get("key", None)

                if enable:
                    request_tasks.append(send_get_request(f"{url}/api/tags", key))
                else:
                    request_tasks.append(asyncio.ensure_future(asyncio.sleep(0, None)))

        responses = await asyncio.gather(*request_tasks)

        for idx, response in enumerate(responses):
            if response:
                url = request.app.state.config.OLLAMA_BASE_URLS[idx]
                api_config = request.app.state.config.OLLAMA_API_CONFIGS.get(url, {})

                prefix_id = api_config.get("prefix_id", None)
                model_ids = api_config.get("model_ids", [])

                if len(model_ids) != 0 and "models" in response:
                    response["models"] = list(
                        filter(
                            lambda model: model["model"] in model_ids,
                            response["models"],
                        )
                    )

                if prefix_id:
                    for model in response.get("models", []):
                        model["model"] = f"{prefix_id}.{model['model']}"

        def merge_models_lists(model_lists):
            """
            Merge multiple lists of models into a single, consolidated list.
            
            This function takes multiple lists of models and combines them, ensuring that:
            - Each unique model appears only once in the result
            - Models are identified by their unique model ID
            - The 'urls' key tracks the indices of sources where each model was found
            
            Parameters:
                model_lists (list): A list of model lists, where each list contains model dictionaries
            
            Returns:
                list: A consolidated list of unique models, with each model having a 'urls' list indicating its source indices
            
            Example:
                >>> model_lists = [
                ...     [{"model": "gpt-3", "name": "GPT-3"}],
                ...     [{"model": "gpt-3", "name": "GPT-3 Variant"}, 
                ...      {"model": "llama2", "name": "Llama 2"}]
                ... ]
                >>> merge_models_lists(model_lists)
                [
                    {"model": "gpt-3", "name": "GPT-3", "urls": [0, 1]},
                    {"model": "llama2", "name": "Llama 2", "urls": [1]}
                ]
            """
            merged_models = {}

            for idx, model_list in enumerate(model_lists):
                if model_list is not None:
                    for model in model_list:
                        id = model["model"]
                        if id not in merged_models:
                            model["urls"] = [idx]
                            merged_models[id] = model
                        else:
                            merged_models[id]["urls"].append(idx)

            return list(merged_models.values())

        models = {
            "models": merge_models_lists(
                map(
                    lambda response: response.get("models", []) if response else None,
                    responses,
                )
            )
        }

    else:
        models = {"models": []}

    request.app.state.OLLAMA_MODELS = {
        model["model"]: model for model in models["models"]
    }
    return models


async def get_filtered_models(models, user):
    # Filter models based on user access control
    """
    Filter models based on user access control.
    
    This function filters a list of models to return only those that the user has permission to access. 
    It checks each model against the user's access rights, considering both model ownership and explicit access control settings.
    
    Parameters:
        models (dict): A dictionary containing a list of models under the 'models' key.
        user (User): The user object attempting to access the models.
    
    Returns:
        list: A filtered list of models that the user is authorized to view.
    
    Notes:
        - Models owned by the user are always included
        - Other models are filtered based on read access permissions
        - Returns an empty list if no models are accessible
    """
    filtered_models = []
    for model in models.get("models", []):
        model_info = Models.get_model_by_id(model["model"])
        if model_info:
            if user.id == model_info.user_id or has_access(
                user.id, type="read", access_control=model_info.access_control
            ):
                filtered_models.append(model)
    return filtered_models


@router.get("/api/tags")
@router.get("/api/tags/{url_idx}")
async def get_ollama_tags(
    request: Request, url_idx: Optional[int] = None, user=Depends(get_verified_user)
):
    """
    Retrieve model tags from an Ollama server, with optional filtering by user role.
    
    Fetches model tags from either a specific Ollama server URL or all configured URLs. 
    Supports optional API key authentication and user-based model access control.
    
    Parameters:
        request (Request): The FastAPI request object containing application state
        url_idx (int, optional): Index of the specific Ollama server URL to query. 
                                  If None, retrieves tags from all configured URLs.
        user (User, optional): Authenticated user making the request, used for access control
    
    Returns:
        dict: A dictionary containing model tags, potentially filtered by user role
    
    Raises:
        HTTPException: If there's an error connecting to the Ollama server or retrieving model tags
    """
    models = []

    if url_idx is None:
        models = await get_all_models(request)
    else:
        url = request.app.state.config.OLLAMA_BASE_URLS[url_idx]
        key = get_api_key(url, request.app.state.config.OLLAMA_API_CONFIGS)

        r = None
        try:
            r = requests.request(
                method="GET",
                url=f"{url}/api/tags",
                headers={**({"Authorization": f"Bearer {key}"} if key else {})},
            )
            r.raise_for_status()

            models = r.json()
        except Exception as e:
            log.exception(e)

            detail = None
            if r is not None:
                try:
                    res = r.json()
                    if "error" in res:
                        detail = f"Ollama: {res['error']}"
                except Exception:
                    detail = f"Ollama: {e}"

            raise HTTPException(
                status_code=r.status_code if r else 500,
                detail=detail if detail else "Open WebUI: Server Connection Error",
            )

    if user.role == "user" and not BYPASS_MODEL_ACCESS_CONTROL:
        models["models"] = get_filtered_models(models, user)

    return models


@router.get("/api/version")
@router.get("/api/version/{url_idx}")
async def get_ollama_versions(request: Request, url_idx: Optional[int] = None):
    """
    Retrieve the version of Ollama from configured base URLs.
    
    Retrieves the Ollama version either for a specific URL index or across all configured URLs. 
    When no specific index is provided, returns the lowest version found among all configured URLs.
    
    Parameters:
        request (Request): The FastAPI request object containing application state
        url_idx (Optional[int], optional): Index of the specific Ollama URL to query. Defaults to None.
    
    Returns:
        dict: A dictionary containing the Ollama version
            - If a specific URL is queried: Returns that URL's version
            - If no URL index specified: Returns the lowest version across all URLs
            - If Ollama API is disabled: Returns {"version": False}
    
    Raises:
        HTTPException: 
            - 500 error if no Ollama instances are found
            - Connection or server errors when querying Ollama URLs
    
    Notes:
        - Requires ENABLE_OLLAMA_API to be True in configuration
        - Uses asynchronous requests for multiple URL version checks
        - Handles version parsing and comparison using semantic versioning
    """
    if request.app.state.config.ENABLE_OLLAMA_API:
        if url_idx is None:
            # returns lowest version
            request_tasks = [
                send_get_request(
                    f"{url}/api/version",
                    request.app.state.config.OLLAMA_API_CONFIGS.get(url, {}).get(
                        "key", None
                    ),
                )
                for url in request.app.state.config.OLLAMA_BASE_URLS
            ]
            responses = await asyncio.gather(*request_tasks)
            responses = list(filter(lambda x: x is not None, responses))

            if len(responses) > 0:
                lowest_version = min(
                    responses,
                    key=lambda x: tuple(
                        map(int, re.sub(r"^v|-.*", "", x["version"]).split("."))
                    ),
                )

                return {"version": lowest_version["version"]}
            else:
                raise HTTPException(
                    status_code=500,
                    detail=ERROR_MESSAGES.OLLAMA_NOT_FOUND,
                )
        else:
            url = request.app.state.config.OLLAMA_BASE_URLS[url_idx]

            r = None
            try:
                r = requests.request(method="GET", url=f"{url}/api/version")
                r.raise_for_status()

                return r.json()
            except Exception as e:
                log.exception(e)

                detail = None
                if r is not None:
                    try:
                        res = r.json()
                        if "error" in res:
                            detail = f"Ollama: {res['error']}"
                    except Exception:
                        detail = f"Ollama: {e}"

                raise HTTPException(
                    status_code=r.status_code if r else 500,
                    detail=detail if detail else "Open WebUI: Server Connection Error",
                )
    else:
        return {"version": False}


@router.get("/api/ps")
async def get_ollama_loaded_models(request: Request, user=Depends(get_verified_user)):
    """
    Retrieve the list of models currently loaded in Ollama memory across configured backend instances.
    
    This asynchronous function queries all configured Ollama base URLs to fetch the list of loaded models. It supports optional API key authentication for each URL.
    
    Parameters:
        request (Request): The FastAPI request object containing application state
        user (dict, optional): Verified user information, obtained through dependency injection
    
    Returns:
        dict: A dictionary mapping Ollama base URLs to their currently loaded models. 
              Returns an empty dictionary if Ollama API is disabled.
    
    Raises:
        HTTPException: If there are issues connecting to or retrieving data from Ollama instances
    
    Notes:
        - Requires ENABLE_OLLAMA_API to be True in the configuration
        - Uses asynchronous requests to query multiple Ollama instances concurrently
        - Retrieves API keys from OLLAMA_API_CONFIGS if configured
    """
    if request.app.state.config.ENABLE_OLLAMA_API:
        request_tasks = [
            send_get_request(
                f"{url}/api/ps",
                request.app.state.config.OLLAMA_API_CONFIGS.get(url, {}).get(
                    "key", None
                ),
            )
            for url in request.app.state.config.OLLAMA_BASE_URLS
        ]
        responses = await asyncio.gather(*request_tasks)

        return dict(zip(request.app.state.config.OLLAMA_BASE_URLS, responses))
    else:
        return {}


class ModelNameForm(BaseModel):
    name: str


@router.post("/api/pull")
@router.post("/api/pull/{url_idx}")
async def pull_model(
    request: Request,
    form_data: ModelNameForm,
    url_idx: int = 0,
    user=Depends(get_admin_user),
):
    """
    Pull a machine learning model from a specified Ollama server.
    
    Allows an admin user to download and install a model from a configured Ollama base URL.
    
    Parameters:
        request (Request): The incoming HTTP request containing application state
        form_data (ModelNameForm): Form data specifying the model name and optional parameters
        url_idx (int, optional): Index of the Ollama base URL to pull the model from. Defaults to 0.
        user (dict, optional): Admin user credentials, verified through dependency injection
    
    Returns:
        dict: Response from the Ollama server containing model pull operation details
    
    Notes:
        - Requires admin user privileges
        - Uses an insecure pull mode to allow pulling from any source
        - Logs the target URL for traceability
        - Supports optional model-specific configuration during pull
    """
    url = request.app.state.config.OLLAMA_BASE_URLS[url_idx]
    log.info(f"url: {url}")

    # Admin should be able to pull models from any source
    payload = {**form_data.model_dump(exclude_none=True), "insecure": True}

    return await send_post_request(
        url=f"{url}/api/pull",
        payload=json.dumps(payload),
        key=get_api_key(url, request.app.state.config.OLLAMA_API_CONFIGS),
    )


class PushModelForm(BaseModel):
    name: str
    insecure: Optional[bool] = None
    stream: Optional[bool] = None


@router.delete("/api/push")
@router.delete("/api/push/{url_idx}")
async def push_model(
    request: Request,
    form_data: PushModelForm,
    url_idx: Optional[int] = None,
    user=Depends(get_admin_user),
):
    """
    Push a model to a specified Ollama backend instance.
    
    This asynchronous function handles pushing a model to a specific Ollama URL, either by using a provided URL index or by automatically selecting the first available URL for an existing model.
    
    Parameters:
        request (Request): The FastAPI request object containing application state
        form_data (PushModelForm): Form data containing model push details
        url_idx (Optional[int], optional): Index of the target Ollama backend URL. Defaults to None.
        user (User, optional): Authenticated admin user. Defaults to admin user dependency.
    
    Returns:
        Response: The response from the Ollama backend after pushing the model
    
    Raises:
        HTTPException: 400 error if the specified model is not found in available models
    
    Notes:
        - Automatically selects the first URL for a known model if no URL index is provided
        - Requires admin user authentication
        - Logs the target URL for debugging purposes
    """
    if url_idx is None:
        await get_all_models(request)
        models = request.app.state.OLLAMA_MODELS

        if form_data.name in models:
            url_idx = models[form_data.name]["urls"][0]
        else:
            raise HTTPException(
                status_code=400,
                detail=ERROR_MESSAGES.MODEL_NOT_FOUND(form_data.name),
            )

    url = request.app.state.config.OLLAMA_BASE_URLS[url_idx]
    log.debug(f"url: {url}")

    return await send_post_request(
        url=f"{url}/api/push",
        payload=form_data.model_dump_json(exclude_none=True).encode(),
        key=get_api_key(url, request.app.state.config.OLLAMA_API_CONFIGS),
    )


class CreateModelForm(BaseModel):
    name: str
    modelfile: Optional[str] = None
    stream: Optional[bool] = None
    path: Optional[str] = None


@router.post("/api/create")
@router.post("/api/create/{url_idx}")
async def create_model(
    request: Request,
    form_data: CreateModelForm,
    url_idx: int = 0,
    user=Depends(get_admin_user),
):
    """
    Create a new model using the Ollama API.
    
    Sends a POST request to the specified Ollama instance to create a new model based on the provided configuration.
    
    Parameters:
        request (Request): The FastAPI request object containing application state
        form_data (CreateModelForm): Model creation parameters including name, base model, and other configuration details
        url_idx (int, optional): Index of the Ollama base URL to use. Defaults to 0.
        user: Authenticated admin user performing the model creation
    
    Returns:
        Response: The API response from the Ollama server containing model creation details
    
    Raises:
        HTTPException: If there are issues with the model creation request or connection to the Ollama server
    """
    log.debug(f"form_data: {form_data}")
    url = request.app.state.config.OLLAMA_BASE_URLS[url_idx]

    return await send_post_request(
        url=f"{url}/api/create",
        payload=form_data.model_dump_json(exclude_none=True).encode(),
        key=get_api_key(url, request.app.state.config.OLLAMA_API_CONFIGS),
    )


class CopyModelForm(BaseModel):
    source: str
    destination: str


@router.post("/api/copy")
@router.post("/api/copy/{url_idx}")
async def copy_model(
    request: Request,
    form_data: CopyModelForm,
    url_idx: Optional[int] = None,
    user=Depends(get_admin_user),
):
    """
    Copy a machine learning model from one location to another using the Ollama API.
    
    This asynchronous function handles model copying across different Ollama instances, with support for optional URL indexing and admin-level authentication.
    
    Parameters:
        request (Request): The FastAPI request object containing application state.
        form_data (CopyModelForm): Form data specifying source and destination model details.
        url_idx (Optional[int], optional): Index of the target Ollama URL. Defaults to None.
        user (User, optional): Authenticated admin user. Defaults to admin user dependency.
    
    Returns:
        bool: True if the model was successfully copied.
    
    Raises:
        HTTPException: 
            - 400: If the source model is not found
            - 500: If there's a server connection error
            - Specific status codes from Ollama API on failure
    
    Example:
        # Copy a model from one Ollama instance to another
        await copy_model(request, CopyModelForm(source="model_name", destination="new_model_name"))
    """
    if url_idx is None:
        await get_all_models(request)
        models = request.app.state.OLLAMA_MODELS

        if form_data.source in models:
            url_idx = models[form_data.source]["urls"][0]
        else:
            raise HTTPException(
                status_code=400,
                detail=ERROR_MESSAGES.MODEL_NOT_FOUND(form_data.source),
            )

    url = request.app.state.config.OLLAMA_BASE_URLS[url_idx]
    key = get_api_key(url, request.app.state.config.OLLAMA_API_CONFIGS)

    try:
        r = requests.request(
            method="POST",
            url=f"{url}/api/copy",
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {key}"} if key else {}),
            },
            data=form_data.model_dump_json(exclude_none=True).encode(),
        )
        r.raise_for_status()

        log.debug(f"r.text: {r.text}")
        return True
    except Exception as e:
        log.exception(e)

        detail = None
        if r is not None:
            try:
                res = r.json()
                if "error" in res:
                    detail = f"Ollama: {res['error']}"
            except Exception:
                detail = f"Ollama: {e}"

        raise HTTPException(
            status_code=r.status_code if r else 500,
            detail=detail if detail else "Open WebUI: Server Connection Error",
        )


@router.delete("/api/delete")
@router.delete("/api/delete/{url_idx}")
async def delete_model(
    request: Request,
    form_data: ModelNameForm,
    url_idx: Optional[int] = None,
    user=Depends(get_admin_user),
):
    """
    Delete a specified machine learning model from an Ollama server.
    
    Attempts to delete a model by its name from a configured Ollama URL. If no specific URL index is provided, it automatically selects the first available URL for the model.
    
    Parameters:
        request (Request): The FastAPI request object containing application state
        form_data (ModelNameForm): Form data containing the name of the model to delete
        url_idx (Optional[int], optional): Index of the specific Ollama URL to delete the model from. Defaults to None.
        user (User, optional): Admin user performing the deletion. Defaults to admin user verification.
    
    Returns:
        bool: True if the model was successfully deleted
    
    Raises:
        HTTPException: 
            - 400: If the model is not found in the available models
            - 500: If there's a server connection error or deletion fails
            - Specific status code from Ollama server if deletion request fails
    
    Example:
        # Delete a model named 'llama2' from the default Ollama URL
        await delete_model(request, ModelNameForm(name='llama2'))
    """
    if url_idx is None:
        await get_all_models(request)
        models = request.app.state.OLLAMA_MODELS

        if form_data.name in models:
            url_idx = models[form_data.name]["urls"][0]
        else:
            raise HTTPException(
                status_code=400,
                detail=ERROR_MESSAGES.MODEL_NOT_FOUND(form_data.name),
            )

    url = request.app.state.config.OLLAMA_BASE_URLS[url_idx]
    key = get_api_key(url, request.app.state.config.OLLAMA_API_CONFIGS)

    try:
        r = requests.request(
            method="DELETE",
            url=f"{url}/api/delete",
            data=form_data.model_dump_json(exclude_none=True).encode(),
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {key}"} if key else {}),
            },
        )
        r.raise_for_status()

        log.debug(f"r.text: {r.text}")
        return True
    except Exception as e:
        log.exception(e)

        detail = None
        if r is not None:
            try:
                res = r.json()
                if "error" in res:
                    detail = f"Ollama: {res['error']}"
            except Exception:
                detail = f"Ollama: {e}"

        raise HTTPException(
            status_code=r.status_code if r else 500,
            detail=detail if detail else "Open WebUI: Server Connection Error",
        )


@router.post("/api/show")
async def show_model_info(
    request: Request, form_data: ModelNameForm, user=Depends(get_verified_user)
):
    """
    Show detailed information about a specific machine learning model.
    
    This asynchronous function retrieves information about a specified model from an Ollama backend instance. It first validates the model's existence, then randomly selects a URL from available sources and sends a POST request to retrieve the model's details.
    
    Parameters:
        request (Request): The FastAPI request object containing application state
        form_data (ModelNameForm): A form containing the name of the model to show
        user (Optional): The authenticated user (verified by dependency)
    
    Returns:
        dict: Detailed information about the specified model
    
    Raises:
        HTTPException: 
            - 400 if the model is not found
            - 500 or corresponding status code for server connection errors or API issues
    
    Example:
        Request payload: {"name": "llama2"}
        Returns model metadata like size, parameters, details from the Ollama backend
    """
    await get_all_models(request)
    models = request.app.state.OLLAMA_MODELS

    if form_data.name not in models:
        raise HTTPException(
            status_code=400,
            detail=ERROR_MESSAGES.MODEL_NOT_FOUND(form_data.name),
        )

    url_idx = random.choice(models[form_data.name]["urls"])

    url = request.app.state.config.OLLAMA_BASE_URLS[url_idx]
    key = get_api_key(url, request.app.state.config.OLLAMA_API_CONFIGS)

    try:
        r = requests.request(
            method="POST",
            url=f"{url}/api/show",
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {key}"} if key else {}),
            },
            data=form_data.model_dump_json(exclude_none=True).encode(),
        )
        r.raise_for_status()

        return r.json()
    except Exception as e:
        log.exception(e)

        detail = None
        if r is not None:
            try:
                res = r.json()
                if "error" in res:
                    detail = f"Ollama: {res['error']}"
            except Exception:
                detail = f"Ollama: {e}"

        raise HTTPException(
            status_code=r.status_code if r else 500,
            detail=detail if detail else "Open WebUI: Server Connection Error",
        )


class GenerateEmbedForm(BaseModel):
    model: str
    input: list[str] | str
    truncate: Optional[bool] = None
    options: Optional[dict] = None
    keep_alive: Optional[Union[int, str]] = None


@router.post("/api/embed")
@router.post("/api/embed/{url_idx}")
async def embed(
    request: Request,
    form_data: GenerateEmbedForm,
    url_idx: Optional[int] = None,
    user=Depends(get_verified_user),
):
    """
    Generate embeddings for a given input using an Ollama model.
    
    Generates embeddings for the specified input text using a selected machine learning model from the Ollama backend. The function supports multiple Ollama instances and handles model selection, API key authentication, and error management.
    
    Parameters:
        request (Request): The FastAPI request object providing access to application state
        form_data (GenerateEmbedForm): Form data containing embedding generation parameters
            - model (str): Name of the model to use for generating embeddings
            - prompt (str): Input text to generate embeddings for
        url_idx (int, optional): Specific URL index to use for embedding generation. Defaults to None.
        user (User, optional): Authenticated user making the request. Defaults to verified user.
    
    Returns:
        dict: A dictionary containing the generated embeddings
    
    Raises:
        HTTPException: 
            - 400: If the specified model is not found
            - 500: If there's a server connection error
            - Varies: Specific error codes from the Ollama backend
    
    Example:
        # Generate embeddings for a text using a specific model
        embeddings = await embed(request, {
            "model": "nomic-embed-text",
            "prompt": "Hello, world!"
        })
    """
    log.info(f"generate_ollama_batch_embeddings {form_data}")

    if url_idx is None:
        await get_all_models(request)
        models = request.app.state.OLLAMA_MODELS

        model = form_data.model

        if ":" not in model:
            model = f"{model}:latest"

        if model in models:
            url_idx = random.choice(models[model]["urls"])
        else:
            raise HTTPException(
                status_code=400,
                detail=ERROR_MESSAGES.MODEL_NOT_FOUND(form_data.model),
            )

    url = request.app.state.config.OLLAMA_BASE_URLS[url_idx]
    key = get_api_key(url, request.app.state.config.OLLAMA_API_CONFIGS)

    try:
        r = requests.request(
            method="POST",
            url=f"{url}/api/embed",
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {key}"} if key else {}),
            },
            data=form_data.model_dump_json(exclude_none=True).encode(),
        )
        r.raise_for_status()

        data = r.json()
        return data
    except Exception as e:
        log.exception(e)

        detail = None
        if r is not None:
            try:
                res = r.json()
                if "error" in res:
                    detail = f"Ollama: {res['error']}"
            except Exception:
                detail = f"Ollama: {e}"

        raise HTTPException(
            status_code=r.status_code if r else 500,
            detail=detail if detail else "Open WebUI: Server Connection Error",
        )


class GenerateEmbeddingsForm(BaseModel):
    model: str
    prompt: str
    options: Optional[dict] = None
    keep_alive: Optional[Union[int, str]] = None


@router.post("/api/embeddings")
@router.post("/api/embeddings/{url_idx}")
async def embeddings(
    request: Request,
    form_data: GenerateEmbeddingsForm,
    url_idx: Optional[int] = None,
    user=Depends(get_verified_user),
):
    """
    Generate embeddings for a given input using an Ollama model.
    
    Asynchronously sends an embedding generation request to a specified Ollama model URL. If no URL index is provided, it automatically selects a model from available Ollama models.
    
    Parameters:
        request (Request): The FastAPI request object containing application state.
        form_data (GenerateEmbeddingsForm): Form data containing the model and input for embedding generation.
        url_idx (Optional[int], optional): Index of the specific Ollama URL to use. Defaults to None.
        user (User, optional): Verified user making the request. Defaults to get_verified_user dependency.
    
    Returns:
        dict: A dictionary containing the generated embeddings.
    
    Raises:
        HTTPException: 
            - 400: If the specified model is not found
            - 500: If there's a server connection error or Ollama API error
    
    Example:
        form_data = GenerateEmbeddingsForm(
            model="nomic-embed-text:latest", 
            prompt="Generate an embedding for this text"
        )
        embeddings = await embeddings(request, form_data)
    """
    log.info(f"generate_ollama_embeddings {form_data}")

    if url_idx is None:
        await get_all_models(request)
        models = request.app.state.OLLAMA_MODELS

        model = form_data.model

        if ":" not in model:
            model = f"{model}:latest"

        if model in models:
            url_idx = random.choice(models[model]["urls"])
        else:
            raise HTTPException(
                status_code=400,
                detail=ERROR_MESSAGES.MODEL_NOT_FOUND(form_data.model),
            )

    url = request.app.state.config.OLLAMA_BASE_URLS[url_idx]
    key = get_api_key(url, request.app.state.config.OLLAMA_API_CONFIGS)

    try:
        r = requests.request(
            method="POST",
            url=f"{url}/api/embeddings",
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {key}"} if key else {}),
            },
            data=form_data.model_dump_json(exclude_none=True).encode(),
        )
        r.raise_for_status()

        data = r.json()
        return data
    except Exception as e:
        log.exception(e)

        detail = None
        if r is not None:
            try:
                res = r.json()
                if "error" in res:
                    detail = f"Ollama: {res['error']}"
            except Exception:
                detail = f"Ollama: {e}"

        raise HTTPException(
            status_code=r.status_code if r else 500,
            detail=detail if detail else "Open WebUI: Server Connection Error",
        )


class GenerateCompletionForm(BaseModel):
    model: str
    prompt: str
    suffix: Optional[str] = None
    images: Optional[list[str]] = None
    format: Optional[str] = None
    options: Optional[dict] = None
    system: Optional[str] = None
    template: Optional[str] = None
    context: Optional[list[int]] = None
    stream: Optional[bool] = True
    raw: Optional[bool] = None
    keep_alive: Optional[Union[int, str]] = None


@router.post("/api/generate")
@router.post("/api/generate/{url_idx}")
async def generate_completion(
    request: Request,
    form_data: GenerateCompletionForm,
    url_idx: Optional[int] = None,
    user=Depends(get_verified_user),
):
    """
    Generate a completion for a given prompt using a specified model.
    
    This asynchronous function handles model selection, URL routing, and API key management for generating text completions via the Ollama API.
    
    Parameters:
        request (Request): The FastAPI request object containing application state.
        form_data (GenerateCompletionForm): Form data containing model and generation parameters.
        url_idx (Optional[int], optional): Specific URL index to send the request. Defaults to None.
        user (User, optional): Verified user making the request. Defaults to authenticated user.
    
    Returns:
        StreamingResponse: A streaming response containing the generated text completion.
    
    Raises:
        HTTPException: 
            - 400 status code if the specified model is not found
            - Potential network or API-related exceptions during request processing
    
    Notes:
        - Automatically selects a random URL if multiple are configured for a model
        - Supports model version specification with ":latest" default
        - Handles prefix ID configuration for model name mapping
    """
    if url_idx is None:
        await get_all_models(request)
        models = request.app.state.OLLAMA_MODELS

        model = form_data.model

        if ":" not in model:
            model = f"{model}:latest"

        if model in models:
            url_idx = random.choice(models[model]["urls"])
        else:
            raise HTTPException(
                status_code=400,
                detail=ERROR_MESSAGES.MODEL_NOT_FOUND(form_data.model),
            )

    url = request.app.state.config.OLLAMA_BASE_URLS[url_idx]
    api_config = request.app.state.config.OLLAMA_API_CONFIGS.get(url, {})

    prefix_id = api_config.get("prefix_id", None)
    if prefix_id:
        form_data.model = form_data.model.replace(f"{prefix_id}.", "")

    return await send_post_request(
        url=f"{url}/api/generate",
        payload=form_data.model_dump_json(exclude_none=True).encode(),
        key=get_api_key(url, request.app.state.config.OLLAMA_API_CONFIGS),
    )


class ChatMessage(BaseModel):
    role: str
    content: str
    images: Optional[list[str]] = None


class GenerateChatCompletionForm(BaseModel):
    model: str
    messages: list[ChatMessage]
    format: Optional[dict] = None
    options: Optional[dict] = None
    template: Optional[str] = None
    stream: Optional[bool] = True
    keep_alive: Optional[Union[int, str]] = None


async def get_ollama_url(request: Request, model: str, url_idx: Optional[int] = None):
    """
    Retrieve the Ollama URL for a specified model with optional URL index selection.
    
    This function determines the appropriate Ollama service URL for a given model, either by:
    1. Randomly selecting from available URLs for the model if no specific index is provided
    2. Using the specified URL index from the configuration
    
    Parameters:
        request (Request): The FastAPI request object containing application state
        model (str): The name of the machine learning model to retrieve a URL for
        url_idx (Optional[int], optional): Specific index of the Ollama base URL to use. Defaults to None.
    
    Returns:
        str: The selected Ollama base URL for the specified model
    
    Raises:
        HTTPException: If the specified model is not found in the available models, with a 400 status code
    
    Example:
        # Randomly select a URL for a model
        url = await get_ollama_url(request, "llama2")
        
        # Select a specific URL by index
        url = await get_ollama_url(request, "llama2", url_idx=0)
    """
    if url_idx is None:
        models = request.app.state.OLLAMA_MODELS
        if model not in models:
            raise HTTPException(
                status_code=400,
                detail=ERROR_MESSAGES.MODEL_NOT_FOUND(model),
            )
        url_idx = random.choice(models[model].get("urls", []))
    url = request.app.state.config.OLLAMA_BASE_URLS[url_idx]
    return url


@router.post("/api/chat")
@router.post("/api/chat/{url_idx}")
async def generate_chat_completion(
    request: Request,
    form_data: dict,
    url_idx: Optional[int] = None,
    user=Depends(get_verified_user),
    bypass_filter: Optional[bool] = False,
):
    """
    Generate a chat completion using the specified model and parameters.
    
    Sends a chat completion request to an Ollama API endpoint with optional streaming and model-specific configurations.
    
    Parameters:
        request (Request): The FastAPI request object providing access to application state
        form_data (dict): Chat completion request parameters
        url_idx (Optional[int], optional): Index of the Ollama API URL to use. Defaults to None.
        user (User, optional): Authenticated user making the request. Defaults to verified user.
        bypass_filter (Optional[bool], optional): Flag to bypass model access control. Defaults to False.
    
    Returns:
        StreamingResponse: A streaming response containing the generated chat completion
    
    Raises:
        HTTPException: 
            - 400: Invalid request parameters
            - 403: Unauthorized access to the model
            - Any other HTTP errors from the Ollama API
    
    Notes:
        - Applies model-specific parameters and system prompts
        - Handles model access control based on user role
        - Supports optional model prefix and API key configuration
        - Streams response from Ollama API if requested
    """
    if BYPASS_MODEL_ACCESS_CONTROL:
        bypass_filter = True

    try:
        form_data = GenerateChatCompletionForm(**form_data)
    except Exception as e:
        log.exception(e)
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )

    payload = {**form_data.model_dump(exclude_none=True)}
    if "metadata" in payload:
        del payload["metadata"]

    model_id = payload["model"]
    model_info = Models.get_model_by_id(model_id)

    if model_info:
        if model_info.base_model_id:
            payload["model"] = model_info.base_model_id

        params = model_info.params.model_dump()

        if params:
            if payload.get("options") is None:
                payload["options"] = {}

            payload["options"] = apply_model_params_to_body_ollama(
                params, payload["options"]
            )
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

    if ":" not in payload["model"]:
        payload["model"] = f"{payload['model']}:latest"

    url = await get_ollama_url(request, payload["model"], url_idx)
    api_config = request.app.state.config.OLLAMA_API_CONFIGS.get(url, {})

    prefix_id = api_config.get("prefix_id", None)
    if prefix_id:
        payload["model"] = payload["model"].replace(f"{prefix_id}.", "")

    return await send_post_request(
        url=f"{url}/api/chat",
        payload=json.dumps(payload),
        stream=form_data.stream,
        key=get_api_key(url, request.app.state.config.OLLAMA_API_CONFIGS),
        content_type="application/x-ndjson",
    )


# TODO: we should update this part once Ollama supports other types
class OpenAIChatMessageContent(BaseModel):
    type: str
    model_config = ConfigDict(extra="allow")


class OpenAIChatMessage(BaseModel):
    role: str
    content: Union[str, list[OpenAIChatMessageContent]]

    model_config = ConfigDict(extra="allow")


class OpenAIChatCompletionForm(BaseModel):
    model: str
    messages: list[OpenAIChatMessage]

    model_config = ConfigDict(extra="allow")


class OpenAICompletionForm(BaseModel):
    model: str
    prompt: str

    model_config = ConfigDict(extra="allow")


@router.post("/v1/completions")
@router.post("/v1/completions/{url_idx}")
async def generate_openai_completion(
    request: Request,
    form_data: dict,
    url_idx: Optional[int] = None,
    user=Depends(get_verified_user),
):
    """
    Generate an OpenAI-compatible text completion using the specified model and parameters.
    
    Handles model selection, parameter configuration, access control, and API request routing for text completion generation.
    
    Parameters:
        request (Request): The FastAPI request object providing application state and context
        form_data (dict): Completion request parameters conforming to OpenAI's completion specification
        url_idx (Optional[int], optional): Index to select a specific backend URL. Defaults to None.
        user (User, optional): Authenticated user making the request. Defaults to verified user.
    
    Returns:
        StreamingResponse or JSONResponse: Generated text completion from the specified Ollama model
    
    Raises:
        HTTPException: 
            - 400: Invalid request parameters
            - 403: Unauthorized model access
            - Any other API-related errors during model completion generation
    
    Notes:
        - Supports streaming and non-streaming completion generation
        - Applies model-specific parameters if configured
        - Handles model version defaulting to ":latest"
        - Supports user role-based access control for model usage
        - Handles prefix ID configuration for multi-backend setups
    """
    try:
        form_data = OpenAICompletionForm(**form_data)
    except Exception as e:
        log.exception(e)
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )

    payload = {**form_data.model_dump(exclude_none=True, exclude=["metadata"])}
    if "metadata" in payload:
        del payload["metadata"]

    model_id = form_data.model
    if ":" not in model_id:
        model_id = f"{model_id}:latest"

    model_info = Models.get_model_by_id(model_id)
    if model_info:
        if model_info.base_model_id:
            payload["model"] = model_info.base_model_id
        params = model_info.params.model_dump()

        if params:
            payload = apply_model_params_to_body_openai(params, payload)

        # Check if user has access to the model
        if user.role == "user":
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
    else:
        if user.role != "admin":
            raise HTTPException(
                status_code=403,
                detail="Model not found",
            )

    if ":" not in payload["model"]:
        payload["model"] = f"{payload['model']}:latest"

    url = await get_ollama_url(request, payload["model"], url_idx)
    api_config = request.app.state.config.OLLAMA_API_CONFIGS.get(url, {})

    prefix_id = api_config.get("prefix_id", None)

    if prefix_id:
        payload["model"] = payload["model"].replace(f"{prefix_id}.", "")

    return await send_post_request(
        url=f"{url}/v1/completions",
        payload=json.dumps(payload),
        stream=payload.get("stream", False),
        key=get_api_key(url, request.app.state.config.OLLAMA_API_CONFIGS),
    )


@router.post("/v1/chat/completions")
@router.post("/v1/chat/completions/{url_idx}")
async def generate_openai_chat_completion(
    request: Request,
    form_data: dict,
    url_idx: Optional[int] = None,
    user=Depends(get_verified_user),
):
    """
    Generate an OpenAI-compatible chat completion using the specified model and parameters.
    
    Handles model selection, parameter configuration, access control, and streaming responses for chat completions.
    
    Parameters:
        request (Request): The FastAPI request object containing application state
        form_data (dict): Chat completion request payload conforming to OpenAI chat completion schema
        url_idx (Optional[int], optional): Index of the Ollama backend URL to use. Defaults to None.
        user (User, optional): Authenticated user making the request. Defaults to verified user.
    
    Returns:
        StreamingResponse or dict: Chat completion response from the Ollama backend, 
        which can be either a streaming or non-streaming response based on request parameters.
    
    Raises:
        HTTPException: 
            - 400: Invalid request payload
            - 403: Unauthorized access to model
            - Any other HTTP errors from backend request processing
    """
    try:
        completion_form = OpenAIChatCompletionForm(**form_data)
    except Exception as e:
        log.exception(e)
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )

    payload = {**completion_form.model_dump(exclude_none=True, exclude=["metadata"])}
    if "metadata" in payload:
        del payload["metadata"]

    model_id = completion_form.model
    if ":" not in model_id:
        model_id = f"{model_id}:latest"

    model_info = Models.get_model_by_id(model_id)
    if model_info:
        if model_info.base_model_id:
            payload["model"] = model_info.base_model_id

        params = model_info.params.model_dump()

        if params:
            payload = apply_model_params_to_body_openai(params, payload)
            payload = apply_model_system_prompt_to_body(params, payload, user)

        # Check if user has access to the model
        if user.role == "user":
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
    else:
        if user.role != "admin":
            raise HTTPException(
                status_code=403,
                detail="Model not found",
            )

    if ":" not in payload["model"]:
        payload["model"] = f"{payload['model']}:latest"

    url = await get_ollama_url(request, payload["model"], url_idx)
    api_config = request.app.state.config.OLLAMA_API_CONFIGS.get(url, {})

    prefix_id = api_config.get("prefix_id", None)
    if prefix_id:
        payload["model"] = payload["model"].replace(f"{prefix_id}.", "")

    return await send_post_request(
        url=f"{url}/v1/chat/completions",
        payload=json.dumps(payload),
        stream=payload.get("stream", False),
        key=get_api_key(url, request.app.state.config.OLLAMA_API_CONFIGS),
    )


@router.get("/v1/models")
@router.get("/v1/models/{url_idx}")
async def get_openai_models(
    request: Request,
    url_idx: Optional[int] = None,
    user=Depends(get_verified_user),
):

    """
    Retrieves a list of OpenAI-compatible model information from Ollama instances.
    
    This function fetches model tags from either all configured Ollama URLs or a specific URL, 
    transforming the model information into an OpenAI-compatible format. It supports optional 
    filtering based on user access control.
    
    Parameters:
        request (Request): The FastAPI request object containing application state.
        url_idx (Optional[int], optional): Index of a specific Ollama URL to query. Defaults to None.
        user (User, optional): Authenticated user making the request. Defaults to verified user.
    
    Returns:
        dict: A dictionary containing:
            - 'data': List of models with OpenAI-compatible model information
            - 'object': Always set to "list"
    
    Raises:
        HTTPException: If there's a connection error or issue retrieving model information.
    
    Notes:
        - When no specific URL is provided, models are fetched from all configured URLs.
        - For users with role "user", models are filtered based on access control unless 
          BYPASS_MODEL_ACCESS_CONTROL is enabled.
        - Each model entry includes 'id', 'object', 'created', and 'owned_by' fields.
    """
    models = []
    if url_idx is None:
        model_list = await get_all_models(request)
        models = [
            {
                "id": model["model"],
                "object": "model",
                "created": int(time.time()),
                "owned_by": "openai",
            }
            for model in model_list["models"]
        ]

    else:
        url = request.app.state.config.OLLAMA_BASE_URLS[url_idx]
        try:
            r = requests.request(method="GET", url=f"{url}/api/tags")
            r.raise_for_status()

            model_list = r.json()

            models = [
                {
                    "id": model["model"],
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "openai",
                }
                for model in models["models"]
            ]
        except Exception as e:
            log.exception(e)
            error_detail = "Open WebUI: Server Connection Error"
            if r is not None:
                try:
                    res = r.json()
                    if "error" in res:
                        error_detail = f"Ollama: {res['error']}"
                except Exception:
                    error_detail = f"Ollama: {e}"

            raise HTTPException(
                status_code=r.status_code if r else 500,
                detail=error_detail,
            )

    if user.role == "user" and not BYPASS_MODEL_ACCESS_CONTROL:
        # Filter models based on user access control
        filtered_models = []
        for model in models:
            model_info = Models.get_model_by_id(model["id"])
            if model_info:
                if user.id == model_info.user_id or has_access(
                    user.id, type="read", access_control=model_info.access_control
                ):
                    filtered_models.append(model)
        models = filtered_models

    return {
        "data": models,
        "object": "list",
    }


class UrlForm(BaseModel):
    url: str


class UploadBlobForm(BaseModel):
    filename: str


def parse_huggingface_url(hf_url):
    try:
        # Parse the URL
        parsed_url = urlparse(hf_url)

        # Get the path and split it into components
        path_components = parsed_url.path.split("/")

        # Extract the desired output
        model_file = path_components[-1]

        return model_file
    except ValueError:
        return None


async def download_file_stream(
    ollama_url, file_url, file_path, file_name, chunk_size=1024 * 1024
):
    done = False

    if os.path.exists(file_path):
        current_size = os.path.getsize(file_path)
    else:
        current_size = 0

    headers = {"Range": f"bytes={current_size}-"} if current_size > 0 else {}

    timeout = aiohttp.ClientTimeout(total=600)  # Set the timeout

    async with aiohttp.ClientSession(timeout=timeout, trust_env=True) as session:
        async with session.get(file_url, headers=headers) as response:
            total_size = int(response.headers.get("content-length", 0)) + current_size

            with open(file_path, "ab+") as file:
                async for data in response.content.iter_chunked(chunk_size):
                    current_size += len(data)
                    file.write(data)

                    done = current_size == total_size
                    progress = round((current_size / total_size) * 100, 2)

                    yield f'data: {{"progress": {progress}, "completed": {current_size}, "total": {total_size}}}\n\n'

                if done:
                    file.seek(0)
                    hashed = calculate_sha256(file)
                    file.seek(0)

                    url = f"{ollama_url}/api/blobs/sha256:{hashed}"
                    response = requests.post(url, data=file)

                    if response.ok:
                        res = {
                            "done": done,
                            "blob": f"sha256:{hashed}",
                            "name": file_name,
                        }
                        os.remove(file_path)

                        yield f"data: {json.dumps(res)}\n\n"
                    else:
                        raise "Ollama: Could not create blob, Please try again."


# url = "https://huggingface.co/TheBloke/stablelm-zephyr-3b-GGUF/resolve/main/stablelm-zephyr-3b.Q2_K.gguf"
@router.post("/models/download")
@router.post("/models/download/{url_idx}")
async def download_model(
    request: Request,
    form_data: UrlForm,
    url_idx: Optional[int] = None,
    user=Depends(get_admin_user),
):
    """
    Download a model from a specified URL to a local file system.
    
    This function allows downloading machine learning models from allowed hosts (Hugging Face and GitHub) 
    to a specified Ollama backend URL. It validates the source URL, generates a file name, and streams 
    the download process.
    
    Parameters:
        request (Request): The FastAPI request object containing application state
        form_data (UrlForm): Form data containing the source URL of the model
        url_idx (Optional[int], optional): Index of the Ollama base URL to use. Defaults to 0.
        user (User, optional): Admin user performing the download. Authenticated via dependency.
    
    Returns:
        StreamingResponse: A streaming response containing the download progress and file
        None: If the URL cannot be parsed
    
    Raises:
        HTTPException: 400 error if the URL is not from an allowed host
    
    Example:
        POST /models/download
        {
            "url": "https://huggingface.co/model/path/model.bin"
        }
    """
    allowed_hosts = ["https://huggingface.co/", "https://github.com/"]

    if not any(form_data.url.startswith(host) for host in allowed_hosts):
        raise HTTPException(
            status_code=400,
            detail="Invalid file_url. Only URLs from allowed hosts are permitted.",
        )

    if url_idx is None:
        url_idx = 0
    url = request.app.state.config.OLLAMA_BASE_URLS[url_idx]

    file_name = parse_huggingface_url(form_data.url)

    if file_name:
        file_path = f"{UPLOAD_DIR}/{file_name}"

        return StreamingResponse(
            download_file_stream(url, form_data.url, file_path, file_name),
        )
    else:
        return None


@router.post("/models/upload")
@router.post("/models/upload/{url_idx}")
def upload_model(
    request: Request,
    file: UploadFile = File(...),
    url_idx: Optional[int] = None,
    user=Depends(get_admin_user),
):
    """
    Upload a model file to an Ollama server with progress tracking and blob creation.
    
    This function handles file upload to a specified Ollama server, processing the file in chunks and providing real-time upload progress. It calculates the file's SHA256 hash, creates a blob on the server, and streams progress updates.
    
    Parameters:
        request (Request): The FastAPI request object containing application state
        file (UploadFile): The model file to be uploaded
        url_idx (int, optional): Index of the Ollama server URL in configuration. Defaults to 0.
        user (dict): Admin user performing the upload, validated by get_admin_user dependency
    
    Returns:
        StreamingResponse: A streaming response with upload progress and completion status
    
    Raises:
        Exception: If blob creation fails or file processing encounters an error
    
    Example:
        Typically used in a FastAPI route to upload model files to an Ollama server
    """
    if url_idx is None:
        url_idx = 0
    ollama_url = request.app.state.config.OLLAMA_BASE_URLS[url_idx]

    file_path = f"{UPLOAD_DIR}/{file.filename}"

    # Save file in chunks
    with open(file_path, "wb+") as f:
        for chunk in file.file:
            f.write(chunk)

    def file_process_stream():
        nonlocal ollama_url
        total_size = os.path.getsize(file_path)
        chunk_size = 1024 * 1024
        try:
            with open(file_path, "rb") as f:
                total = 0
                done = False

                while not done:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        done = True
                        continue

                    total += len(chunk)
                    progress = round((total / total_size) * 100, 2)

                    res = {
                        "progress": progress,
                        "total": total_size,
                        "completed": total,
                    }
                    yield f"data: {json.dumps(res)}\n\n"

                if done:
                    f.seek(0)
                    hashed = calculate_sha256(f)
                    f.seek(0)

                    url = f"{ollama_url}/api/blobs/sha256:{hashed}"
                    response = requests.post(url, data=f)

                    if response.ok:
                        res = {
                            "done": done,
                            "blob": f"sha256:{hashed}",
                            "name": file.filename,
                        }
                        os.remove(file_path)
                        yield f"data: {json.dumps(res)}\n\n"
                    else:
                        raise Exception(
                            "Ollama: Could not create blob, Please try again."
                        )

        except Exception as e:
            res = {"error": str(e)}
            yield f"data: {json.dumps(res)}\n\n"

    return StreamingResponse(file_process_stream(), media_type="text/event-stream")
