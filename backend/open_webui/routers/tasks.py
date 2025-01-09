from fastapi import APIRouter, Depends, HTTPException, Response, status, Request
from fastapi.responses import JSONResponse, RedirectResponse

from pydantic import BaseModel
from typing import Optional
import logging

from open_webui.utils.chat import generate_chat_completion
from open_webui.utils.task import (
    title_generation_template,
    query_generation_template,
    autocomplete_generation_template,
    tags_generation_template,
    emoji_generation_template,
    moa_response_generation_template,
)
from open_webui.utils.auth import get_admin_user, get_verified_user
from open_webui.constants import TASKS

from open_webui.routers.pipelines import process_pipeline_inlet_filter
from open_webui.utils.task import get_task_model_id

from open_webui.config import (
    DEFAULT_TITLE_GENERATION_PROMPT_TEMPLATE,
    DEFAULT_TAGS_GENERATION_PROMPT_TEMPLATE,
    DEFAULT_QUERY_GENERATION_PROMPT_TEMPLATE,
    DEFAULT_AUTOCOMPLETE_GENERATION_PROMPT_TEMPLATE,
    DEFAULT_EMOJI_GENERATION_PROMPT_TEMPLATE,
    DEFAULT_MOA_GENERATION_PROMPT_TEMPLATE,
)
from open_webui.env import SRC_LOG_LEVELS


log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MODELS"])

router = APIRouter()


##################################
#
# Task Endpoints
#
##################################


@router.get("/config")
async def get_task_config(request: Request, user=Depends(get_verified_user)):
    """
    Retrieve the current task configuration settings.
    
    This endpoint returns a dictionary of task-related configuration parameters, including model settings, generation templates, and feature toggles.
    
    Parameters:
        request (Request): The FastAPI request object containing application state
        user (dict, optional): Verified user information obtained through dependency injection
    
    Returns:
        dict: A dictionary containing various task configuration settings, including:
            - TASK_MODEL: Primary task model identifier
            - TASK_MODEL_EXTERNAL: External task model identifier
            - TITLE_GENERATION_PROMPT_TEMPLATE: Template for generating titles
            - ENABLE_AUTOCOMPLETE_GENERATION: Flag to enable/disable autocompletion
            - AUTOCOMPLETE_GENERATION_INPUT_MAX_LENGTH: Maximum input length for autocompletion
            - TAGS_GENERATION_PROMPT_TEMPLATE: Template for generating tags
            - ENABLE_TAGS_GENERATION: Flag to enable/disable tag generation
            - ENABLE_SEARCH_QUERY_GENERATION: Flag to enable/disable search query generation
            - ENABLE_RETRIEVAL_QUERY_GENERATION: Flag to enable/disable retrieval query generation
            - QUERY_GENERATION_PROMPT_TEMPLATE: Template for generating queries
            - TOOLS_FUNCTION_CALLING_PROMPT_TEMPLATE: Template for function calling
    
    Requires:
        - Verified user authentication
    """
    return {
        "TASK_MODEL": request.app.state.config.TASK_MODEL,
        "TASK_MODEL_EXTERNAL": request.app.state.config.TASK_MODEL_EXTERNAL,
        "TITLE_GENERATION_PROMPT_TEMPLATE": request.app.state.config.TITLE_GENERATION_PROMPT_TEMPLATE,
        "ENABLE_AUTOCOMPLETE_GENERATION": request.app.state.config.ENABLE_AUTOCOMPLETE_GENERATION,
        "AUTOCOMPLETE_GENERATION_INPUT_MAX_LENGTH": request.app.state.config.AUTOCOMPLETE_GENERATION_INPUT_MAX_LENGTH,
        "TAGS_GENERATION_PROMPT_TEMPLATE": request.app.state.config.TAGS_GENERATION_PROMPT_TEMPLATE,
        "ENABLE_TAGS_GENERATION": request.app.state.config.ENABLE_TAGS_GENERATION,
        "ENABLE_SEARCH_QUERY_GENERATION": request.app.state.config.ENABLE_SEARCH_QUERY_GENERATION,
        "ENABLE_RETRIEVAL_QUERY_GENERATION": request.app.state.config.ENABLE_RETRIEVAL_QUERY_GENERATION,
        "QUERY_GENERATION_PROMPT_TEMPLATE": request.app.state.config.QUERY_GENERATION_PROMPT_TEMPLATE,
        "TOOLS_FUNCTION_CALLING_PROMPT_TEMPLATE": request.app.state.config.TOOLS_FUNCTION_CALLING_PROMPT_TEMPLATE,
    }


