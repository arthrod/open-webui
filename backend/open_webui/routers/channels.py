import json
import logging
from typing import Optional


from fastapi import APIRouter, Depends, HTTPException, Request, status, BackgroundTasks
from pydantic import BaseModel


from open_webui.socket.main import sio, get_user_ids_from_room
from open_webui.models.users import Users, UserNameResponse

from open_webui.models.channels import Channels, ChannelModel, ChannelForm
from open_webui.models.messages import (
    Messages,
    MessageModel,
    MessageResponse,
    MessageForm,
)


from open_webui.config import ENABLE_ADMIN_CHAT_ACCESS, ENABLE_ADMIN_EXPORT
from open_webui.constants import ERROR_MESSAGES
from open_webui.env import SRC_LOG_LEVELS


from open_webui.utils.auth import get_admin_user, get_verified_user
from open_webui.utils.access_control import has_access, get_users_with_access
from open_webui.utils.webhook import post_webhook

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MODELS"])

router = APIRouter()

############################
# GetChatList
############################


@router.get("/", response_model=list[ChannelModel])
async def get_channels(user=Depends(get_verified_user)):
    """
    Retrieve a list of channels based on user role.
    
    For admin users, returns all available channels. For regular users, returns only channels
    associated with their user ID.
    
    Parameters:
        user (User): Authenticated user obtained through dependency injection. 
                     Must be a verified user.
    
    Returns:
        list: A list of channel objects, filtered based on user role and permissions.
    
    Raises:
        HTTPException: If user authentication fails or user lacks necessary permissions.
    """
    if user.role == "admin":
        return Channels.get_channels()
    else:
        return Channels.get_channels_by_user_id(user.id)


############################
# CreateNewChannel
############################


@router.post("/create", response_model=Optional[ChannelModel])
async def create_new_channel(form_data: ChannelForm, user=Depends(get_admin_user)):
    """
    Create a new channel with the provided channel form data.
    
    This endpoint is restricted to admin users and allows creating a new channel in the system.
    
    Parameters:
        form_data (ChannelForm): The form data containing details for the new channel
        user (User, optional): The admin user creating the channel, automatically injected via dependency
    
    Returns:
        ChannelModel: The newly created channel with its assigned details
    
    Raises:
        HTTPException: 400 Bad Request if channel creation fails due to any error
    """
    try:
        channel = Channels.insert_new_channel(None, form_data, user.id)
        return ChannelModel(**channel.model_dump())
    except Exception as e:
        log.exception(e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=ERROR_MESSAGES.DEFAULT()
        )


############################
# GetChannelById
############################


@router.get("/{id}", response_model=Optional[ChannelModel])
async def get_channel_by_id(id: str, user=Depends(get_verified_user)):
    """
    Retrieve a specific channel by its ID with access control.
    
    Fetches a channel using the provided ID and performs access validation. 
    Only admin users or users with explicit read permissions can access the channel.
    
    Parameters:
        id (str): Unique identifier of the channel to retrieve
        user (User): Authenticated user making the request, obtained via dependency injection
    
    Returns:
        ChannelModel: Detailed information about the requested channel
    
    Raises:
        HTTPException: 404 error if channel is not found
        HTTPException: 403 error if user lacks required access permissions
    """
    channel = Channels.get_channel_by_id(id)
    if not channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=ERROR_MESSAGES.NOT_FOUND
        )

    if user.role != "admin" and not has_access(
        user.id, type="read", access_control=channel.access_control
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=ERROR_MESSAGES.DEFAULT()
        )

    return ChannelModel(**channel.model_dump())


############################
# UpdateChannelById
############################


@router.post("/{id}/update", response_model=Optional[ChannelModel])
async def update_channel_by_id(
    id: str, form_data: ChannelForm, user=Depends(get_admin_user)
):
    """
    Update an existing channel by its ID.
    
    This endpoint allows admin users to modify the details of a specific channel. It performs the following steps:
    1. Retrieves the channel by its ID
    2. Raises a 404 error if the channel does not exist
    3. Attempts to update the channel with the provided form data
    4. Returns the updated channel model
    5. Handles and logs any exceptions during the update process
    
    Parameters:
        id (str): The unique identifier of the channel to be updated
        form_data (ChannelForm): The new channel details to be applied
        user (dict, optional): The admin user performing the update (automatically injected via dependency)
    
    Returns:
        ChannelModel: The updated channel with its new details
    
    Raises:
        HTTPException: 404 error if channel is not found
        HTTPException: 400 error if update fails due to any internal error
    """
    channel = Channels.get_channel_by_id(id)
    if not channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=ERROR_MESSAGES.NOT_FOUND
        )

    try:
        channel = Channels.update_channel_by_id(id, form_data)
        return ChannelModel(**channel.model_dump())
    except Exception as e:
        log.exception(e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=ERROR_MESSAGES.DEFAULT()
        )


