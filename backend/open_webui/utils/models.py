import time
import logging
import sys

from fastapi import Request

from beyond_the_loop.models.users import User
from open_webui.routers import ollama
from beyond_the_loop.routers import openai
from open_webui.functions import get_function_models


from open_webui.models.functions import Functions
from beyond_the_loop.models.models import Models, ModelForm, ModelMeta, ModelParams


from open_webui.utils.plugin import load_function_module_by_id
from open_webui.utils.access_control import has_access


from open_webui.config import (
    DEFAULT_ARENA_MODEL,
)

from open_webui.env import SRC_LOG_LEVELS, GLOBAL_LOG_LEVEL


logging.basicConfig(stream=sys.stdout, level=GLOBAL_LOG_LEVEL)
log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MAIN"])


async def get_all_base_models(request: Request, user: User):
    """
    Retrieves and registers available base models asynchronously.
    
    This function aggregates models from multiple sources based on configuration settings. When the OpenAI API is enabled,
    it fetches OpenAI models and registers any that are not already present in the database. Similarly, if the Ollama API is
    enabled, it retrieves and reformats models from Ollama. Additionally, function models are obtained via a dedicated helper.
    The resulting list combines function models, OpenAI models, and Ollama models.
    
    Parameters:
        request: The HTTP request object providing access to application state and configuration.
        user: The current user, whose company information is used for registering OpenAI models.
    
    Returns:
        A list of base models aggregated from function models, OpenAI, and Ollama.
    """
    function_models = []
    openai_models = []
    ollama_models = []

    if request.app.state.config.ENABLE_OPENAI_API:
        openai_models = await openai.get_all_models(request)
        openai_models = openai_models["data"]
        
        # Register OpenAI models in the database if they don't exist
        for model in openai_models:
            existing_model = Models.get_model_by_id(model["id"])
            if not existing_model:
                Models.insert_new_model(
                    ModelForm(
                        id=model["id"],
                        name=model["id"],  # Use ID as name since OpenAI models don't have separate names
                        meta=ModelMeta(
                            description="OpenAI model",
                            profile_image_url="/static/favicon.png",
                        ),
                        params=ModelParams(),
                        access_control=None,  # None means public access
                    ),
                    company_id=user.company_id,
                )

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


async def get_all_models(request: Request, user: User):
    """
    Retrieves and aggregates available models with custom and arena configurations.
    
    This asynchronous function compiles a complete list of models by first retrieving base models from
    external APIs. It then optionally adds evaluation arena models from a predefined configuration if enabled,
    integrates custom models from the database, and enhances each model with associated action metadata.
    The updated model list is stored in the application state before being returned.
    
    Returns:
        List[dict]: A list of dictionaries representing the compiled model information.
    
    Raises:
        Exception: If an action defined by a model is not found.
    """
    models = await get_all_base_models(request, user)

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
    Checks if a user is authorized to access a model.
    
    Verifies that the specified user has read permission for the given model. For arena 
    models, access is determined using the model’s embedded access control metadata. 
    For non-arena models, the function retrieves model details from storage and validates 
    access based on the stored access control settings. An exception is raised if the 
    model is not found or the user lacks the required access.
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
            has_access(
                user.id, type="read", access_control=model_info.access_control
            )
        ):
            raise Exception("Model not found")