class TaskConfigForm(BaseModel):
    TASK_MODEL: Optional[str]
    TASK_MODEL_EXTERNAL: Optional[str]
    TITLE_GENERATION_PROMPT_TEMPLATE: str
    ENABLE_AUTOCOMPLETE_GENERATION: bool
    AUTOCOMPLETE_GENERATION_INPUT_MAX_LENGTH: int
    TAGS_GENERATION_PROMPT_TEMPLATE: str
    ENABLE_TAGS_GENERATION: bool
    ENABLE_SEARCH_QUERY_GENERATION: bool
    ENABLE_RETRIEVAL_QUERY_GENERATION: bool
    QUERY_GENERATION_PROMPT_TEMPLATE: str
    TOOLS_FUNCTION_CALLING_PROMPT_TEMPLATE: str


@router.post("/config/update")
async def update_task_config(
    request: Request, form_data: TaskConfigForm, user=Depends(get_admin_user)
):
    """
    Update the task configuration for various generation settings.
    
    This endpoint allows an admin user to modify task-related configuration parameters, including model settings, generation templates, and feature toggles.
    
    Parameters:
        request (Request): The FastAPI request object containing application state.
        form_data (TaskConfigForm): A form containing configuration parameters to update.
        user (dict, optional): The admin user making the configuration update. Defaults to the result of get_admin_user dependency.
    
    Returns:
        dict: A dictionary containing the updated configuration settings, including:
            - TASK_MODEL: Primary task model
            - TASK_MODEL_EXTERNAL: External task model
            - TITLE_GENERATION_PROMPT_TEMPLATE: Template for title generation
            - ENABLE_AUTOCOMPLETE_GENERATION: Flag to enable autocompletion
            - AUTOCOMPLETE_GENERATION_INPUT_MAX_LENGTH: Maximum input length for autocompletion
            - TAGS_GENERATION_PROMPT_TEMPLATE: Template for tags generation
            - ENABLE_TAGS_GENERATION: Flag to enable tags generation
            - ENABLE_SEARCH_QUERY_GENERATION: Flag to enable search query generation
            - ENABLE_RETRIEVAL_QUERY_GENERATION: Flag to enable retrieval query generation
            - QUERY_GENERATION_PROMPT_TEMPLATE: Template for query generation
            - TOOLS_FUNCTION_CALLING_PROMPT_TEMPLATE: Template for tools function calling
    
    Notes:
        - Requires admin user authentication
        - Updates application-level configuration state
        - Modifies multiple generation and model-related settings
    """
    request.app.state.config.TASK_MODEL = form_data.TASK_MODEL
    request.app.state.config.TASK_MODEL_EXTERNAL = form_data.TASK_MODEL_EXTERNAL
    request.app.state.config.TITLE_GENERATION_PROMPT_TEMPLATE = (
        form_data.TITLE_GENERATION_PROMPT_TEMPLATE
    )

    request.app.state.config.ENABLE_AUTOCOMPLETE_GENERATION = (
        form_data.ENABLE_AUTOCOMPLETE_GENERATION
    )
    request.app.state.config.AUTOCOMPLETE_GENERATION_INPUT_MAX_LENGTH = (
        form_data.AUTOCOMPLETE_GENERATION_INPUT_MAX_LENGTH
    )

    request.app.state.config.TAGS_GENERATION_PROMPT_TEMPLATE = (
        form_data.TAGS_GENERATION_PROMPT_TEMPLATE
    )
    request.app.state.config.ENABLE_TAGS_GENERATION = form_data.ENABLE_TAGS_GENERATION
    request.app.state.config.ENABLE_SEARCH_QUERY_GENERATION = (
        form_data.ENABLE_SEARCH_QUERY_GENERATION
    )
    request.app.state.config.ENABLE_RETRIEVAL_QUERY_GENERATION = (
        form_data.ENABLE_RETRIEVAL_QUERY_GENERATION
    )

    request.app.state.config.QUERY_GENERATION_PROMPT_TEMPLATE = (
        form_data.QUERY_GENERATION_PROMPT_TEMPLATE
    )
    request.app.state.config.TOOLS_FUNCTION_CALLING_PROMPT_TEMPLATE = (
        form_data.TOOLS_FUNCTION_CALLING_PROMPT_TEMPLATE
    )

    return {
        "TASK_MODEL": request.app.state.config.TASK_MODEL,
        "TASK_MODEL_EXTERNAL": request.app.state.config.TASK_MODEL_EXTERNAL,
        "TITLE_GENERATION_PROMPT_TEMPLATE": request.app.state.config.TITLE_GENERATION_PROMPT_TEMPLATE,
        "ENABLE_AUTOCOMPLETE_GENERATION": request.app.state.config.ENABLE_AUTOCOMPLETE_GENERATION,
        "AUTOCOMPLETE_GENERATION_INPUT_MAX_LENGTH": request.app.state.config.AUTOCOMPLETE_GENERATION_INPUT_MAX_LENGTH,
        "TAGS_GENERATION_PROMPT_TEMPLATE": request.app.state.config.TAGS_GENERATION_PROMPT_TEMPLATE,
        "ENABLE_TAGS_GENERATION": request.app.state.config.ENABLE_TAGS_GENERATION,
        "ENABLE_SEARCH_QUERY_GENERATION": request.app.state.config.ENABLE_SEARCH_QUERY_GENERATION,
        "ENABLE_RETRIEVAL_QUERY_GENERATION": request.app.state.config.ENABLE_RETRIEVAL_QUERY_GENERATION,
        "QUERY_GENERATION_PROMPT_TEMPLATE": request.app.state.config.QUERY_GENERATION_PROMPT_TEMPLATE,
        "TOOLS_FUNCTION_CALLING_PROMPT_TEMPLATE": request.app.state.config.TOOLS_FUNCTION_CALLING_PROMPT_TEMPLATE,
    }