############################
# DeleteChannelById
############################


@router.delete("/{id}/delete", response_model=bool)
async def delete_channel_by_id(id: str, user=Depends(get_admin_user)):
    """
    Delete a channel by its unique identifier.
    
    Deletes the specified channel from the system. Only accessible to admin users.
    
    Parameters:
        id (str): The unique identifier of the channel to be deleted
        user (dict, optional): The authenticated admin user performing the deletion. Defaults to the result of get_admin_user dependency.
    
    Returns:
        bool: True if the channel is successfully deleted
    
    Raises:
        HTTPException: 404 error if the channel is not found
        HTTPException: 400 error if an unexpected error occurs during deletion
    """
    channel = Channels.get_channel_by_id(id)
    if not channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=ERROR_MESSAGES.NOT_FOUND
        )

    try:
        Channels.delete_channel_by_id(id)
        return True
    except Exception as e:
        log.exception(e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=ERROR_MESSAGES.DEFAULT()
        )


############################
# GetChannelMessages
############################


class MessageUserResponse(MessageResponse):
    user: UserNameResponse


@router.get("/{id}/messages", response_model=list[MessageUserResponse])
async def get_channel_messages(
    id: str, skip: int = 0, limit: int = 50, user=Depends(get_verified_user)
):
    """
    Retrieve messages for a specific channel with pagination and user details.
    
    Fetches messages for a given channel, with optional pagination and comprehensive message metadata. Requires user authentication and access control verification.
    
    Parameters:
        id (str): Unique identifier of the channel to retrieve messages from
        skip (int, optional): Number of messages to skip for pagination. Defaults to 0.
        limit (int, optional): Maximum number of messages to return. Defaults to 50.
        user (User): Authenticated user making the request, automatically injected via dependency
    
    Returns:
        List[MessageUserResponse]: A list of messages with extended metadata including:
            - Full message details
            - User information
            - Reply count
            - Latest reply timestamp
            - Message reactions
    
    Raises:
        HTTPException: 404 if channel is not found
        HTTPException: 403 if user lacks read access to the channel
    """
    channel = Channels.get_channel_by_id(id)
    if not channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=ERROR_MESSAGES.NOT_FOUND
        )

    if user.role != "admin" and not has_access(
        user.id, type="read", access_control=channel.access_control
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=ERROR_MESSAGES.DEFAULT()
        )

    message_list = Messages.get_messages_by_channel_id(id, skip, limit)
    users = {}

    messages = []
    for message in message_list:
        if message.user_id not in users:
            user = Users.get_user_by_id(message.user_id)
            users[message.user_id] = user

        replies = Messages.get_replies_by_message_id(message.id)
        latest_reply_at = replies[0].created_at if replies else None

        messages.append(
            MessageUserResponse(
                **{
                    **message.model_dump(),
                    "reply_count": len(replies),
                    "latest_reply_at": latest_reply_at,
                    "reactions": Messages.get_reactions_by_message_id(message.id),
                    "user": UserNameResponse(**users[message.user_id].model_dump()),
                }
            )
        )

    return messages


############################
# PostNewMessage
############################


async def send_notification(webui_url, channel, message, active_user_ids):
    """
    Send notifications to users with channel access who are not currently active.
    
    This function identifies users with read access to a channel and sends webhook notifications
    to those who are not currently active in the channel. Notifications include channel details
    and message content.
    
    Parameters:
        webui_url (str): Base URL of the web application
        channel (Channel): Channel object containing channel metadata
        message (Message): Message object containing message content
        active_user_ids (list): List of currently active user IDs in the channel
    
    Notes:
        - Skips sending notifications to currently active users
        - Only sends notifications to users with configured webhook URLs
        - Webhook payload includes channel name, URL, and message content
    """
    users = get_users_with_access("read", channel.access_control)

    for user in users:
        if user.id in active_user_ids:
            continue
        else:
            if user.settings:
                webhook_url = user.settings.ui.get("notifications", {}).get(
                    "webhook_url", None
                )

                if webhook_url:
                    post_webhook(
                        webhook_url,
                        f"#{channel.name} - {webui_url}/channels/{channel.id}\n\n{message.content}",
                        {
                            "action": "channel",
                            "message": message.content,
                            "title": channel.name,
                            "url": f"{webui_url}/channels/{channel.id}",
                        },
                    )


