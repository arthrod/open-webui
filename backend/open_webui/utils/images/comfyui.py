import asyncio
import json
import logging
import random
import urllib.parse
import urllib.request
from typing import Optional

import websocket  # NOTE: websocket-client (https://github.com/websocket-client/websocket-client)
from open_webui.env import SRC_LOG_LEVELS
from pydantic import BaseModel

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["COMFYUI"])

default_headers = {"User-Agent": "Mozilla/5.0"}


def queue_prompt(prompt, client_id, base_url, api_key):
    """
    Queue a prompt for processing on a ComfyUI image generation server.
    
    Sends a JSON payload containing the prompt and client ID to the specified server endpoint, 
    with an authorization header for secure access.
    
    Parameters:
        prompt (dict): The workflow and configuration for image generation
        client_id (str): Unique identifier for the client session
        base_url (str): Base URL of the ComfyUI server
        api_key (str): Authentication token for accessing the server
    
    Returns:
        dict: Server response containing details about the queued prompt, typically including a prompt ID
    
    Raises:
        Exception: If there is an error during the request, such as network issues or authentication problems
    """
    log.info("queue_prompt")
    p = {"prompt": prompt, "client_id": client_id}
    data = json.dumps(p).encode("utf-8")
    log.debug(f"queue_prompt data: {data}")
    try:
        req = urllib.request.Request(
            f"{base_url}/prompt",
            data=data,
            headers={**default_headers, "Authorization": f"Bearer {api_key}"},
        )
        response = urllib.request.urlopen(req).read()
        return json.loads(response)
    except Exception as e:
        log.exception(f"Error while queuing prompt: {e}")
        raise e


def get_image(filename, subfolder, folder_type, base_url, api_key):
    """
    Retrieve an image from the server using specified parameters.
    
    Sends an HTTP GET request to fetch an image file from a specified URL with authentication.
    
    Parameters:
        filename (str): Name of the image file to retrieve
        subfolder (str): Subfolder path where the image is located
        folder_type (str): Type or category of the folder containing the image
        base_url (str): Base URL of the image server
        api_key (str): Authentication token for accessing the image server
    
    Returns:
        bytes: Raw image data retrieved from the server
    
    Raises:
        urllib.error.URLError: If there is a network-related error during image retrieval
        urllib.error.HTTPError: If the server returns an error response
    """
    log.info("get_image")
    data = {"filename": filename, "subfolder": subfolder, "type": folder_type}
    url_values = urllib.parse.urlencode(data)
    req = urllib.request.Request(
        f"{base_url}/view?{url_values}",
        headers={**default_headers, "Authorization": f"Bearer {api_key}"},
    )
    with urllib.request.urlopen(req) as response:
        return response.read()


def get_image_url(filename, subfolder, folder_type, base_url):
    log.info("get_image")
    data = {"filename": filename, "subfolder": subfolder, "type": folder_type}
    url_values = urllib.parse.urlencode(data)
    return f"{base_url}/view?{url_values}"


def get_history(prompt_id, base_url, api_key):
    """
    Retrieve the processing history for a specific prompt from the ComfyUI server.
    
    Parameters:
        prompt_id (str): Unique identifier of the prompt to retrieve history for
        base_url (str): Base URL of the ComfyUI server
        api_key (str): Authorization token for accessing the server
    
    Returns:
        dict: JSON-parsed history data for the specified prompt
    
    Raises:
        urllib.error.URLError: If there is a network-related error during the request
        json.JSONDecodeError: If the server response cannot be parsed as JSON
    """
    log.info("get_history")

    req = urllib.request.Request(
        f"{base_url}/history/{prompt_id}",
        headers={**default_headers, "Authorization": f"Bearer {api_key}"},
    )
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read())


def get_images(ws, prompt, client_id, base_url, api_key):
    """
    Retrieve generated images from a WebSocket connection after queuing a prompt.
    
    This function manages the process of generating images by:
    1. Queuing a prompt and obtaining a prompt ID
    2. Waiting for the execution to complete via WebSocket
    3. Retrieving the image history
    4. Extracting image URLs from the generated outputs
    
    Parameters:
        ws (WebSocket): Active WebSocket connection for receiving execution updates
        prompt (dict): Workflow prompt to be processed
        client_id (str): Unique client identifier for the request
        base_url (str): Base URL of the image generation service
        api_key (str): Authorization key for accessing the service
    
    Returns:
        dict: A dictionary containing a list of generated image URLs under the 'data' key
    
    Raises:
        json.JSONDecodeError: If WebSocket message cannot be parsed
        WebSocketException: If WebSocket communication fails
    """
    prompt_id = queue_prompt(prompt, client_id, base_url, api_key)["prompt_id"]
    output_images = []
    while True:
        out = ws.recv()
        if isinstance(out, str):
            message = json.loads(out)
            if message["type"] == "executing":
                data = message["data"]
                if data["node"] is None and data["prompt_id"] == prompt_id:
                    break  # Execution is done
        else:
            continue  # previews are binary data

    history = get_history(prompt_id, base_url, api_key)[prompt_id]
    for o in history["outputs"]:
        for node_id in history["outputs"]:
            node_output = history["outputs"][node_id]
            if "images" in node_output:
                for image in node_output["images"]:
                    url = get_image_url(
                        image["filename"], image["subfolder"], image["type"], base_url
                    )
                    output_images.append({"url": url})
    return {"data": output_images}