@router.post("/title/completions")
async def generate_title(
    request: Request, form_data: dict, user=Depends(get_verified_user)
):
    """
    Generate a title for a chat conversation using a specified language model.
    
    This asynchronous function handles title generation for chat conversations by:
    - Validating the selected model
    - Selecting an appropriate task model
    - Generating a title using a configurable or default prompt template
    - Calling the chat completion generation endpoint
    
    Parameters:
        request (Request): The FastAPI request object containing application state
        form_data (dict): A dictionary containing generation parameters, including:
            - model (str): The ID of the language model to use
            - messages (list): Chat messages to use as context for title generation
        user (User, optional): The verified user making the request
    
    Returns:
        JSONResponse: Generated chat title or an error response
    
    Raises:
        HTTPException: If the specified model is not found
        JSONResponse: If an internal error occurs during title generation
    
    Notes:
        - Uses a configurable or default title generation prompt template
        - Supports different token limits for Ollama and other models
        - Logs debug information and potential errors
    """
    models = request.app.state.MODELS

    model_id = form_data["model"]
    if model_id not in models:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model not found",
        )

    # Check if the user has a custom task model
    # If the user has a custom task model, use that model
    task_model_id = get_task_model_id(
        model_id,
        request.app.state.config.TASK_MODEL,
        request.app.state.config.TASK_MODEL_EXTERNAL,
        models,
    )

    log.debug(
        f"generating chat title using model {task_model_id} for user {user.email} "
    )

    if request.app.state.config.TITLE_GENERATION_PROMPT_TEMPLATE != "":
        template = request.app.state.config.TITLE_GENERATION_PROMPT_TEMPLATE
    else:
        template = DEFAULT_TITLE_GENERATION_PROMPT_TEMPLATE

    content = title_generation_template(
        template,
        form_data["messages"],
        {
            "name": user.name,
            "location": user.info.get("location") if user.info else None,
        },
    )

    payload = {
        "model": task_model_id,
        "messages": [{"role": "user", "content": content}],
        "stream": False,
        **(
            {"max_tokens": 50}
            if models[task_model_id]["owned_by"] == "ollama"
            else {
                "max_completion_tokens": 50,
            }
        ),
        "metadata": {
            "task": str(TASKS.TITLE_GENERATION),
            "task_body": form_data,
            "chat_id": form_data.get("chat_id", None),
        },
    }

    try:
        return await generate_chat_completion(request, form_data=payload, user=user)
    except Exception as e:
        log.error("Exception occurred", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "An internal error has occurred."},
        )


