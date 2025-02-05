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


def get_api_key(idx, url, configs):
    """
    Retrieve an API key from a configuration dictionary using an index or the base URL.
    
    This function extracts the base URL (scheme and network location) from the given URL and attempts to retrieve
    the corresponding API configuration. It first checks for a configuration using the provided index (converted to a string).
    If that lookup fails, it falls back to using the base URL, providing legacy support for configurations keyed by URL.
    
    Parameters:
        idx (Any): An identifier (typically an int or str) used to index into the configuration dictionary.
        url (str): The full URL from which to derive the base URL.
        configs (dict): A mapping of configuration entries where keys can be string representations of indices or base URLs.
                        Each entry should be a dictionary containing a "key" field with the API key.
    
    Returns:
        Optional[str]: The API key if found; otherwise, None.
    
    Examples:
        >>> configs = {"1": {"key": "abc123"}, "http://example.com": {"key": "legacy456"}}
        >>> get_api_key(1, "http://example.com/path", configs)
        "abc123"
        >>> get_api_key(2, "http://example.com/path", configs)
        "legacy456"
    """
    parsed_url = urlparse(url)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
    return configs.get(str(idx), configs.get(base_url, {})).get(
        "key", None
    )  # Legacy support


##########################################
#
# API routes
#
##########################################

router = APIRouter()


@router.head("/")
@router.get("/")
async def get_status():
    return {"status": True}


class ConnectionVerificationForm(BaseModel):
    url: str
    key: Optional[str] = None