@router.post("/{id}/messages/post", response_model=Optional[MessageModel])
async def post_new_message(
    request: Request,
    id: str,
    form_data: MessageForm,
    background_tasks: BackgroundTasks,
    user=Depends(get_verified_user),
):
    """
    Post a new message to a specific channel.
    
    Allows a verified user to send a message to a channel, with access control and real-time event notifications.
    
    Parameters:
        request (Request): The incoming HTTP request.
        id (str): The unique identifier of the channel.
        form_data (MessageForm): The message data to be posted.
        background_tasks (BackgroundTasks): Background task handler for async operations.
        user (User, optional): The authenticated user posting the message. Defaults to verified user.
    
    Returns:
        MessageModel: The newly created message with its details.
    
    Raises:
        HTTPException: 404 if channel not found, 403 if user lacks access, 400 for message posting errors.
    
    Side Effects:
        - Emits real-time socket events for channel and message updates
        - Sends background notifications to channel users
        - Logs any exceptions during message posting
    """
    channel = Channels.get_channel_by_id(id)
    if not channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=ERROR_MESSAGES.NOT_FOUND
        )

    if user.role != "admin" and not has_access(
        user.id, type="read", access_control=channel.access_control
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=ERROR_MESSAGES.DEFAULT()
        )

    try:
        message = Messages.insert_new_message(form_data, channel.id, user.id)

        if message:
            event_data = {
                "channel_id": channel.id,
                "message_id": message.id,
                "data": {
                    "type": "message",
                    "data": MessageUserResponse(
                        **{
                            **message.model_dump(),
                            "reply_count": 0,
                            "latest_reply_at": None,
                            "reactions": Messages.get_reactions_by_message_id(
                                message.id
                            ),
                            "user": UserNameResponse(**user.model_dump()),
                        }
                    ).model_dump(),
                },
                "user": UserNameResponse(**user.model_dump()).model_dump(),
                "channel": channel.model_dump(),
            }

            await sio.emit(
                "channel-events",
                event_data,
                to=f"channel:{channel.id}",
            )

            if message.parent_id:
                # If this message is a reply, emit to the parent message as well
                parent_message = Messages.get_message_by_id(message.parent_id)

                if parent_message:
                    await sio.emit(
                        "channel-events",
                        {
                            "channel_id": channel.id,
                            "message_id": parent_message.id,
                            "data": {
                                "type": "message:reply",
                                "data": MessageUserResponse(
                                    **{
                                        **parent_message.model_dump(),
                                        "user": UserNameResponse(
                                            **Users.get_user_by_id(
                                                parent_message.user_id
                                            ).model_dump()
                                        ),
                                    }
                                ).model_dump(),
                            },
                            "user": UserNameResponse(**user.model_dump()).model_dump(),
                            "channel": channel.model_dump(),
                        },
                        to=f"channel:{channel.id}",
                    )

            active_user_ids = get_user_ids_from_room(f"channel:{channel.id}")

            background_tasks.add_task(
                send_notification,
                request.app.state.config.WEBUI_URL,
                channel,
                message,
                active_user_ids,
            )

        return MessageModel(**message.model_dump())
    except Exception as e:
        log.exception(e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=ERROR_MESSAGES.DEFAULT()
        )


############################
# GetChannelMessage
############################