@router.post("/tags/completions")
async def generate_chat_tags(
    request: Request, form_data: dict, user=Depends(get_verified_user)
):

    """
    Generate tags for a chat based on user messages using a specified language model.
    
    This asynchronous function handles tag generation with the following key features:
    - Checks if tag generation is enabled in the system configuration
    - Validates the selected language model
    - Supports custom task models
    - Uses a configurable or default prompt template for tag generation
    - Generates tags via a chat completion API call
    
    Parameters:
        request (Request): The FastAPI request object containing application state
        form_data (dict): A dictionary containing generation parameters
            - 'model': The ID of the language model to use
            - 'messages': The chat messages to generate tags from
        user (User, optional): The verified user making the request
    
    Returns:
        JSONResponse: Generated tags or an error response
            - 200 OK: Successfully generated tags
            - 404 Not Found: Invalid model selected
            - 500 Internal Server Error: Generation failure
    
    Raises:
        HTTPException: If the specified model is not found
    """
    if not request.app.state.config.ENABLE_TAGS_GENERATION:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"detail": "Tags generation is disabled"},
        )

    models = request.app.state.MODELS

    model_id = form_data["model"]
    if model_id not in models:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model not found",
        )

    # Check if the user has a custom task model
    # If the user has a custom task model, use that model
    task_model_id = get_task_model_id(
        model_id,
        request.app.state.config.TASK_MODEL,
        request.app.state.config.TASK_MODEL_EXTERNAL,
        models,
    )

    log.debug(
        f"generating chat tags using model {task_model_id} for user {user.email} "
    )

    if request.app.state.config.TAGS_GENERATION_PROMPT_TEMPLATE != "":
        template = request.app.state.config.TAGS_GENERATION_PROMPT_TEMPLATE
    else:
        template = DEFAULT_TAGS_GENERATION_PROMPT_TEMPLATE

    content = tags_generation_template(
        template, form_data["messages"], {"name": user.name}
    )

    payload = {
        "model": task_model_id,
        "messages": [{"role": "user", "content": content}],
        "stream": False,
        "metadata": {
            "task": str(TASKS.TAGS_GENERATION),
            "task_body": form_data,
            "chat_id": form_data.get("chat_id", None),
        },
    }

    try:
        return await generate_chat_completion(request, form_data=payload, user=user)
    except Exception as e:
        log.error(f"Error generating chat completion: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "An internal error has occurred."},
        )


@router.post("/queries/completions")
async def generate_queries(
    request: Request, form_data: dict, user=Depends(get_verified_user)
):

    """
    Generate queries based on the specified type and user messages.
    
    This asynchronous function handles query generation for web search or retrieval purposes. It validates the query generation settings, checks model availability, and generates queries using a specified or default template.
    
    Parameters:
        request (Request): The FastAPI request object containing application state.
        form_data (dict): A dictionary containing query generation parameters:
            - type (str): Type of query generation ('web_search' or 'retrieval')
            - model (str): ID of the model to use for query generation
            - messages (list): User messages to generate queries from
            - chat_id (str, optional): Identifier for the current chat session
        user (User): The verified user making the request.
    
    Returns:
        JSONResponse: Generated queries or an error response.
    
    Raises:
        HTTPException: 
            - 400 if query generation is disabled for the specified type
            - 404 if the specified model is not found
    
    Notes:
        - Supports custom query generation prompt templates
        - Uses a task-specific model for generation
        - Logs query generation details for debugging
    """
    type = form_data.get("type")
    if type == "web_search":
        if not request.app.state.config.ENABLE_SEARCH_QUERY_GENERATION:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Search query generation is disabled",
            )
    elif type == "retrieval":
        if not request.app.state.config.ENABLE_RETRIEVAL_QUERY_GENERATION:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Query generation is disabled",
            )

    models = request.app.state.MODELS

    model_id = form_data["model"]
    if model_id not in models:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model not found",
        )

    # Check if the user has a custom task model
    # If the user has a custom task model, use that model
    task_model_id = get_task_model_id(
        model_id,
        request.app.state.config.TASK_MODEL,
        request.app.state.config.TASK_MODEL_EXTERNAL,
        models,
    )

    log.debug(
        f"generating {type} queries using model {task_model_id} for user {user.email}"
    )

    if (request.app.state.config.QUERY_GENERATION_PROMPT_TEMPLATE).strip() != "":
        template = request.app.state.config.QUERY_GENERATION_PROMPT_TEMPLATE
    else:
        template = DEFAULT_QUERY_GENERATION_PROMPT_TEMPLATE

    content = query_generation_template(
        template, form_data["messages"], {"name": user.name}
    )

    payload = {
        "model": task_model_id,
        "messages": [{"role": "user", "content": content}],
        "stream": False,
        "metadata": {
            "task": str(TASKS.QUERY_GENERATION),
            "task_body": form_data,
            "chat_id": form_data.get("chat_id", None),
        },
    }

    try:
        return await generate_chat_completion(request, form_data=payload, user=user)
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": str(e)},
        )