@router.post("/verify")
async def verify_connection(
    form_data: ConnectionVerificationForm, user=Depends(get_admin_user)
):
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
    Update the application's Ollama API configuration.
    
    This asynchronous function updates the FastAPI application's state configuration using the provided form data.
    It sets the ENABLE_OLLAMA_API flag, updates the list of OLLAMA_BASE_URLS, and refreshes the OLLAMA_API_CONFIGS while
    filtering out any API configuration entries that do not correspond to any of the current base URLs.
    
    Parameters:
        request (Request): The incoming HTTP request containing the application's state.
        form_data (OllamaConfigForm): Form data containing new configuration values for the Ollama API. It should include:
            - ENABLE_OLLAMA_API: A boolean flag indicating if the Ollama API should be enabled.
            - OLLAMA_BASE_URLS: A list of base URLs to be used for the Ollama API.
            - OLLAMA_API_CONFIGS: A dictionary mapping string keys to API configuration details.
        user: The admin user dependency ensuring that only authorized users can update the configuration.
    
    Returns:
        dict: A dictionary containing the updated configuration with the following keys:
            - "ENABLE_OLLAMA_API": The updated boolean flag.
            - "OLLAMA_BASE_URLS": The updated list of base URLs.
            - "OLLAMA_API_CONFIGS": The filtered dictionary of API configurations.
    """
    request.app.state.config.ENABLE_OLLAMA_API = form_data.ENABLE_OLLAMA_API

    request.app.state.config.OLLAMA_BASE_URLS = form_data.OLLAMA_BASE_URLS
    request.app.state.config.OLLAMA_API_CONFIGS = form_data.OLLAMA_API_CONFIGS

    # Remove the API configs that are not in the API URLS
    keys = list(map(str, range(len(request.app.state.config.OLLAMA_BASE_URLS))))
    request.app.state.config.OLLAMA_API_CONFIGS = {
        key: value
        for key, value in request.app.state.config.OLLAMA_API_CONFIGS.items()
        if key in keys
    }

    return {
        "ENABLE_OLLAMA_API": request.app.state.config.ENABLE_OLLAMA_API,
        "OLLAMA_BASE_URLS": request.app.state.config.OLLAMA_BASE_URLS,
        "OLLAMA_API_CONFIGS": request.app.state.config.OLLAMA_API_CONFIGS,
    }


@cached(ttl=3)
async def get_all_models(request: Request):
    """
    Retrieve and aggregate model information from configured OLLAMA API endpoints.
    
    This asynchronous function concurrently sends GET requests to all base URLs specified in the application's configuration. It fetches model tags from each endpoint using legacy or new API configuration parameters (supporting both string indices and URL keys) and processes the responses:
      - Filters models based on an optional list of allowed model IDs.
      - Optionally prepends a prefix to the model identifier if specified.
      - Merges models from multiple endpoints, including a record of the originating URL indices in a "urls" field.
    
    The aggregated model data is stored in the application's state under `OLLAMA_MODELS` as a mapping from model ID to model details, and a dictionary with a key `"models"` (containing a list of merged model records) is returned.
    
    Parameters:
        request (Request): The incoming HTTP request object that provides access to the application state and configuration,
                           including OLLAMA API settings.
    
    Returns:
        dict: A dictionary with a key "models" containing a list of model objects. Each model object includes model details
              and a "urls" field listing the indices of the base URLs where the model was found.
    
    Side Effects:
        Updates `request.app.state.OLLAMA_MODELS` with a dictionary mapping model IDs to their corresponding model data.
    """
    log.info("get_all_models()")
    if request.app.state.config.ENABLE_OLLAMA_API:
        request_tasks = []
        for idx, url in enumerate(request.app.state.config.OLLAMA_BASE_URLS):
            if (str(idx) not in request.app.state.config.OLLAMA_API_CONFIGS) and (
                url not in request.app.state.config.OLLAMA_API_CONFIGS  # Legacy support
            ):
                request_tasks.append(send_get_request(f"{url}/api/tags"))
            else:
                api_config = request.app.state.config.OLLAMA_API_CONFIGS.get(
                    str(idx),
                    request.app.state.config.OLLAMA_API_CONFIGS.get(
                        url, {}
                    ),  # Legacy support
                )

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
                api_config = request.app.state.config.OLLAMA_API_CONFIGS.get(
                    str(idx),
                    request.app.state.config.OLLAMA_API_CONFIGS.get(
                        url, {}
                    ),  # Legacy support
                )

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
    Retrieve Ollama model tags from a configured backend.
    
    This asynchronous function fetches model tags either by retrieving all models via a default endpoint
    or by targeting a specific backend URL based on the provided index. When a specific url_idx is provided,
    the function constructs the request URL from the application configuration and retrieves the associated API key.
    It then performs an HTTP GET request to obtain the tags. If url_idx is None, the function calls a helper
    to fetch all available models. Additionally, if the user's role is "user" and model access control is not bypassed,
    the returned model list is filtered based on the user's permissions.
    
    Parameters:
        request (Request): The FastAPI request object containing application state and configuration.
        url_idx (Optional[int]): Index corresponding to a specific external API URL in the configuration. If None,
                                 tags for all models are retrieved.
        user: The verified user object obtained via dependency injection, used for access control filtering.
    
    Returns:
        dict: A dictionary containing model tag information. Typically, the dictionary includes a "models" key
              with a list of model tags, potentially filtered based on user permissions.
    
    Raises:
        HTTPException: If the HTTP GET request to the external API fails, or if an error occurs while processing the request.
    """
    models = []

    if url_idx is None:
        models = await get_all_models(request)
    else:
        url = request.app.state.config.OLLAMA_BASE_URLS[url_idx]
        key = get_api_key(url_idx, url, request.app.state.config.OLLAMA_API_CONFIGS)

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
    Retrieve the Ollama API version from configured endpoints.
    
    This asynchronous function interacts with the external Ollama API to obtain its version. When the Ollama API is enabled, the behavior is as follows:
    - If `url_idx` is None, the function asynchronously sends GET requests to the `/api/version` endpoint for all configured Ollama base URLs. It filters out any None responses, compares the version numbers (after stripping a leading "v" and any suffix), and returns the lowest version found.
    - If a specific `url_idx` is provided, the function synchronously sends a GET request to the `/api/version` endpoint of the corresponding Ollama base URL. If the request fails or returns an error, the function logs the exception and raises an HTTPException with appropriate status code and error detail.
    
    If the Ollama API is disabled in the configuration, the function immediately returns {"version": False}.
    
    Parameters:
        request (Request): The FastAPI request object containing application state and configuration settings.
        url_idx (Optional[int], optional): The index of the specific Ollama base URL to query. If not provided, the function queries all endpoints
            and returns the lowest version. Defaults to None.
    
    Returns:
        dict: A dictionary with the key "version" containing a version string if successful, or {"version": False} if the API is disabled.
    
    Raises:
        HTTPException: If no valid version information is retrieved from any endpoint when querying all URLs, or if the request to a specific endpoint fails.
    """
    if request.app.state.config.ENABLE_OLLAMA_API:
        if url_idx is None:
            # returns lowest version
            request_tasks = [
                send_get_request(
                    f"{url}/api/version",
                    request.app.state.config.OLLAMA_API_CONFIGS.get(
                        str(idx),
                        request.app.state.config.OLLAMA_API_CONFIGS.get(
                            url, {}
                        ),  # Legacy support
                    ).get("key", None),
                )
                for idx, url in enumerate(request.app.state.config.OLLAMA_BASE_URLS)
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
    Asynchronously retrieves the models currently loaded in memory on each configured Ollama node.
    
    This function iterates over each base URL specified in the application's configuration (found in 
    `request.app.state.config.OLLAMA_BASE_URLS`) and sends asynchronous GET requests to the `/api/ps` endpoint 
    of the Ollama API. For each URL, it retrieves the corresponding API key from the configuration (`OLLAMA_API_CONFIGS`), 
    with support for legacy key lookup based on the URL if an index-based lookup is not available. The responses 
    from all nodes are gathered concurrently using `asyncio.gather` and then mapped to their respective base URLs and returned.
    
    Parameters:
        request (Request): The FastAPI request object providing access to application state and configuration.
        user (Any): The authenticated user object obtained via dependency injection through `get_verified_user`. 
                    This parameter ensures that the endpoint is accessed by an authorized user.
    
    Returns:
        dict: A dictionary mapping each Ollama base URL (str) to its loaded models response. 
              If the Ollama API is disabled in the configuration (i.e., `ENABLE_OLLAMA_API` is False), an empty dictionary is returned.
    
    Example:
        If the configuration contains two base URLs, the returned dictionary might look like:
            {
                "http://ollama-node1.example.com": {"models": [...]},
                "http://ollama-node2.example.com": {"models": [...]}
            }
    """
    if request.app.state.config.ENABLE_OLLAMA_API:
        request_tasks = [
            send_get_request(
                f"{url}/api/ps",
                request.app.state.config.OLLAMA_API_CONFIGS.get(
                    str(idx),
                    request.app.state.config.OLLAMA_API_CONFIGS.get(
                        url, {}
                    ),  # Legacy support
                ).get("key", None),
            )
            for idx, url in enumerate(request.app.state.config.OLLAMA_BASE_URLS)
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
    Pulls a model from an external endpoint using the specified model name and configuration.
    
    This asynchronous function extracts the target base URL for the pull operation from the application's configuration
    using the provided index (url_idx), constructs a payload from the ModelNameForm data with an "insecure" flag set to True,
    and sends a POST request to the external API's pull endpoint. Administrative privileges are required, as enforced by the
    user dependency.
    
    Parameters:
        request (Request): FastAPI request object containing the application state and configuration.
        form_data (ModelNameForm): Form data containing the model name and additional parameters for the pull request.
        url_idx (int, optional): Index to select the target base URL from the configuration's OLLAMA_BASE_URLS list. Default is 0.
        user: Dependency injection ensuring the user has administrative privileges (obtained via get_admin_user).
    
    Returns:
        Awaitable: The asynchronous result of the POST request made by send_post_request, typically a response object
        or a dictionary representing the outcome of the pull operation.
    
    Raises:
        HTTPException: If the external API request fails or returns an error, an HTTPException is raised with the relevant status code and message.
    
    Example:
        response = await pull_model(request, form_data, url_idx=1)
        if response.get("status") == "success":
            print("Model pulled successfully.")
    """
    url = request.app.state.config.OLLAMA_BASE_URLS[url_idx]
    log.info(f"url: {url}")

    # Admin should be able to pull models from any source
    payload = {**form_data.model_dump(exclude_none=True), "insecure": True}

    return await send_post_request(
        url=f"{url}/api/pull",
        payload=json.dumps(payload),
        key=get_api_key(url_idx, url, request.app.state.config.OLLAMA_API_CONFIGS),
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
    Pushes a model to an external API endpoint using a POST request.
    
    If the URL index is not provided, the function retrieves all models from the application state by invoking `get_all_models`. It then attempts to determine the appropriate URL index by checking if the model name specified in `form_data.name` exists in the state. If the model is found, the first associated URL index is used; otherwise, an HTTP 400 error is raised indicating that the model was not found.
    
    Parameters:
        request (Request): The current FastAPI request object containing the application state.
        form_data (PushModelForm): Form data containing model details. Must include the model "name" and can include additional parameters.
        url_idx (Optional[int]): An optional index specifying which URL from the configuration to use. If not provided, the function will select the URL based on the model name.
        user: An injected dependency ensuring the caller is an admin user.
    
    Returns:
        The response returned by the POST request to the external API, as obtained from `send_post_request`.
    
    Raises:
        HTTPException: If the model specified in `form_data.name` is not found, raises an HTTP 400 error with a detail message indicating the model was not found.
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
        key=get_api_key(url_idx, url, request.app.state.config.OLLAMA_API_CONFIGS),
    )


class CreateModelForm(BaseModel):
    model: Optional[str] = None
    stream: Optional[bool] = None
    path: Optional[str] = None

    model_config = ConfigDict(extra="allow")


@router.post("/api/create")
@router.post("/api/create/{url_idx}")
async def create_model(
    request: Request,
    form_data: CreateModelForm,
    url_idx: int = 0,
    user=Depends(get_admin_user),
):
    """
    Asynchronously creates a new model by sending a POST request to the external API's '/api/create' endpoint.
    
    This function extracts the appropriate base URL using the provided index from the application configuration,
    serializes the model creation data from the form, and retrieves the required API key from the configuration.
    The request is sent only after an admin user is authenticated via a dependency.
    
    Parameters:
        request (Request): The incoming FastAPI request object, used to access the application's state and configuration.
        form_data (CreateModelForm): A Pydantic model containing the data required to create the model.
        url_idx (int, optional): The index to select the base URL from the application's configuration (default is 0).
        user: The admin user obtained via dependency injection to ensure the requester has administrative privileges.
    
    Returns:
        The response from the external API as returned by the asynchronous POST request to create the model.
    
    Raises:
        HTTPException: Propagates any HTTP errors encountered during the POST request.
    """
    log.debug(f"form_data: {form_data}")
    url = request.app.state.config.OLLAMA_BASE_URLS[url_idx]

    return await send_post_request(
        url=f"{url}/api/create",
        payload=form_data.model_dump_json(exclude_none=True).encode(),
        key=get_api_key(url_idx, url, request.app.state.config.OLLAMA_API_CONFIGS),
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
    Copies a machine learning model by forwarding a POST request to an external API.
    
    This asynchronous function handles the copying of a model using the provided form data. If the URL index (url_idx)
    is not specified, it retrieves all models from the application state and determines the URL index based on the source
    model provided in form_data. If the source model is not found, an HTTPException with status code 400 is raised.
    
    The function constructs the target URL from the application's configuration, retrieves the corresponding API key,
    and sends a POST request to the "/api/copy" endpoint. On a successful request, it returns True. In the event of a failure,
    it logs the exception, attempts to extract error details from the response, and raises an HTTPException with the
    appropriate status code and message.
    
    Parameters:
        request (Request): The FastAPI request object containing application state and configuration details.
        form_data (CopyModelForm): The form data that includes the source model identifier and additional parameters
                                   required for the copy operation.
        url_idx (Optional[int], optional): The index used to select the target URL from the configuration. If not provided,
                                           the function will derive it from the cached model data. Defaults to None.
        user: An injected dependency representing the admin user, ensuring that only authorized users can perform the operation.
    
    Returns:
        bool: True if the model copy operation is successful.
    
    Raises:
        HTTPException: If the specified model is not found in the cached models or if the external API request fails.
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
    key = get_api_key(url_idx, url, request.app.state.config.OLLAMA_API_CONFIGS)

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
    Deletes a model via an external API.
    
    This asynchronous function deletes a specified model by sending an HTTP DELETE request to an external Ollama API endpoint. If no URL index is provided, it fetches the available models from the application state and automatically selects the base URL associated with the model. The function also retrieves an authorization key based on the URL index and configuration. On successful deletion, it returns True; otherwise, it raises an HTTPException with relevant error details.
    
    Parameters:
        request (Request): FastAPI Request object containing application state and configuration.
        form_data (ModelNameForm): Form data containing the name of the model to be deleted.
        url_idx (Optional[int], optional): Index for selecting the base URL from the configuration. Defaults to None.
        user: The admin user object, injected via dependency, ensuring that only authorized users can perform deletion.
    
    Returns:
        bool: True if the deletion was successful.
    
    Raises:
        HTTPException: If the model is not found or if the deletion request fails due to a server or connection error.
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
    key = get_api_key(url_idx, url, request.app.state.config.OLLAMA_API_CONFIGS)

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
    Retrieve detailed information about a model specified by its name.
    
    This asynchronous endpoint verifies that the requested model exists in the application's state, randomly selects one of the model's associated URLs, retrieves the appropriate API key based on the selected URL, and then forwards a POST request to the external API's '/api/show' endpoint to fetch detailed model information. The JSON response from the external API is returned.
    
    Parameters:
        request (Request): The incoming FastAPI request containing application state and configuration.
        form_data (ModelNameForm): The form payload with the model name to retrieve information for.
        user: The verified user object provided via dependency injection for access control.
    
    Returns:
        dict: A JSON dictionary with details about the requested model as returned by the external API.
    
    Raises:
        HTTPException: 
            - If the specified model name does not exist in the current model registry.
            - If an error occurs during the external API call, providing an appropriate error message.
            
    Example:
        If a valid model name is provided, a successful response might be:
        
            {
                "name": "example-model",
                "version": "1.0",
                "description": "A sample model used for demonstration purposes."
            }
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
    key = get_api_key(url_idx, url, request.app.state.config.OLLAMA_API_CONFIGS)

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
    Generate embeddings for the given input using the Ollama API.
    
    This asynchronous endpoint logs the embedding request and determines the appropriate base URL to use. If no URL index is provided, the function retrieves the list of available models from the application's state and normalizes the model name (appending ":latest" if no version is specified). It then selects a random URL index from the available models; if the model is not found, an HTTP 400 error is raised. The function retrieves the corresponding API key and sends a POST request to the "/api/embed" endpoint with the JSON-encoded form data. On success, the JSON response from the Ollama API is returned. In case of errors during the request, an HTTPException is raised with the relevant status code and error details.
    
    Parameters:
        request (Request): The incoming HTTP request object.
        form_data (GenerateEmbedForm): Form data containing the embedding request details including the model.
        url_idx (Optional[int]): Optional index specifying which base URL to use. If not provided, a lookup is performed.
        user: The verified user dependency injected via FastAPI's Depends(get_verified_user).
    
    Returns:
        dict: The JSON response from the Ollama API containing the generated embeddings.
    
    Raises:
        HTTPException: 
            - If the specified model is not found (400 status).
            - For any errors occurring during the POST request, with the status code from the Ollama API or 500 if unavailable.
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
    key = get_api_key(url_idx, url, request.app.state.config.OLLAMA_API_CONFIGS)

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
    Generate embeddings using a specified model via an external API call.
    
    Parameters:
        request (Request): FastAPI request object containing the application state.
        form_data (GenerateEmbeddingsForm): Form data with model information used for generating embeddings.
        url_idx (Optional[int], optional): Index specifying which base URL to use. If None, the model list is refreshed and the URL is chosen based on the model name. Defaults to None.
        user: A dependency-injected verified user, ensuring that the request is authenticated.
    
    Returns:
        dict: A JSON dictionary containing the embeddings response from the external API.
    
    Raises:
        HTTPException: 
            - If the specified model is not found in the available models.
            - If the external API call fails (e.g., an error response is received), with the corresponding HTTP status code and error message.
     
    Notes:
        - The function logs its operations and exceptions for debugging purposes.
        - When url_idx is not provided, the model name is normalized by appending ':latest' if necessary.
        - The external API key is retrieved based on the provided URL index and configuration.
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
    key = get_api_key(url_idx, url, request.app.state.config.OLLAMA_API_CONFIGS)

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
    Generate a completion for a given prompt using a specified model via the OLLAMA API.
    
    This asynchronous function first determines the correct base URL to use for generating a completion. If the optional URL index (url_idx) is not provided, it retrieves the list of available models from the application state and searches for the requested model. If the provided model name lacks a version suffix (indicated by ":"), it appends ":latest" by default. When a matching model is found, a random URL index from the model's available URLs is chosen; otherwise, an HTTPException is raised indicating that the model was not found.
    
    Once the URL index is determined, the function fetches the corresponding base URL and API configuration from the application state. If an API configuration prefix (prefix_id) is present, it is stripped from the model identifier before making the request. Finally, the function sends an asynchronous POST request to the external API's "/api/generate" endpoint with a payload derived from the form_data, along with the appropriate API key obtained via the get_api_key function.
    
    Parameters:
        request (Request): The FastAPI request object, used to access the application state.
        form_data (GenerateCompletionForm): The form data containing the model identifier and additional settings for generating a completion.
        url_idx (Optional[int], optional): The index specifying which configured URL to use. If not provided, the function attempts to select an appropriate index based on available models.
        user: A dependency-injected verified user object (obtained via get_verified_user) ensuring that the request is authenticated.
    
    Returns:
        The response from the external API as returned by send_post_request, which typically includes the generated completion.
    
    Raises:
        HTTPException: If the specified model is not found in the available models (status code 400).
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
    api_config = request.app.state.config.OLLAMA_API_CONFIGS.get(
        str(url_idx),
        request.app.state.config.OLLAMA_API_CONFIGS.get(url, {}),  # Legacy support
    )

    prefix_id = api_config.get("prefix_id", None)
    if prefix_id:
        form_data.model = form_data.model.replace(f"{prefix_id}.", "")

    return await send_post_request(
        url=f"{url}/api/generate",
        payload=form_data.model_dump_json(exclude_none=True).encode(),
        key=get_api_key(url_idx, url, request.app.state.config.OLLAMA_API_CONFIGS),
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
    Retrieve an Ollama URL and its index for a given model.
    
    This asynchronous function obtains the URL associated with a specified model by using the application's state.
    If no URL index is provided, the function randomly selects one from the list of URLs for the model.
    If the model is not present in the state's OLLAMA_MODELS, the function raises an HTTPException with a 400 status code.
    
    Parameters:
        request (Request): The FastAPI request object containing the application's state with OLLAMA_MODELS and configuration.
        model (str): The name of the model for which the URL is to be retrieved.
        url_idx (Optional[int], optional): The index corresponding to an entry in the OLLAMA_BASE_URLS.
            If not provided, a random index from the model's available URLs is selected.
    
    Returns:
        Tuple[str, int]: A tuple containing the selected URL and the URL index used.
    
    Raises:
        HTTPException: If the model is not found in the application's OLLAMA_MODELS.
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
    return url, url_idx


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
    Generate chat completions asynchronously using an external API.
    
    This function processes a chat completion request by validating and transforming the provided form data,
    applying model-specific parameters and system prompts, and enforcing user access control.
    After processing, it sends the modified payload to an external chat API endpoint and returns its response.
    The endpoint URL and API configuration are determined using the provided URL index with legacy support.
    
    Parameters:
        request (Request): The FastAPI request object.
        form_data (dict): Dictionary containing chat parameters; must conform to the schema defined by GenerateChatCompletionForm.
        url_idx (Optional[int]): Optional index to select a specific API endpoint configuration. Defaults to None.
        user: The authenticated user object provided via dependency injection from get_verified_user.
        bypass_filter (Optional[bool]): Flag to bypass model access control checks. Defaults to False.
    
    Returns:
        The response from the external API as returned by send_post_request, which may be a stream or a complete response
        in NDJSON format.
    
    Raises:
        HTTPException: 
            400 if the form_data fails validation.
            403 if the user does not have access to the requested model.
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

    url, url_idx = await get_ollama_url(request, payload["model"], url_idx)
    api_config = request.app.state.config.OLLAMA_API_CONFIGS.get(
        str(url_idx),
        request.app.state.config.OLLAMA_API_CONFIGS.get(url, {}),  # Legacy support
    )

    prefix_id = api_config.get("prefix_id", None)
    if prefix_id:
        payload["model"] = payload["model"].replace(f"{prefix_id}.", "")

    return await send_post_request(
        url=f"{url}/api/chat",
        payload=json.dumps(payload),
        stream=form_data.stream,
        key=get_api_key(url_idx, url, request.app.state.config.OLLAMA_API_CONFIGS),
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
    Asynchronously generates an OpenAI-style completion by validating form data, processing model configuration, and forwarding the request to an external API.
    
    This function validates the input form data against the OpenAICompletionForm schema, normalizes the model identifier to include a ":latest" suffix if not provided, and retrieves corresponding model configuration. If model information is available, it applies any model-specific parameters and verifies the user's access rights before invoking a POST request to the external completion endpoint. The target API URL and key are determined dynamically using the provided URL index and application configuration.
    
    Parameters:
        request (Request): The incoming FastAPI request object.
        form_data (dict): A dictionary containing the form data for the completion request.
        url_idx (Optional[int]): An optional index for selecting the correct external API URL and configuration.
        user: The authenticated user, obtained through dependency injection (using get_verified_user).
    
    Returns:
        An asynchronous response from the external API endpoint, which typically streams the generated completion.
    
    Raises:
        HTTPException: If form data validation fails (status code 400) or if the user is unauthorized to access the requested model (status code 403).
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

    url, url_idx = await get_ollama_url(request, payload["model"], url_idx)
    api_config = request.app.state.config.OLLAMA_API_CONFIGS.get(
        str(url_idx),
        request.app.state.config.OLLAMA_API_CONFIGS.get(url, {}),  # Legacy support
    )

    prefix_id = api_config.get("prefix_id", None)

    if prefix_id:
        payload["model"] = payload["model"].replace(f"{prefix_id}.", "")

    return await send_post_request(
        url=f"{url}/v1/completions",
        payload=json.dumps(payload),
        stream=payload.get("stream", False),
        key=get_api_key(url_idx, url, request.app.state.config.OLLAMA_API_CONFIGS),
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
    Generate a chat completion request for OpenAI's API via an external service.
    
    This asynchronous function processes an incoming request to generate a chat completion. It validates the input form data by instantiating an OpenAIChatCompletionForm and constructs a request payload from its attributes. If the provided model identifier lacks a version delimiter (i.e., a colon), it appends the default version "latest". The function then retrieves model information, applies relevant model parameters and system prompts to the payload, and enforces access control for non-admin users. Based on the provided or legacy URL index, it determines the appropriate external service URL and API configuration. Finally, it modifies the model identifier if a prefix is configured, and sends a POST request to the external API endpoint to generate a chat completion, optionally streaming the response.
    
    Parameters:
        request (Request): The FastAPI request object.
        form_data (dict): A dictionary containing parameters for the chat completion request.
        url_idx (Optional[int], optional): An optional index to select a specific backend URL configuration. Defaults to None.
        user: A verified user object (resolved via dependency injection) that includes authentication details such as role and id.
    
    Returns:
        The response from the external API as returned by the asynchronous send_post_request call, which may be streamed.
    
    Raises:
        HTTPException: 
            - 400: If instantiation of OpenAIChatCompletionForm fails due to invalid input data.
            - 403: If the specified model is not found or the user lacks permission to access the model.
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
        if user.role == "user" and not BYPASS_MODEL_ACCESS_CONTROL:
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

    url, url_idx = await get_ollama_url(request, payload["model"], url_idx)
    api_config = request.app.state.config.OLLAMA_API_CONFIGS.get(
        str(url_idx),
        request.app.state.config.OLLAMA_API_CONFIGS.get(url, {}),  # Legacy support
    )

    prefix_id = api_config.get("prefix_id", None)
    if prefix_id:
        payload["model"] = payload["model"].replace(f"{prefix_id}.", "")

    return await send_post_request(
        url=f"{url}/v1/chat/completions",
        payload=json.dumps(payload),
        stream=payload.get("stream", False),
        key=get_api_key(url_idx, url, request.app.state.config.OLLAMA_API_CONFIGS),
    )


@router.get("/v1/models")
@router.get("/v1/models/{url_idx}")
async def get_openai_models(
    request: Request,
    url_idx: Optional[int] = None,
    user=Depends(get_verified_user),
):

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