@router.get("/{id}/messages/{message_id}", response_model=Optional[MessageUserResponse])
async def get_channel_message(
    id: str, message_id: str, user=Depends(get_verified_user)
):
    """
    Retrieve a specific message from a channel by its message ID.
    
    This endpoint allows users to fetch a single message from a channel, with strict access control and validation. It ensures that:
    - The channel exists
    - The user has read access to the channel
    - The message belongs to the specified channel
    
    Parameters:
        id (str): The unique identifier of the channel
        message_id (str): The unique identifier of the message to retrieve
        user (User): The authenticated user making the request, obtained via dependency injection
    
    Returns:
        MessageUserResponse: A detailed message object including user information
    
    Raises:
        HTTPException: 404 if the channel or message is not found
        HTTPException: 403 if the user lacks permission to access the channel
        HTTPException: 400 if the message does not belong to the specified channel
    """
    channel = Channels.get_channel_by_id(id)
    if not channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=ERROR_MESSAGES.NOT_FOUND
        )

    if user.role != "admin" and not has_access(
        user.id, type="read", access_control=channel.access_control
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=ERROR_MESSAGES.DEFAULT()
        )

    message = Messages.get_message_by_id(message_id)
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=ERROR_MESSAGES.NOT_FOUND
        )

    if message.channel_id != id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=ERROR_MESSAGES.DEFAULT()
        )

    return MessageUserResponse(
        **{
            **message.model_dump(),
            "user": UserNameResponse(
                **Users.get_user_by_id(message.user_id).model_dump()
            ),
        }
    )


############################
# GetChannelThreadMessages
############################


@router.get(
    "/{id}/messages/{message_id}/thread", response_model=list[MessageUserResponse]
)
async def get_channel_thread_messages(
    id: str,
    message_id: str,
    skip: int = 0,
    limit: int = 50,
    user=Depends(get_verified_user),
):
    """
    Retrieve thread messages for a specific message in a channel.
    
    Fetches a list of messages that are part of a thread associated with a given message ID, with pagination support. Requires user authentication and channel access verification.
    
    Parameters:
        id (str): The unique identifier of the channel.
        message_id (str): The unique identifier of the parent message for the thread.
        skip (int, optional): Number of messages to skip for pagination. Defaults to 0.
        limit (int, optional): Maximum number of messages to return. Defaults to 50.
        user (User, optional): Authenticated user obtained through dependency injection.
    
    Returns:
        List[MessageUserResponse]: A list of thread messages with user details, reactions, and metadata.
    
    Raises:
        HTTPException: 404 error if the channel is not found.
        HTTPException: 403 error if the user lacks read access to the channel.
    """
    channel = Channels.get_channel_by_id(id)
    if not channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=ERROR_MESSAGES.NOT_FOUND
        )

    if user.role != "admin" and not has_access(
        user.id, type="read", access_control=channel.access_control
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=ERROR_MESSAGES.DEFAULT()
        )

    message_list = Messages.get_messages_by_parent_id(id, message_id, skip, limit)
    users = {}

    messages = []
    for message in message_list:
        if message.user_id not in users:
            user = Users.get_user_by_id(message.user_id)
            users[message.user_id] = user

        messages.append(
            MessageUserResponse(
                **{
                    **message.model_dump(),
                    "reply_count": 0,
                    "latest_reply_at": None,
                    "reactions": Messages.get_reactions_by_message_id(message.id),
                    "user": UserNameResponse(**users[message.user_id].model_dump()),
                }
            )
        )

    return messages


############################
# UpdateMessageById
############################


@router.post(
    "/{id}/messages/{message_id}/update", response_model=Optional[MessageModel]
)
async def update_message_by_id(
    id: str, message_id: str, form_data: MessageForm, user=Depends(get_verified_user)
):
    """
    Update a specific message within a channel.
    
    Allows users to modify an existing message, with access control and real-time event notifications.
    
    Parameters:
        id (str): The unique identifier of the channel containing the message
        message_id (str): The unique identifier of the message to be updated
        form_data (MessageForm): The updated message content and metadata
        user (User, optional): The authenticated user performing the update, obtained via dependency injection
    
    Returns:
        MessageModel: The updated message with its latest details
    
    Raises:
        HTTPException: 404 if the channel or message is not found
        HTTPException: 403 if the user lacks permission to update the message
        HTTPException: 400 for invalid update requests or processing errors
    
    Side Effects:
        - Emits a real-time socket event to notify channel members about the message update
        - Logs any exceptions during the update process
    """
    channel = Channels.get_channel_by_id(id)
    if not channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=ERROR_MESSAGES.NOT_FOUND
        )

    if user.role != "admin" and not has_access(
        user.id, type="read", access_control=channel.access_control
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=ERROR_MESSAGES.DEFAULT()
        )

    message = Messages.get_message_by_id(message_id)
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=ERROR_MESSAGES.NOT_FOUND
        )

    if message.channel_id != id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=ERROR_MESSAGES.DEFAULT()
        )

    try:
        message = Messages.update_message_by_id(message_id, form_data)
        message = Messages.get_message_by_id(message_id)

        if message:
            await sio.emit(
                "channel-events",
                {
                    "channel_id": channel.id,
                    "message_id": message.id,
                    "data": {
                        "type": "message:update",
                        "data": MessageUserResponse(
                            **{
                                **message.model_dump(),
                                "user": UserNameResponse(
                                    **user.model_dump()
                                ).model_dump(),
                            }
                        ).model_dump(),
                    },
                    "user": UserNameResponse(**user.model_dump()).model_dump(),
                    "channel": channel.model_dump(),
                },
                to=f"channel:{channel.id}",
            )

        return MessageModel(**message.model_dump())
    except Exception as e:
        log.exception(e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=ERROR_MESSAGES.DEFAULT()
        )