@router.post("/auto/completions")
async def generate_autocompletion(
    request: Request, form_data: dict, user=Depends(get_verified_user)
):
    """
    Generate an autocompletion response based on the provided prompt and messages.
    
    This endpoint allows generating autocompletion text using a specified language model, with several validation checks:
    - Checks if autocompletion generation is enabled
    - Validates input prompt length against maximum allowed length
    - Verifies the selected model exists
    - Supports custom task models
    
    Parameters:
        request (Request): The FastAPI request object containing application state
        form_data (dict): A dictionary containing generation parameters:
            - type (str, optional): Type of autocompletion
            - prompt (str): The input prompt for autocompletion
            - messages (list, optional): Previous conversation messages
            - model (str): ID of the language model to use
    
    Returns:
        JSONResponse: Generated autocompletion text or an error response
    
    Raises:
        HTTPException: 
            - 400 if autocompletion generation is disabled
            - 400 if input prompt exceeds maximum length
            - 404 if specified model is not found
        
    Behavior:
        - Uses a configurable or default prompt template for generation
        - Supports streaming and non-streaming model responses
        - Logs generation details for debugging
        - Handles potential generation errors gracefully
    """
    if not request.app.state.config.ENABLE_AUTOCOMPLETE_GENERATION:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Autocompletion generation is disabled",
        )

    type = form_data.get("type")
    prompt = form_data.get("prompt")
    messages = form_data.get("messages")

    if request.app.state.config.AUTOCOMPLETE_GENERATION_INPUT_MAX_LENGTH > 0:
        if (
            len(prompt)
            > request.app.state.config.AUTOCOMPLETE_GENERATION_INPUT_MAX_LENGTH
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Input prompt exceeds maximum length of {request.app.state.config.AUTOCOMPLETE_GENERATION_INPUT_MAX_LENGTH}",
            )

    models = request.app.state.MODELS

    model_id = form_data["model"]
    if model_id not in models:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model not found",
        )

    # Check if the user has a custom task model
    # If the user has a custom task model, use that model
    task_model_id = get_task_model_id(
        model_id,
        request.app.state.config.TASK_MODEL,
        request.app.state.config.TASK_MODEL_EXTERNAL,
        models,
    )

    log.debug(
        f"generating autocompletion using model {task_model_id} for user {user.email}"
    )

    if (request.app.state.config.AUTOCOMPLETE_GENERATION_PROMPT_TEMPLATE).strip() != "":
        template = request.app.state.config.AUTOCOMPLETE_GENERATION_PROMPT_TEMPLATE
    else:
        template = DEFAULT_AUTOCOMPLETE_GENERATION_PROMPT_TEMPLATE

    content = autocomplete_generation_template(
        template, prompt, messages, type, {"name": user.name}
    )

    payload = {
        "model": task_model_id,
        "messages": [{"role": "user", "content": content}],
        "stream": False,
        "metadata": {
            "task": str(TASKS.AUTOCOMPLETE_GENERATION),
            "task_body": form_data,
            "chat_id": form_data.get("chat_id", None),
        },
    }

    try:
        return await generate_chat_completion(request, form_data=payload, user=user)
    except Exception as e:
        log.error(f"Error generating chat completion: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "An internal error has occurred."},
        )


