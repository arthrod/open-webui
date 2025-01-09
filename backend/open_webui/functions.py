import logging
import sys
import inspect
import json

from pydantic import BaseModel
from typing import AsyncGenerator, Generator, Iterator
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from starlette.responses import Response, StreamingResponse


from open_webui.socket.main import (
    get_event_call,
    get_event_emitter,
)


from open_webui.models.functions import Functions
from open_webui.models.models import Models

from open_webui.utils.plugin import load_function_module_by_id
from open_webui.utils.tools import get_tools
from open_webui.utils.access_control import has_access

from open_webui.env import SRC_LOG_LEVELS, GLOBAL_LOG_LEVEL

from open_webui.utils.misc import (
    add_or_update_system_message,
    get_last_user_message,
    prepend_to_first_user_message_content,
    openai_chat_chunk_message_template,
    openai_chat_completion_message_template,
)
from open_webui.utils.payload import (
    apply_model_params_to_body_openai,
    apply_model_system_prompt_to_body,
)


logging.basicConfig(stream=sys.stdout, level=GLOBAL_LOG_LEVEL)
log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MAIN"])


def get_function_module_by_id(request: Request, pipe_id: str):
    # Check if function is already loaded
    """
    Retrieve a function module by its unique identifier, loading it if not already present in the application state.
    
    This function manages the caching and initialization of function modules, ensuring that each module is loaded only once and its valves are properly configured.
    
    Parameters:
        request (Request): The FastAPI request object containing the application state
        pipe_id (str): The unique identifier of the function module to retrieve
    
    Returns:
        module: The loaded function module with optional valve configuration
    
    Raises:
        Exception: If the function module cannot be loaded or initialized
    """
    if pipe_id not in request.app.state.FUNCTIONS:
        function_module, _, _ = load_function_module_by_id(pipe_id)
        request.app.state.FUNCTIONS[pipe_id] = function_module
    else:
        function_module = request.app.state.FUNCTIONS[pipe_id]

    if hasattr(function_module, "valves") and hasattr(function_module, "Valves"):
        valves = Functions.get_function_valves_by_id(pipe_id)
        function_module.valves = function_module.Valves(**(valves if valves else {}))
    return function_module


async def get_function_models(request):
    """
    Retrieve a list of function models for active pipes.
    
    This asynchronous function collects and processes function models from active pipes, handling both single pipes and manifold (multi-function) pipes. It generates a standardized list of pipe models with metadata.
    
    Parameters:
        request (Request): The incoming HTTP request object used for context and module retrieval.
    
    Returns:
        list: A list of pipe models, each containing:
            - id (str): Unique identifier for the pipe
            - name (str): Name of the pipe
            - object (str): Always set to "model"
            - created (datetime): Creation timestamp of the pipe
            - owned_by (str): Owner of the pipe (set to "openai")
            - pipe (dict): Pipe type information
    
    Raises:
        Exception: Logs and captures any errors during pipe processing, continuing with other pipes.
    
    Notes:
        - Handles both single pipes and manifold pipes with multiple sub-pipes
        - Supports pipes defined as static lists or callable functions
        - Logs debug information about pipe processing
    """
    pipes = Functions.get_functions_by_type("pipe", active_only=True)
    pipe_models = []

    for pipe in pipes:
        function_module = get_function_module_by_id(request, pipe.id)

        # Check if function is a manifold
        if hasattr(function_module, "pipes"):
            sub_pipes = []

            # Check if pipes is a function or a list

            try:
                if callable(function_module.pipes):
                    sub_pipes = function_module.pipes()
                else:
                    sub_pipes = function_module.pipes
            except Exception as e:
                log.exception(e)
                sub_pipes = []

            log.debug(
                f"get_function_models: function '{pipe.id}' is a manifold of {sub_pipes}"
            )

            for p in sub_pipes:
                sub_pipe_id = f'{pipe.id}.{p["id"]}'
                sub_pipe_name = p["name"]

                if hasattr(function_module, "name"):
                    sub_pipe_name = f"{function_module.name}{sub_pipe_name}"

                pipe_flag = {"type": pipe.type}

                pipe_models.append(
                    {
                        "id": sub_pipe_id,
                        "name": sub_pipe_name,
                        "object": "model",
                        "created": pipe.created_at,
                        "owned_by": "openai",
                        "pipe": pipe_flag,
                    }
                )
        else:
            pipe_flag = {"type": "pipe"}

            log.debug(
                f"get_function_models: function '{pipe.id}' is a single pipe {{ 'id': {pipe.id}, 'name': {pipe.name} }}"
            )

            pipe_models.append(
                {
                    "id": pipe.id,
                    "name": pipe.name,
                    "object": "model",
                    "created": pipe.created_at,
                    "owned_by": "openai",
                    "pipe": pipe_flag,
                }
            )

    return pipe_models