class ComfyUINodeInput(BaseModel):
    type: Optional[str] = None
    node_ids: list[str] = []
    key: Optional[str] = "text"
    value: Optional[str] = None


class ComfyUIWorkflow(BaseModel):
    workflow: str
    nodes: list[ComfyUINodeInput]


class ComfyUIGenerateImageForm(BaseModel):
    workflow: ComfyUIWorkflow

    prompt: str
    negative_prompt: Optional[str] = None
    width: int
    height: int
    n: int = 1

    steps: Optional[int] = None
    seed: Optional[int] = None


async def comfyui_generate_image(
    model: str, payload: ComfyUIGenerateImageForm, client_id, base_url, api_key
):
    """
    Asynchronously generate images using ComfyUI workflow with dynamic configuration.
    
    This function dynamically updates a ComfyUI workflow based on input parameters, establishes a WebSocket connection, and retrieves generated images.
    
    Parameters:
        model (str): The machine learning model to use for image generation.
        payload (ComfyUIGenerateImageForm): Structured form containing workflow and generation parameters.
        client_id (str): Unique client identifier for the WebSocket connection.
        base_url (str): Base URL of the ComfyUI server.
        api_key (str): Authentication key for accessing the ComfyUI service.
    
    Returns:
        list or None: A list of generated image data, or None if image generation fails.
    
    Raises:
        WebSocketException: If WebSocket connection cannot be established.
        RuntimeError: If workflow processing or image retrieval encounters an error.
    
    Notes:
        - Supports dynamic workflow modification for various generation parameters
        - Automatically generates random seed if not provided
        - Handles different node types like model, prompt, dimensions, steps
        - Logs detailed information about workflow and generation process
    """
    ws_url = base_url.replace("http://", "ws://").replace("https://", "wss://")
    workflow = json.loads(payload.workflow.workflow)

    for node in payload.workflow.nodes:
        if node.type:
            if node.type == "model":
                for node_id in node.node_ids:
                    workflow[node_id]["inputs"][node.key] = model
            elif node.type == "prompt":
                for node_id in node.node_ids:
                    workflow[node_id]["inputs"][
                        node.key if node.key else "text"
                    ] = payload.prompt
            elif node.type == "negative_prompt":
                for node_id in node.node_ids:
                    workflow[node_id]["inputs"][
                        node.key if node.key else "text"
                    ] = payload.negative_prompt
            elif node.type == "width":
                for node_id in node.node_ids:
                    workflow[node_id]["inputs"][
                        node.key if node.key else "width"
                    ] = payload.width
            elif node.type == "height":
                for node_id in node.node_ids:
                    workflow[node_id]["inputs"][
                        node.key if node.key else "height"
                    ] = payload.height
            elif node.type == "n":
                for node_id in node.node_ids:
                    workflow[node_id]["inputs"][
                        node.key if node.key else "batch_size"
                    ] = payload.n
            elif node.type == "steps":
                for node_id in node.node_ids:
                    workflow[node_id]["inputs"][
                        node.key if node.key else "steps"
                    ] = payload.steps
            elif node.type == "seed":
                seed = (
                    payload.seed
                    if payload.seed
                    else random.randint(0, 18446744073709551614)
                )
                for node_id in node.node_ids:
                    workflow[node_id]["inputs"][node.key] = seed
        else:
            for node_id in node.node_ids:
                workflow[node_id]["inputs"][node.key] = node.value

    try:
        ws = websocket.WebSocket()
        headers = {"Authorization": f"Bearer {api_key}"}
        ws.connect(f"{ws_url}/ws?clientId={client_id}", header=headers)
        log.info("WebSocket connection established.")
    except Exception as e:
        log.exception(f"Failed to connect to WebSocket server: {e}")
        return None

    try:
        log.info("Sending workflow to WebSocket server.")
        log.info(f"Workflow: {workflow}")
        images = await asyncio.to_thread(
            get_images, ws, workflow, client_id, base_url, api_key
        )
    except Exception as e:
        log.exception(f"Error while receiving images: {e}")
        images = None

    ws.close()

    return images
