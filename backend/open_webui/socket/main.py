import asyncio
import socketio
import logging
import sys
import time

from open_webui.models.users import Users, UserNameResponse
from open_webui.models.channels import Channels
from open_webui.models.chats import Chats

from open_webui.env import (
    ENABLE_WEBSOCKET_SUPPORT,
    WEBSOCKET_MANAGER,
    WEBSOCKET_REDIS_URL,
)
from open_webui.utils.auth import decode_token
from open_webui.socket.utils import RedisDict, RedisLock

from open_webui.env import (
    GLOBAL_LOG_LEVEL,
    SRC_LOG_LEVELS,
)


logging.basicConfig(stream=sys.stdout, level=GLOBAL_LOG_LEVEL)
log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["SOCKET"])


if WEBSOCKET_MANAGER == "redis":
    mgr = socketio.AsyncRedisManager(WEBSOCKET_REDIS_URL)
    sio = socketio.AsyncServer(
        cors_allowed_origins=[],
        async_mode="asgi",
        transports=(["websocket"] if ENABLE_WEBSOCKET_SUPPORT else ["polling"]),
        allow_upgrades=ENABLE_WEBSOCKET_SUPPORT,
        always_connect=True,
        client_manager=mgr,
    )
else:
    sio = socketio.AsyncServer(
        cors_allowed_origins=[],
        async_mode="asgi",
        transports=(["websocket"] if ENABLE_WEBSOCKET_SUPPORT else ["polling"]),
        allow_upgrades=ENABLE_WEBSOCKET_SUPPORT,
        always_connect=True,
    )


# Timeout duration in seconds
TIMEOUT_DURATION = 3

# Dictionary to maintain the user pool

if WEBSOCKET_MANAGER == "redis":
    log.debug("Using Redis to manage websockets.")
    SESSION_POOL = RedisDict("open-webui:session_pool", redis_url=WEBSOCKET_REDIS_URL)
    USER_POOL = RedisDict("open-webui:user_pool", redis_url=WEBSOCKET_REDIS_URL)
    USAGE_POOL = RedisDict("open-webui:usage_pool", redis_url=WEBSOCKET_REDIS_URL)

    clean_up_lock = RedisLock(
        redis_url=WEBSOCKET_REDIS_URL,
        lock_name="usage_cleanup_lock",
        timeout_secs=TIMEOUT_DURATION * 2,
    )
    aquire_func = clean_up_lock.aquire_lock
    renew_func = clean_up_lock.renew_lock
    release_func = clean_up_lock.release_lock
else:
    SESSION_POOL = {}
    USER_POOL = {}
    USAGE_POOL = {}
    aquire_func = release_func = renew_func = lambda: True


async def periodic_usage_pool_cleanup():
    """
    Periodically clean up the usage pool by removing expired session connections and emitting updated usage information.
    
    This asynchronous function manages the cleanup of inactive WebSocket connections in the usage pool. It runs in an infinite loop, periodically checking and removing sessions that have exceeded the timeout duration. 
    
    Key behaviors:
    - Acquires a lock to prevent concurrent cleanup operations
    - Removes session IDs that have been inactive beyond the specified timeout
    - Removes models with no active connections
    - Emits updated usage information after cleanup
    - Continues running until an error occurs with lock renewal
    
    Raises:
        Exception: If unable to renew the cleanup lock during the process
    
    Notes:
        - Uses global variables USAGE_POOL, TIMEOUT_DURATION
        - Requires external lock acquisition functions (aquire_func, renew_func, release_func)
        - Emits WebSocket event 'usage' with current models in use
    """
    if not aquire_func():
        log.debug("Usage pool cleanup lock already exists. Not running it.")
        return
    log.debug("Running periodic_usage_pool_cleanup")
    try:
        while True:
            if not renew_func():
                log.error(f"Unable to renew cleanup lock. Exiting usage pool cleanup.")
                raise Exception("Unable to renew usage pool cleanup lock.")

            now = int(time.time())
            send_usage = False
            for model_id, connections in list(USAGE_POOL.items()):
                # Creating a list of sids to remove if they have timed out
                expired_sids = [
                    sid
                    for sid, details in connections.items()
                    if now - details["updated_at"] > TIMEOUT_DURATION
                ]

                for sid in expired_sids:
                    del connections[sid]

                if not connections:
                    log.debug(f"Cleaning up model {model_id} from usage pool")
                    del USAGE_POOL[model_id]
                else:
                    USAGE_POOL[model_id] = connections

                send_usage = True

            if send_usage:
                # Emit updated usage information after cleaning
                await sio.emit("usage", {"models": get_models_in_use()})

            await asyncio.sleep(TIMEOUT_DURATION)
    finally:
        release_func()


