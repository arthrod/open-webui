import time
import logging
import sys

from aiocache import cached
from fastapi import Request

from open_webui.routers import openai, ollama
from open_webui.functions import get_function_models


from open_webui.models.functions import Functions
from open_webui.models.models import Models


from open_webui.utils.plugin import load_function_module_by_id
from open_webui.utils.access_control import has_access


from open_webui.config import (
    DEFAULT_ARENA_MODEL,
)

from open_webui.env import SRC_LOG_LEVELS, GLOBAL_LOG_LEVEL


logging.basicConfig(stream=sys.stdout, level=GLOBAL_LOG_LEVEL)
log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MAIN"])


async def get_all_base_models(request: Request):
    """
    Retrieve base models from OpenAI, Ollama, and custom function sources.
    
    This asynchronous function aggregates models from different providers based on application configuration. It supports retrieving models from OpenAI, Ollama, and custom function models.
    
    Parameters:
        request (Request): The FastAPI request object containing application state and configuration.
    
    Returns:
        list: A comprehensive list of models with standardized metadata, including:
            - Models from OpenAI (if enabled)
            - Models from Ollama (if enabled)
            - Custom function models
            Each model includes properties like id, name, object type, creation timestamp, and ownership.
    
    Notes:
        - Requires ENABLE_OPENAI_API and ENABLE_OLLAMA_API configuration flags to be set
        - Ollama models are enriched with additional metadata for consistency
        - Combines models from multiple sources into a single list
    """
    function_models = []
    openai_models = []
    ollama_models = []

    if request.app.state.config.ENABLE_OPENAI_API:
        openai_models = await openai.get_all_models(request)
        openai_models = openai_models["data"]

    if request.app.state.config.ENABLE_OLLAMA_API:
        ollama_models = await ollama.get_all_models(request)
        ollama_models = [
            {
                "id": model["model"],
                "name": model["name"],
                "object": "model",
                "created": int(time.time()),
                "owned_by": "ollama",
                "ollama": model,
            }
            for model in ollama_models["models"]
        ]

    function_models = await get_function_models(request)
    models = function_models + openai_models + ollama_models

    return models