############################
# AddReactionToMessage
############################


class ReactionForm(BaseModel):
    name: str


@router.post("/{id}/messages/{message_id}/reactions/add", response_model=bool)
async def add_reaction_to_message(
    id: str, message_id: str, form_data: ReactionForm, user=Depends(get_verified_user)
):
    """
    Add a reaction to a specific message in a channel.
    
    Adds a user's reaction to a message after performing several validation checks:
    - Verifies the channel exists
    - Checks user has read access to the channel
    - Confirms the message exists and belongs to the specified channel
    
    Parameters:
        id (str): The ID of the channel containing the message
        message_id (str): The ID of the message to react to
        form_data (ReactionForm): The reaction details to be added
        user (User, optional): The authenticated user adding the reaction
    
    Returns:
        bool: True if the reaction was successfully added
    
    Raises:
        HTTPException: 404 if channel or message not found
        HTTPException: 403 if user lacks channel access
        HTTPException: 400 for invalid reaction attempts
    
    Side Effects:
        - Emits a WebSocket event to the channel with reaction details
        - Logs any exceptions during the process
    """
    channel = Channels.get_channel_by_id(id)
    if not channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=ERROR_MESSAGES.NOT_FOUND
        )

    if user.role != "admin" and not has_access(
        user.id, type="read", access_control=channel.access_control
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=ERROR_MESSAGES.DEFAULT()
        )

    message = Messages.get_message_by_id(message_id)
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=ERROR_MESSAGES.NOT_FOUND
        )

    if message.channel_id != id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=ERROR_MESSAGES.DEFAULT()
        )

    try:
        Messages.add_reaction_to_message(message_id, user.id, form_data.name)
        message = Messages.get_message_by_id(message_id)

        await sio.emit(
            "channel-events",
            {
                "channel_id": channel.id,
                "message_id": message.id,
                "data": {
                    "type": "message:reaction:add",
                    "data": {
                        **message.model_dump(),
                        "user": UserNameResponse(
                            **Users.get_user_by_id(message.user_id).model_dump()
                        ).model_dump(),
                        "name": form_data.name,
                    },
                },
                "user": UserNameResponse(**user.model_dump()).model_dump(),
                "channel": channel.model_dump(),
            },
            to=f"channel:{channel.id}",
        )

        return True
    except Exception as e:
        log.exception(e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=ERROR_MESSAGES.DEFAULT()
        )


############################
# RemoveReactionById
############################