app = socketio.ASGIApp(
    sio,
    socketio_path="/ws/socket.io",
)


def get_models_in_use():
    # List models that are currently in use
    """
    Retrieves a list of models currently in use.
    
    Returns:
        list: A list of model names that are currently active in the usage pool.
    
    Note:
        This function provides a snapshot of models being utilized at the time of calling,
        based on the global USAGE_POOL dictionary.
    """
    models_in_use = list(USAGE_POOL.keys())
    return models_in_use


@sio.on("usage")
async def usage(sid, data):
    """
    Track and broadcast the usage of a specific model by a client.
    
    This function records the current usage of a model by a specific client session and updates
    the global usage pool. It then broadcasts the current models in use to all connected clients.
    
    Parameters:
        sid (str): The session ID of the client reporting usage.
        data (dict): A dictionary containing the model identifier.
            - model (str): The unique identifier of the model being used.
    
    Side Effects:
        - Updates the global USAGE_POOL with the current session's usage timestamp.
        - Emits a "usage" event to all connected clients with the current models in use.
    
    Example:
        await usage('session123', {'model': 'gpt-4'})
    """
    model_id = data["model"]
    # Record the timestamp for the last update
    current_time = int(time.time())

    # Store the new usage data and task
    USAGE_POOL[model_id] = {
        **(USAGE_POOL[model_id] if model_id in USAGE_POOL else {}),
        sid: {"updated_at": current_time},
    }

    # Broadcast the usage data to all clients
    await sio.emit("usage", {"models": get_models_in_use()})


@sio.event
async def connect(sid, environ, auth):
    """
    Handles WebSocket connection events for authenticated users.
    
    Authenticates a user via token, manages session and user pools, and broadcasts connection updates.
    
    Parameters:
        sid (str): The unique session ID for the WebSocket connection
        environ (dict): Environment details of the connection
        auth (dict): Authentication credentials containing a token
    
    Side Effects:
        - Populates SESSION_POOL with user information
        - Updates USER_POOL with session IDs for the connected user
        - Emits events to broadcast updated user list and model usage
    
    Returns:
        None: Manages connection state without returning a value
    """
    user = None
    if auth and "token" in auth:
        data = decode_token(auth["token"])

        if data is not None and "id" in data:
            user = Users.get_user_by_id(data["id"])

        if user:
            SESSION_POOL[sid] = user.model_dump()
            if user.id in USER_POOL:
                USER_POOL[user.id] = USER_POOL[user.id] + [sid]
            else:
                USER_POOL[user.id] = [sid]

            # print(f"user {user.name}({user.id}) connected with session ID {sid}")
            await sio.emit("user-list", {"user_ids": list(USER_POOL.keys())})
            await sio.emit("usage", {"models": get_models_in_use()})


@sio.on("user-join")
async def user_join(sid, data):

    """
    Handle user join event for WebSocket connection.
    
    Authenticates and processes a user joining the WebSocket server by validating their authentication token, retrieving user details, and managing session and user pools.
    
    Parameters:
        sid (str): The Socket.IO session ID for the connecting client
        data (dict): Connection data containing authentication information
    
    Returns:
        dict or None: A dictionary with user ID and name if successfully joined, None otherwise
    
    Behavior:
        - Validates the authentication token
        - Retrieves user details from the database
        - Adds user to session and user pools
        - Automatically joins user's existing channels
        - Broadcasts updated user list to connected clients
    
    Raises:
        No explicit exceptions, silently returns if authentication or user retrieval fails
    """
    auth = data["auth"] if "auth" in data else None
    if not auth or "token" not in auth:
        return

    data = decode_token(auth["token"])
    if data is None or "id" not in data:
        return

    user = Users.get_user_by_id(data["id"])
    if not user:
        return

    SESSION_POOL[sid] = user.model_dump()
    if user.id in USER_POOL:
        USER_POOL[user.id] = USER_POOL[user.id] + [sid]
    else:
        USER_POOL[user.id] = [sid]

    # Join all the channels
    channels = Channels.get_channels_by_user_id(user.id)
    log.debug(f"{channels=}")
    for channel in channels:
        await sio.enter_room(sid, f"channel:{channel.id}")

    # print(f"user {user.name}({user.id}) connected with session ID {sid}")

    await sio.emit("user-list", {"user_ids": list(USER_POOL.keys())})
    return {"id": user.id, "name": user.name}


