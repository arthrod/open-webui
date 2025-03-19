from typing import Optional

from open_webui.models.prompts import (
    PromptForm,
    PromptUserResponse,
    PromptModel,
    Prompts,
)
from open_webui.constants import ERROR_MESSAGES
from fastapi import APIRouter, Depends, HTTPException, status, Request
from open_webui.utils.auth import get_admin_user, get_verified_user
from open_webui.utils.access_control import has_access, has_permission

router = APIRouter()

############################
# GetPrompts
############################


@router.get("/", response_model=list[PromptModel])
async def get_prompts(user=Depends(get_verified_user)):
    if user.role == "admin":
        prompts = Prompts.get_prompts()
    else:
        prompts = Prompts.get_prompts_by_user_id(user.id, "read")

    return prompts


@router.get("/list", response_model=list[PromptUserResponse])
async def get_prompt_list(user=Depends(get_verified_user)):
    if user.role == "admin":
        prompts = Prompts.get_prompts()
    else:
        prompts = Prompts.get_prompts_by_user_id(user.id, "write")

    return prompts


############################
# CreateNewPrompt
############################


@router.post("/create", response_model=Optional[PromptModel])
async def create_new_prompt(
    request: Request, form_data: PromptForm, user=Depends(get_verified_user)
):
    if user.role != "admin" and not has_permission(
        user.id, "workspace.prompts", request.app.state.config.USER_PERMISSIONS
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.UNAUTHORIZED,
        )

    prompt = Prompts.get_prompt_by_command(form_data.command)
    if prompt is None:
        prompt = Prompts.insert_new_prompt(user.id, form_data)

        if prompt:
            return prompt
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DEFAULT(),
        )
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=ERROR_MESSAGES.COMMAND_TAKEN,
    )


############################
# GetPromptByCommand
############################


@router.get("/command/{command}", response_model=Optional[PromptModel])
async def get_prompt_by_command(command: str, user=Depends(get_verified_user)):
    prompt = Prompts.get_prompt_by_command(f"/{command}")

    if prompt:
        if (
            user.role == "admin"
            or prompt.user_id == user.id
            or has_access(user.id, "read", prompt.access_control)
        ):
            return prompt
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


############################
# UpdatePromptByCommand
############################


@router.post("/command/{command}/update", response_model=Optional[PromptModel])
async def update_prompt_by_command(
    command: str,
    form_data: PromptForm,
    user=Depends(get_verified_user),
):
    """
    Update an existing prompt identified by its command.
    
    This asynchronous function retrieves a prompt using the provided command (with a preceding "/"),
    checks whether the user is permitted to update it, and then applies the update using the supplied form data.
    A user is allowed to update the prompt if they are the original creator, belong to a group with write access to the prompt,
    or have an administrator role.
    
    Parameters:
        command (str): The command identifier of the prompt to update.
        form_data (PromptForm): The form data containing the new prompt values.
        user (User, optional): The authenticated user, injected by the dependency `get_verified_user`.
    
    Returns:
        The updated prompt object if the update is successful.
    
    Raises:
        HTTPException: 
            - If no prompt is found for the given command.
            - If the user does not have permission to update the prompt.
            - If the update operation fails.
    """
    prompt = Prompts.get_prompt_by_command(f"/{command}")
    if not prompt:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    # Is the user the original creator, in a group with write access, or an admin
    if (
        prompt.user_id != user.id
        and not has_access(user.id, "write", prompt.access_control)
        and user.role != "admin"
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    prompt = Prompts.update_prompt_by_command(f"/{command}", form_data)
    if prompt:
        return prompt
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )


############################
# DeletePromptByCommand
############################


@router.delete("/command/{command}/delete", response_model=bool)
async def delete_prompt_by_command(command: str, user=Depends(get_verified_user)):
    prompt = Prompts.get_prompt_by_command(f"/{command}")
    if not prompt:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if prompt.user_id != user.id and user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    result = Prompts.delete_prompt_by_command(f"/{command}")
    return result