@router.post("/{id}/messages/{message_id}/reactions/remove", response_model=bool)
async def remove_reaction_by_id_and_user_id_and_name(
    id: str, message_id: str, form_data: ReactionForm, user=Depends(get_verified_user)
):
    """
    Remove a reaction from a specific message in a channel.
    
    Removes a user's reaction from a message, with access control and event emission.
    
    Parameters:
        id (str): The channel ID
        message_id (str): The ID of the message from which to remove the reaction
        form_data (ReactionForm): Form data containing the reaction name to remove
        user (User, optional): The authenticated user removing the reaction
    
    Returns:
        bool: True if the reaction was successfully removed
    
    Raises:
        HTTPException: 404 if channel or message not found
        HTTPException: 403 if user lacks channel access
        HTTPException: 400 for invalid request or removal failure
    """
    channel = Channels.get_channel_by_id(id)
    if not channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=ERROR_MESSAGES.NOT_FOUND
        )

    if user.role != "admin" and not has_access(
        user.id, type="read", access_control=channel.access_control
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=ERROR_MESSAGES.DEFAULT()
        )

    message = Messages.get_message_by_id(message_id)
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=ERROR_MESSAGES.NOT_FOUND
        )

    if message.channel_id != id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=ERROR_MESSAGES.DEFAULT()
        )

    try:
        Messages.remove_reaction_by_id_and_user_id_and_name(
            message_id, user.id, form_data.name
        )

        message = Messages.get_message_by_id(message_id)

        await sio.emit(
            "channel-events",
            {
                "channel_id": channel.id,
                "message_id": message.id,
                "data": {
                    "type": "message:reaction:remove",
                    "data": {
                        **message.model_dump(),
                        "user": UserNameResponse(
                            **Users.get_user_by_id(message.user_id).model_dump()
                        ).model_dump(),
                        "name": form_data.name,
                    },
                },
                "user": UserNameResponse(**user.model_dump()).model_dump(),
                "channel": channel.model_dump(),
            },
            to=f"channel:{channel.id}",
        )

        return True
    except Exception as e:
        log.exception(e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=ERROR_MESSAGES.DEFAULT()
        )


############################
# DeleteMessageById
############################


@router.delete("/{id}/messages/{message_id}/delete", response_model=bool)
async def delete_message_by_id(
    id: str, message_id: str, user=Depends(get_verified_user)
):
    """
    Delete a specific message from a channel.
    
    Deletes a message by its ID within a specified channel, with access control and event notifications.
    
    Parameters:
        id (str): The ID of the channel containing the message.
        message_id (str): The unique identifier of the message to be deleted.
        user (User, optional): The authenticated user performing the deletion. Defaults to verified user.
    
    Returns:
        bool: True if the message is successfully deleted.
    
    Raises:
        HTTPException: 
            - 404 Not Found if the channel or message does not exist
            - 403 Forbidden if the user lacks access permissions
            - 400 Bad Request for invalid deletion attempts or processing errors
    
    Side Effects:
        - Emits a 'channel-events' socket event for message deletion
        - Emits an additional event for parent message thread updates if the deleted message is a reply
        - Logs any exceptions during the deletion process
    
    Notes:
        - Only admins or users with channel access can delete messages
        - Supports deleting both top-level messages and thread replies
    """
    channel = Channels.get_channel_by_id(id)
    if not channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=ERROR_MESSAGES.NOT_FOUND
        )

    if user.role != "admin" and not has_access(
        user.id, type="read", access_control=channel.access_control
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=ERROR_MESSAGES.DEFAULT()
        )

    message = Messages.get_message_by_id(message_id)
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=ERROR_MESSAGES.NOT_FOUND
        )

    if message.channel_id != id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=ERROR_MESSAGES.DEFAULT()
        )

    try:
        Messages.delete_message_by_id(message_id)
        await sio.emit(
            "channel-events",
            {
                "channel_id": channel.id,
                "message_id": message.id,
                "data": {
                    "type": "message:delete",
                    "data": {
                        **message.model_dump(),
                        "user": UserNameResponse(**user.model_dump()).model_dump(),
                    },
                },
                "user": UserNameResponse(**user.model_dump()).model_dump(),
                "channel": channel.model_dump(),
            },
            to=f"channel:{channel.id}",
        )

        if message.parent_id:
            # If this message is a reply, emit to the parent message as well
            parent_message = Messages.get_message_by_id(message.parent_id)

            if parent_message:
                await sio.emit(
                    "channel-events",
                    {
                        "channel_id": channel.id,
                        "message_id": parent_message.id,
                        "data": {
                            "type": "message:reply",
                            "data": MessageUserResponse(
                                **{
                                    **parent_message.model_dump(),
                                    "user": UserNameResponse(
                                        **Users.get_user_by_id(
                                            parent_message.user_id
                                        ).model_dump()
                                    ),
                                }
                            ).model_dump(),
                        },
                        "user": UserNameResponse(**user.model_dump()).model_dump(),
                        "channel": channel.model_dump(),
                    },
                    to=f"channel:{channel.id}",
                )

        return True
    except Exception as e:
        log.exception(e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=ERROR_MESSAGES.DEFAULT()
        )