@router.post("/emoji/completions")
async def generate_emoji(
    request: Request, form_data: dict, user=Depends(get_verified_user)
):

    """
    Generate an emoji based on the provided prompt using a specified language model.
    
    This asynchronous function handles emoji generation by selecting an appropriate task model, preparing a generation template, and invoking a chat completion generation process.
    
    Parameters:
        request (Request): The FastAPI request object containing application state.
        form_data (dict): A dictionary containing generation parameters including:
            - 'model': The ID of the language model to use
            - 'prompt': The input text to generate an emoji for
        user (User, optional): The verified user making the request. Defaults to the result of get_verified_user dependency.
    
    Returns:
        JSONResponse: The generated emoji or an error response.
    
    Raises:
        HTTPException: If the specified model is not found.
        JSONResponse: With a 400 status code if generation fails.
    
    Notes:
        - Uses a default emoji generation template
        - Supports different token limit configurations for Ollama and other models
        - Logs debug information about the emoji generation process
    """
    models = request.app.state.MODELS

    model_id = form_data["model"]
    if model_id not in models:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model not found",
        )

    # Check if the user has a custom task model
    # If the user has a custom task model, use that model
    task_model_id = get_task_model_id(
        model_id,
        request.app.state.config.TASK_MODEL,
        request.app.state.config.TASK_MODEL_EXTERNAL,
        models,
    )

    log.debug(f"generating emoji using model {task_model_id} for user {user.email} ")

    template = DEFAULT_EMOJI_GENERATION_PROMPT_TEMPLATE

    content = emoji_generation_template(
        template,
        form_data["prompt"],
        {
            "name": user.name,
            "location": user.info.get("location") if user.info else None,
        },
    )

    payload = {
        "model": task_model_id,
        "messages": [{"role": "user", "content": content}],
        "stream": False,
        **(
            {"max_tokens": 4}
            if models[task_model_id]["owned_by"] == "ollama"
            else {
                "max_completion_tokens": 4,
            }
        ),
        "chat_id": form_data.get("chat_id", None),
        "metadata": {"task": str(TASKS.EMOJI_GENERATION), "task_body": form_data},
    }

    try:
        return await generate_chat_completion(request, form_data=payload, user=user)
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": str(e)},
        )


@router.post("/moa/completions")
async def generate_moa_response(
    request: Request, form_data: dict, user=Depends(get_verified_user)
):

    """
    Generate a Model of Action (MOA) response using the specified language model.
    
    This asynchronous function handles the generation of a MOA response based on a given prompt and previous responses. It validates the selected model, prepares a generation template, and calls the chat completion generation process.
    
    Parameters:
        request (Request): The FastAPI request object containing application state.
        form_data (dict): A dictionary containing generation parameters:
            - model (str): The ID of the language model to use
            - prompt (str): The initial prompt for MOA response generation
            - responses (list): Previous responses to contextualize the generation
            - stream (bool, optional): Whether to stream the response
            - chat_id (str, optional): Identifier for the current chat session
    
    Returns:
        JSONResponse: Generated MOA response or an error message if generation fails
    
    Raises:
        HTTPException: If the specified model is not found (404 status code)
        HTTPException: If there's an error during response generation (400 status code)
    
    Notes:
        - Uses a default MOA generation prompt template
        - Supports custom task models based on configuration
        - Logs debug information about the generation process
    """
    models = request.app.state.MODELS
    model_id = form_data["model"]

    if model_id not in models:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model not found",
        )

    # Check if the user has a custom task model
    # If the user has a custom task model, use that model
    task_model_id = get_task_model_id(
        model_id,
        request.app.state.config.TASK_MODEL,
        request.app.state.config.TASK_MODEL_EXTERNAL,
        models,
    )

    log.debug(f"generating MOA model {task_model_id} for user {user.email} ")

    template = DEFAULT_MOA_GENERATION_PROMPT_TEMPLATE

    content = moa_response_generation_template(
        template,
        form_data["prompt"],
        form_data["responses"],
    )

    payload = {
        "model": task_model_id,
        "messages": [{"role": "user", "content": content}],
        "stream": form_data.get("stream", False),
        "metadata": {
            "chat_id": form_data.get("chat_id", None),
            "task": str(TASKS.MOA_RESPONSE_GENERATION),
            "task_body": form_data,
        },
    }

    try:
        return await generate_chat_completion(request, form_data=payload, user=user)
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": str(e)},
        )