@sio.on("join-channels")
async def join_channel(sid, data):
    """
    Handles user channel joining based on authentication token.
    
    Authenticates the user and joins all channels associated with their user ID.
    
    Parameters:
        sid (str): The socket connection session ID
        data (dict): A dictionary containing authentication information
    
    Behavior:
        - Validates the presence of an authentication token
        - Decodes the authentication token
        - Retrieves the user associated with the token
        - Fetches all channels for the authenticated user
        - Adds the socket connection to each channel's room
    
    Requires:
        - Valid authentication token
        - Existing user in the system
        - User must have associated channels
    
    Side Effects:
        - Socket connection enters rooms for each user's channels
        - Logs debug information about retrieved channels
    """
    auth = data["auth"] if "auth" in data else None
    if not auth or "token" not in auth:
        return

    data = decode_token(auth["token"])
    if data is None or "id" not in data:
        return

    user = Users.get_user_by_id(data["id"])
    if not user:
        return

    # Join all the channels
    channels = Channels.get_channels_by_user_id(user.id)
    log.debug(f"{channels=}")
    for channel in channels:
        await sio.enter_room(sid, f"channel:{channel.id}")


@sio.on("channel-events")
async def channel_events(sid, data):
    """
    Handle channel-specific events, primarily focusing on typing notifications.
    
    This asynchronous function manages events within a specific channel, with special handling for typing indicators. It ensures that only participants of the channel can trigger events and broadcasts typing notifications to all channel members.
    
    Parameters:
        sid (str): The session ID of the client triggering the event
        data (dict): Event data containing channel information and event details
    
    Behavior:
        - Verifies the sender is a participant in the specified channel
        - Supports 'typing' event type for sending typing indicators
        - Broadcasts typing events to all participants in the channel
        - Includes user information from the session pool in the event payload
    
    Raises:
        No explicit exceptions are raised within the function
    """
    room = f"channel:{data['channel_id']}"
    participants = sio.manager.get_participants(
        namespace="/",
        room=room,
    )

    sids = [sid for sid, _ in participants]
    if sid not in sids:
        return

    event_data = data["data"]
    event_type = event_data["type"]

    if event_type == "typing":
        await sio.emit(
            "channel-events",
            {
                "channel_id": data["channel_id"],
                "message_id": data.get("message_id", None),
                "data": event_data,
                "user": UserNameResponse(**SESSION_POOL[sid]).model_dump(),
            },
            room=room,
        )


@sio.on("user-list")
async def user_list(sid):
    """
    Emit the list of currently connected user IDs to the requesting client.
    
    This function broadcasts the current list of active user IDs stored in the USER_POOL 
    to the client that requested the user list via the "user-list" event.
    
    Parameters:
        sid (str): The session ID of the client requesting the user list.
    
    Side Effects:
        - Sends a WebSocket event "user-list" with the current list of user IDs.
    """
    await sio.emit("user-list", {"user_ids": list(USER_POOL.keys())})


@sio.event
async def disconnect(sid):
    """
    Handle user disconnection from the WebSocket server.
    
    This asynchronous function is triggered when a user disconnects. It performs the following tasks:
    - Removes the session from the SESSION_POOL
    - Updates the USER_POOL by removing the specific session ID
    - Deletes the user from USER_POOL if no active sessions remain
    - Broadcasts an updated list of active users to all connected clients
    
    Parameters:
        sid (str): The session ID of the disconnecting user
    
    Side Effects:
        - Modifies SESSION_POOL and USER_POOL global dictionaries
        - Emits a "user-list" event with current active user IDs
    """
    if sid in SESSION_POOL:
        user = SESSION_POOL[sid]
        del SESSION_POOL[sid]

        user_id = user["id"]
        USER_POOL[user_id] = [_sid for _sid in USER_POOL[user_id] if _sid != sid]

        if len(USER_POOL[user_id]) == 0:
            del USER_POOL[user_id]

        await sio.emit("user-list", {"user_ids": list(USER_POOL.keys())})
    else:
        pass
        # print(f"Unknown session ID {sid} disconnected")