async def get_all_models(request):
    """
    Retrieve and process all available models with their associated actions.
    
    This asynchronous function aggregates models from various sources including base models, arena models, and custom models. It performs the following key operations:
    - Retrieves base models using get_all_base_models()
    - Adds arena models if enabled in configuration
    - Processes custom models, updating or adding them to the model list
    - Resolves and attaches action items to each model based on global and enabled action IDs
    
    Parameters:
        request (Request): The FastAPI request object containing application state and configuration
    
    Returns:
        list: A list of model dictionaries, each containing model details and associated actions
    
    Raises:
        Exception: If an action cannot be found during model processing
    
    Side Effects:
        - Updates request.app.state.MODELS with a dictionary of models indexed by their IDs
        - Logs the number of models retrieved
    """
    models = await get_all_base_models(request)

    # If there are no models, return an empty list
    if len(models) == 0:
        return []

    # Add arena models
    if request.app.state.config.ENABLE_EVALUATION_ARENA_MODELS:
        arena_models = []
        if len(request.app.state.config.EVALUATION_ARENA_MODELS) > 0:
            arena_models = [
                {
                    "id": model["id"],
                    "name": model["name"],
                    "info": {
                        "meta": model["meta"],
                    },
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "arena",
                    "arena": True,
                }
                for model in request.app.state.config.EVALUATION_ARENA_MODELS
            ]
        else:
            # Add default arena model
            arena_models = [
                {
                    "id": DEFAULT_ARENA_MODEL["id"],
                    "name": DEFAULT_ARENA_MODEL["name"],
                    "info": {
                        "meta": DEFAULT_ARENA_MODEL["meta"],
                    },
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "arena",
                    "arena": True,
                }
            ]
        models = models + arena_models

    global_action_ids = [
        function.id for function in Functions.get_global_action_functions()
    ]
    enabled_action_ids = [
        function.id
        for function in Functions.get_functions_by_type("action", active_only=True)
    ]

    custom_models = Models.get_all_models()
    for custom_model in custom_models:
        if custom_model.base_model_id is None:
            for model in models:
                if (
                    custom_model.id == model["id"]
                    or custom_model.id == model["id"].split(":")[0]
                ):
                    if custom_model.is_active:
                        model["name"] = custom_model.name
                        model["info"] = custom_model.model_dump()

                        action_ids = []
                        if "info" in model and "meta" in model["info"]:
                            action_ids.extend(
                                model["info"]["meta"].get("actionIds", [])
                            )

                        model["action_ids"] = action_ids
                    else:
                        models.remove(model)

        elif custom_model.is_active and (
            custom_model.id not in [model["id"] for model in models]
        ):
            owned_by = "openai"
            pipe = None
            action_ids = []

            for model in models:
                if (
                    custom_model.base_model_id == model["id"]
                    or custom_model.base_model_id == model["id"].split(":")[0]
                ):
                    owned_by = model["owned_by"]
                    if "pipe" in model:
                        pipe = model["pipe"]
                    break

            if custom_model.meta:
                meta = custom_model.meta.model_dump()
                if "actionIds" in meta:
                    action_ids.extend(meta["actionIds"])

            models.append(
                {
                    "id": f"{custom_model.id}",
                    "name": custom_model.name,
                    "object": "model",
                    "created": custom_model.created_at,
                    "owned_by": owned_by,
                    "info": custom_model.model_dump(),
                    "preset": True,
                    **({"pipe": pipe} if pipe is not None else {}),
                    "action_ids": action_ids,
                }
            )

    # Process action_ids to get the actions
    def get_action_items_from_module(function, module):
        """
        Extracts action items from a given module, handling both modules with explicit actions and those without.
        
        Parameters:
            function (object): The function object containing metadata about the module.
            module (module): The Python module to extract action items from.
        
        Returns:
            list: A list of action item dictionaries, each containing:
                - 'id': Unique identifier for the action
                - 'name': Display name of the action
                - 'description': Description of the action
                - 'icon_url': Optional URL for the action's icon
        
        Notes:
            - If the module has an 'actions' attribute, it generates action items with compound IDs.
            - If no actions are defined, it creates a default action item using the function's metadata.
        """
        actions = []
        if hasattr(module, "actions"):
            actions = module.actions
            return [
                {
                    "id": f"{function.id}.{action['id']}",
                    "name": action.get("name", f"{function.name} ({action['id']})"),
                    "description": function.meta.description,
                    "icon_url": action.get(
                        "icon_url", function.meta.manifest.get("icon_url", None)
                    ),
                }
                for action in actions
            ]
        else:
            return [
                {
                    "id": function.id,
                    "name": function.name,
                    "description": function.meta.description,
                    "icon_url": function.meta.manifest.get("icon_url", None),
                }
            ]

    def get_function_module_by_id(function_id):
        """
        Retrieve a function module by its unique identifier, utilizing application state caching.
        
        This method checks if a function module is already loaded in the application's state cache. 
        If not found, it dynamically loads the module using the provided function ID and stores it 
        in the application state for future quick access.
        
        Parameters:
            function_id (str): A unique identifier for the function module to be retrieved.
        
        Returns:
            module: The loaded Python module corresponding to the given function ID.
        
        Side Effects:
            - Modifies request.app.state.FUNCTIONS dictionary by adding newly loaded function modules
            - Uses load_function_module_by_id() to dynamically import modules
        
        Notes:
            - Implements a simple caching mechanism to improve performance of repeated module loads
            - Assumes the existence of a load_function_module_by_id() function in the current context
        """
        if function_id in request.app.state.FUNCTIONS:
            function_module = request.app.state.FUNCTIONS[function_id]
        else:
            function_module, _, _ = load_function_module_by_id(function_id)
            request.app.state.FUNCTIONS[function_id] = function_module

    for model in models:
        action_ids = [
            action_id
            for action_id in list(set(model.pop("action_ids", []) + global_action_ids))
            if action_id in enabled_action_ids
        ]

        model["actions"] = []
        for action_id in action_ids:
            action_function = Functions.get_function_by_id(action_id)
            if action_function is None:
                raise Exception(f"Action not found: {action_id}")

            function_module = get_function_module_by_id(action_id)
            model["actions"].extend(
                get_action_items_from_module(action_function, function_module)
            )
    log.debug(f"get_all_models() returned {len(models)} models")

    request.app.state.MODELS = {model["id"]: model for model in models}
    return models


def check_model_access(user, model):
    """
    Check if a user has access to a specific model.
    
    This function verifies model access rights based on the model type and user permissions.
    
    Parameters:
        user (User): The user attempting to access the model
        model (dict): A dictionary containing model information
    
    Raises:
        Exception: If the model is not found or the user lacks access rights
    
    Notes:
        - For arena models, access is checked using the model's access control metadata
        - For non-arena models, access is determined by user ownership or explicit access rights
        - Raises a generic "Model not found" exception to prevent information disclosure
    """
    if model.get("arena"):
        if not has_access(
            user.id,
            type="read",
            access_control=model.get("info", {})
            .get("meta", {})
            .get("access_control", {}),
        ):
            raise Exception("Model not found")
    else:
        model_info = Models.get_model_by_id(model.get("id"))
        if not model_info:
            raise Exception("Model not found")
        elif not (
            user.id == model_info.user_id
            or has_access(
                user.id, type="read", access_control=model_info.access_control
            )
        ):
            raise Exception("Model not found")