async def generate_function_chat_completion(
    request, form_data, user, models: dict = {}
):
    """
    Generate a chat completion for a function module with advanced streaming and processing capabilities.
    
    This asynchronous function handles the execution of function pipes, supporting various response types and streaming modes. It dynamically processes function parameters, manages user valves, and provides flexible response handling.
    
    Parameters:
        request (Request): The incoming HTTP request object.
        form_data (dict): Data containing model configuration, messages, and other parameters.
        user (User): The authenticated user making the request.
        models (dict, optional): Additional model configurations. Defaults to an empty dictionary.
    
    Returns:
        StreamingResponse or dict: A streaming response for stream mode or a complete chat completion message.
        Supports multiple response types including strings, generators, async generators, and streaming responses.
    
    Key Features:
        - Dynamic function parameter generation
        - User valve management
        - Support for streaming and non-streaming responses
        - Error handling and logging
        - Flexible message processing
        - Compatibility with various function module types
    
    Raises:
        Exception: Captures and logs any errors during function execution.
    """
    async def execute_pipe(pipe, params):
        if inspect.iscoroutinefunction(pipe):
            return await pipe(**params)
        else:
            return pipe(**params)

    async def get_message_content(res: str | Generator | AsyncGenerator) -> str:
        """
        Extracts and converts message content from various response types.
        
        Parameters:
            res (str | Generator | AsyncGenerator): The response to process, which can be a string, generator, or async generator.
        
        Returns:
            str: A concatenated string representation of the response content.
        
        Handles different input types:
            - For strings, returns the string directly
            - For generators, joins all elements as strings
            - For async generators, asynchronously joins all elements as strings
        """
        if isinstance(res, str):
            return res
        if isinstance(res, Generator):
            return "".join(map(str, res))
        if isinstance(res, AsyncGenerator):
            return "".join([str(stream) async for stream in res])

    def process_line(form_data: dict, line):
        """
        Process a line of output for streaming chat responses, converting various input types to a consistent JSON-formatted data stream.
        
        Parameters:
            form_data (dict): Form data containing model configuration
            line (Any): Input line to be processed, which can be a BaseModel, dict, bytes, or string
        
        Returns:
            str: Formatted data stream line with JSON-encoded content, ready for server-sent events (SSE)
        
        Notes:
            - Handles conversion of BaseModel and dict instances to JSON
            - Decodes bytes to UTF-8 strings
            - Applies OpenAI chat chunk message template for non-data lines
            - Ensures consistent "data: " prefix for streaming responses
        """
        if isinstance(line, BaseModel):
            line = line.model_dump_json()
            line = f"data: {line}"
        if isinstance(line, dict):
            line = f"data: {json.dumps(line)}"

        try:
            line = line.decode("utf-8")
        except Exception:
            pass

        if line.startswith("data:"):
            return f"{line}\n\n"
        else:
            line = openai_chat_chunk_message_template(form_data["model"], line)
            return f"data: {json.dumps(line)}\n\n"

    def get_pipe_id(form_data: dict) -> str:
        """
        Extract the pipe ID from the form data.
        
        This function parses the 'model' field from the input dictionary, handling cases where the model name might include additional details after a dot.
        
        Parameters:
            form_data (dict): A dictionary containing form submission data with a 'model' key.
        
        Returns:
            str: The primary pipe identifier, extracted by splitting on the first dot if present.
        
        Example:
            >>> get_pipe_id({"model": "my_pipe.additional_info"})
            'my_pipe'
            >>> get_pipe_id({"model": "simple_pipe"})
            'simple_pipe'
        """
        pipe_id = form_data["model"]
        if "." in pipe_id:
            pipe_id, _ = pipe_id.split(".", 1)
        return pipe_id

    def get_function_params(function_module, form_data, user, extra_params=None):
        """
        Prepare function parameters for executing a function module with user-specific and extra parameters.
        
        Parameters:
            function_module (object): The function module containing the pipe function to be executed.
            form_data (dict): Request form data to be included as the 'body' parameter.
            user (User): The current user object.
            extra_params (dict, optional): Additional parameters to be passed to the function. Defaults to None.
        
        Returns:
            dict: A dictionary of parameters to be used when calling the function module's pipe, including:
                - 'body': The original form data
                - Any extra parameters that match the function's signature
                - User-specific valves if applicable
        
        Notes:
            - Filters extra parameters to only include those matching the function's signature
            - If the function module has a UserValves class, attempts to populate user-specific valve configurations
            - Handles potential errors in valve configuration by falling back to default UserValves
        """
        if extra_params is None:
            extra_params = {}

        pipe_id = get_pipe_id(form_data)

        # Get the signature of the function
        sig = inspect.signature(function_module.pipe)
        params = {"body": form_data} | {
            k: v for k, v in extra_params.items() if k in sig.parameters
        }

        if "__user__" in params and hasattr(function_module, "UserValves"):
            user_valves = Functions.get_user_valves_by_id_and_user_id(pipe_id, user.id)
            try:
                params["__user__"]["valves"] = function_module.UserValves(**user_valves)
            except Exception as e:
                log.exception(e)
                params["__user__"]["valves"] = function_module.UserValves()

        return params

    model_id = form_data.get("model")
    model_info = Models.get_model_by_id(model_id)

    metadata = form_data.pop("metadata", {})

    files = metadata.get("files", [])
    tool_ids = metadata.get("tool_ids", [])
    # Check if tool_ids is None
    if tool_ids is None:
        tool_ids = []

    __event_emitter__ = None
    __event_call__ = None
    __task__ = None
    __task_body__ = None

    if metadata:
        if all(k in metadata for k in ("session_id", "chat_id", "message_id")):
            __event_emitter__ = get_event_emitter(metadata)
            __event_call__ = get_event_call(metadata)
        __task__ = metadata.get("task", None)
        __task_body__ = metadata.get("task_body", None)

    extra_params = {
        "__event_emitter__": __event_emitter__,
        "__event_call__": __event_call__,
        "__task__": __task__,
        "__task_body__": __task_body__,
        "__files__": files,
        "__user__": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role,
        },
        "__metadata__": metadata,
        "__request__": request,
    }
    extra_params["__tools__"] = get_tools(
        request,
        tool_ids,
        user,
        {
            **extra_params,
            "__model__": models.get(form_data["model"], None),
            "__messages__": form_data["messages"],
            "__files__": files,
        },
    )

    if model_info:
        if model_info.base_model_id:
            form_data["model"] = model_info.base_model_id

        params = model_info.params.model_dump()
        form_data = apply_model_params_to_body_openai(params, form_data)
        form_data = apply_model_system_prompt_to_body(params, form_data, user)

    pipe_id = get_pipe_id(form_data)
    function_module = get_function_module_by_id(request, pipe_id)

    pipe = function_module.pipe
    params = get_function_params(function_module, form_data, user, extra_params)

    if form_data.get("stream", False):

        async def stream_content():
            """
            Stream the output of a function pipe with robust handling of different response types.
            
            This asynchronous generator function executes a pipe function and yields its content in a streaming format compatible with OpenAI chat completion protocols. It supports multiple response types including:
            - StreamingResponse objects
            - Dictionaries
            - Strings
            - Iterators
            - Async generators
            
            Handles various edge cases and error scenarios, converting outputs to JSON-formatted server-sent events (SSE).
            
            Yields:
                Streaming data chunks formatted as JSON server-sent events, including:
                - Successful response data
                - Error messages
                - Completion markers
            
            Raises:
                Logs and yields any exceptions encountered during pipe execution
            """
            try:
                res = await execute_pipe(pipe, params)

                # Directly return if the response is a StreamingResponse
                if isinstance(res, StreamingResponse):
                    async for data in res.body_iterator:
                        yield data
                    return
                if isinstance(res, dict):
                    yield f"data: {json.dumps(res)}\n\n"
                    return

            except Exception as e:
                log.error(f"Error: {e}")
                yield f"data: {json.dumps({'error': {'detail':str(e)}})}\n\n"
                return

            if isinstance(res, str):
                message = openai_chat_chunk_message_template(form_data["model"], res)
                yield f"data: {json.dumps(message)}\n\n"

            if isinstance(res, Iterator):
                for line in res:
                    yield process_line(form_data, line)

            if isinstance(res, AsyncGenerator):
                async for line in res:
                    yield process_line(form_data, line)

            if isinstance(res, str) or isinstance(res, Generator):
                finish_message = openai_chat_chunk_message_template(
                    form_data["model"], ""
                )
                finish_message["choices"][0]["finish_reason"] = "stop"
                yield f"data: {json.dumps(finish_message)}\n\n"
                yield "data: [DONE]"

        return StreamingResponse(stream_content(), media_type="text/event-stream")
    else:
        try:
            res = await execute_pipe(pipe, params)

        except Exception as e:
            log.error(f"Error: {e}")
            return {"error": {"detail": str(e)}}

        if isinstance(res, StreamingResponse) or isinstance(res, dict):
            return res
        if isinstance(res, BaseModel):
            return res.model_dump()

        message = await get_message_content(res)
        return openai_chat_completion_message_template(form_data["model"], message)