def get_event_emitter(request_info):
    """
    Generates an event emitter function for WebSocket chat events with multi-session support.
    
    This function creates an asynchronous event emitter that broadcasts chat events to all sessions
    associated with a specific user, updates message statuses, and manages message content modifications.
    
    Parameters:
        request_info (dict): A dictionary containing request metadata including:
            - user_id (str): Unique identifier for the user
            - session_id (str): Current WebSocket session ID
            - chat_id (str): Identifier for the chat
            - message_id (str): Unique identifier for the message
    
    Returns:
        __event_emitter__ (callable): An asynchronous function that emits chat events and updates
        message content based on event type.
    
    Event Types Handled:
        - 'status': Updates message status in the chat
        - 'message': Appends content to an existing message
        - 'replace': Replaces the entire message content
    
    Side Effects:
        - Emits WebSocket events to all user sessions
        - Modifies chat message content in the database
        - Updates message status in the chat
    """
    async def __event_emitter__(event_data):
        user_id = request_info["user_id"]
        session_ids = list(
            set(USER_POOL.get(user_id, []) + [request_info["session_id"]])
        )

        for session_id in session_ids:
            await sio.emit(
                "chat-events",
                {
                    "chat_id": request_info["chat_id"],
                    "message_id": request_info["message_id"],
                    "data": event_data,
                },
                to=session_id,
            )

        if "type" in event_data and event_data["type"] == "status":
            Chats.add_message_status_to_chat_by_id_and_message_id(
                request_info["chat_id"],
                request_info["message_id"],
                event_data.get("data", {}),
            )

        if "type" in event_data and event_data["type"] == "message":
            message = Chats.get_message_by_id_and_message_id(
                request_info["chat_id"],
                request_info["message_id"],
            )

            content = message.get("content", "")
            content += event_data.get("data", {}).get("content", "")

            Chats.upsert_message_to_chat_by_id_and_message_id(
                request_info["chat_id"],
                request_info["message_id"],
                {
                    "content": content,
                },
            )

        if "type" in event_data and event_data["type"] == "replace":
            content = event_data.get("data", {}).get("content", "")

            Chats.upsert_message_to_chat_by_id_and_message_id(
                request_info["chat_id"],
                request_info["message_id"],
                {
                    "content": content,
                },
            )

    return __event_emitter__


def get_event_call(request_info):
    """
    Create an event call function for WebSocket communication with specific request details.
    
    This function generates an asynchronous event call handler that sends chat events to a specific WebSocket session and waits for a response.
    
    Parameters:
        request_info (dict): A dictionary containing request details with the following keys:
            - chat_id (str): Unique identifier for the chat
            - message_id (str): Unique identifier for the message
            - session_id (str): WebSocket session identifier
    
    Returns:
        callable: An asynchronous function that can be called with event data and returns a response from the specified WebSocket session
    """
    async def __event_call__(event_data):
        response = await sio.call(
            "chat-events",
            {
                "chat_id": request_info["chat_id"],
                "message_id": request_info["message_id"],
                "data": event_data,
            },
            to=request_info["session_id"],
        )
        return response

    return __event_call__


def get_user_id_from_session_pool(sid):
    """
    Retrieve the user ID associated with a given session ID from the session pool.
    
    Parameters:
        sid (str): The session ID to look up in the session pool.
    
    Returns:
        str or None: The user ID if the session exists in the pool, otherwise None.
    """
    user = SESSION_POOL.get(sid)
    if user:
        return user["id"]
    return None


def get_user_ids_from_room(room):
    """
    Retrieve the list of active user IDs in a specific room.
    
    This function extracts user IDs from the current active sessions in a given room. It uses the Socket.IO manager to get session participants and maps these sessions to their corresponding user IDs.
    
    Parameters:
        room (str): The name of the room to retrieve active user IDs from.
    
    Returns:
        list: A list of unique user IDs currently active in the specified room.
    
    Raises:
        KeyError: If a session ID does not have a corresponding entry in the SESSION_POOL.
    """
    active_session_ids = sio.manager.get_participants(
        namespace="/",
        room=room,
    )

    active_user_ids = list(
        set(
            [SESSION_POOL.get(session_id[0])["id"] for session_id in active_session_ids]
        )
    )
    return active_user_ids


def get_active_status_by_user_id(user_id):
    """
    Check if a user is currently active in the system.
    
    Parameters:
        user_id (str): The unique identifier of the user to check for active status.
    
    Returns:
        bool: True if the user is currently in the USER_POOL (active), False otherwise.
    """
    if user_id in USER_POOL:
        return True
    return False
