import json
import time
import uuid
from typing import Optional

from open_webui.internal.db import Base, get_db
from open_webui.models.tags import TagModel, Tag, Tags


from pydantic import BaseModel, ConfigDict
from sqlalchemy import BigInteger, Boolean, Column, String, Text, JSON
from sqlalchemy import or_, func, select, and_, text
from sqlalchemy.sql import exists

####################
# Message DB Schema
####################


class MessageReaction(Base):
    __tablename__ = "message_reaction"
    id = Column(Text, primary_key=True)
    user_id = Column(Text)
    message_id = Column(Text)
    name = Column(Text)
    created_at = Column(BigInteger)


class MessageReactionModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    message_id: str
    name: str
    created_at: int  # timestamp in epoch


class Message(Base):
    __tablename__ = "message"
    id = Column(Text, primary_key=True)

    user_id = Column(Text)
    channel_id = Column(Text, nullable=True)

    parent_id = Column(Text, nullable=True)

    content = Column(Text)
    data = Column(JSON, nullable=True)
    meta = Column(JSON, nullable=True)

    created_at = Column(BigInteger)  # time_ns
    updated_at = Column(BigInteger)  # time_ns


class MessageModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    channel_id: Optional[str] = None

    parent_id: Optional[str] = None

    content: str
    data: Optional[dict] = None
    meta: Optional[dict] = None

    created_at: int  # timestamp in epoch
    updated_at: int  # timestamp in epoch


####################
# Forms
####################


class MessageForm(BaseModel):
    content: str
    parent_id: Optional[str] = None
    data: Optional[dict] = None
    meta: Optional[dict] = None


class Reactions(BaseModel):
    name: str
    user_ids: list[str]
    count: int


class MessageResponse(MessageModel):
    latest_reply_at: Optional[int]
    reply_count: int
    reactions: list[Reactions]


class MessageTable:
    def insert_new_message(
        self, form_data: MessageForm, channel_id: str, user_id: str
    ) -> Optional[MessageModel]:
        """
        Insert a new message into the database.
        
        Creates a new message with a unique identifier, timestamps, and details from the provided message form. 
        Stores the message in the database and returns the created message model.
        
        Parameters:
            form_data (MessageForm): The form data containing message content, parent ID, additional data, and metadata
            channel_id (str): The ID of the channel where the message is being sent
            user_id (str): The ID of the user sending the message
        
        Returns:
            Optional[MessageModel]: The created message model, or None if message creation fails
        
        Raises:
            SQLAlchemyError: If there are database-related issues during message insertion
        """
        with get_db() as db:
            id = str(uuid.uuid4())

            ts = int(time.time_ns())
            message = MessageModel(
                **{
                    "id": id,
                    "user_id": user_id,
                    "channel_id": channel_id,
                    "parent_id": form_data.parent_id,
                    "content": form_data.content,
                    "data": form_data.data,
                    "meta": form_data.meta,
                    "created_at": ts,
                    "updated_at": ts,
                }
            )

            result = Message(**message.model_dump())
            db.add(result)
            db.commit()
            db.refresh(result)
            return MessageModel.model_validate(result) if result else None

    def get_message_by_id(self, id: str) -> Optional[MessageResponse]:
        """
        Retrieve a message by its unique identifier with associated reactions and replies.
        
        Fetches a message from the database and enriches it with additional metadata including reactions, replies, and reply statistics.
        
        Parameters:
            id (str): The unique identifier of the message to retrieve.
        
        Returns:
            MessageResponse: A comprehensive message object containing:
                - Original message details
                - Total number of replies
                - Timestamp of the latest reply (if any)
                - List of reactions to the message
            None if no message is found with the given ID.
        
        Example:
            message = Messages.get_message_by_id("msg_123")
            # Returns a MessageResponse with message details, or None
        """
        with get_db() as db:
            message = db.get(Message, id)
            if not message:
                return None

            reactions = self.get_reactions_by_message_id(id)
            replies = self.get_replies_by_message_id(id)

            return MessageResponse(
                **{
                    **MessageModel.model_validate(message).model_dump(),
                    "latest_reply_at": replies[0].created_at if replies else None,
                    "reply_count": len(replies),
                    "reactions": reactions,
                }
            )

    def get_replies_by_message_id(self, id: str) -> list[MessageModel]:
        """
        Retrieve all replies to a specific message, ordered by creation time in descending order.
        
        Parameters:
            id (str): The unique identifier of the parent message for which replies are to be fetched.
        
        Returns:
            list[MessageModel]: A list of message models representing the replies to the specified message, 
            sorted from most recent to oldest.
        
        Raises:
            SQLAlchemyError: Potential database query errors (implicitly handled by context manager).
        """
        with get_db() as db:
            all_messages = (
                db.query(Message)
                .filter_by(parent_id=id)
                .order_by(Message.created_at.desc())
                .all()
            )
            return [MessageModel.model_validate(message) for message in all_messages]

    def get_reply_user_ids_by_message_id(self, id: str) -> list[str]:
        """
        Retrieve the list of user IDs who replied to a specific message.
        
        Parameters:
            id (str): The unique identifier of the parent message.
        
        Returns:
            list[str]: A list of user IDs who have replied to the specified message.
        
        Example:
            # Get user IDs who replied to a message with ID 'abc123'
            reply_users = Messages.get_reply_user_ids_by_message_id('abc123')
        """
        with get_db() as db:
            return [
                message.user_id
                for message in db.query(Message).filter_by(parent_id=id).all()
            ]

    def get_messages_by_channel_id(
        self, channel_id: str, skip: int = 0, limit: int = 50
    ) -> list[MessageModel]:
        """
        Retrieve messages for a specific channel with pagination support.
        
        Fetches a list of top-level messages (without parent messages) from a given channel, sorted by creation time in descending order.
        
        Parameters:
            channel_id (str): Unique identifier of the channel to retrieve messages from
            skip (int, optional): Number of messages to skip for pagination. Defaults to 0.
            limit (int, optional): Maximum number of messages to return. Defaults to 50.
        
        Returns:
            list[MessageModel]: A list of messages from the specified channel, converted to Pydantic models
        
        Example:
            # Retrieve first 50 messages from a channel
            messages = Messages.get_messages_by_channel_id('channel123')
            
            # Retrieve next 50 messages (pagination)
            next_messages = Messages.get_messages_by_channel_id('channel123', skip=50)
        """
        with get_db() as db:
            all_messages = (
                db.query(Message)
                .filter_by(channel_id=channel_id, parent_id=None)
                .order_by(Message.created_at.desc())
                .offset(skip)
                .limit(limit)
                .all()
            )
            return [MessageModel.model_validate(message) for message in all_messages]

    def get_messages_by_parent_id(
        self, channel_id: str, parent_id: str, skip: int = 0, limit: int = 50
    ) -> list[MessageModel]:
        """
        Retrieve messages that are replies to a specific parent message within a channel.
        
        Fetches a list of child messages for a given parent message, with optional pagination. If the number of child messages is less than the specified limit, the parent message is also included in the results.
        
        Parameters:
            channel_id (str): The ID of the channel containing the messages
            parent_id (str): The ID of the parent message to retrieve replies for
            skip (int, optional): Number of messages to skip for pagination. Defaults to 0.
            limit (int, optional): Maximum number of messages to retrieve. Defaults to 50.
        
        Returns:
            list[MessageModel]: A list of message models representing replies to the parent message, 
            optionally including the parent message if the number of replies is less than the limit.
        
        Behavior:
            - Returns an empty list if the parent message does not exist
            - Orders messages by creation time in descending order
            - Applies pagination using skip and limit parameters
            - Includes parent message if total replies are fewer than the limit
        """
        with get_db() as db:
            message = db.get(Message, parent_id)

            if not message:
                return []

            all_messages = (
                db.query(Message)
                .filter_by(channel_id=channel_id, parent_id=parent_id)
                .order_by(Message.created_at.desc())
                .offset(skip)
                .limit(limit)
                .all()
            )

            # If length of all_messages is less than limit, then add the parent message
            if len(all_messages) < limit:
                all_messages.append(message)

            return [MessageModel.model_validate(message) for message in all_messages]

    def update_message_by_id(
        self, id: str, form_data: MessageForm
    ) -> Optional[MessageModel]:
        """
        Update an existing message by its unique identifier.
        
        Parameters:
            id (str): The unique identifier of the message to update
            form_data (MessageForm): A form containing the updated message details
        
        Returns:
            Optional[MessageModel]: The updated message model if found and successfully updated, otherwise None
        
        Raises:
            SQLAlchemy exceptions may be raised for database-related errors during the update process
        
        Notes:
            - Updates the message's content, data, and metadata
            - Sets the updated_at timestamp to the current nanosecond timestamp
            - Commits the changes to the database
            - Refreshes the message object to reflect the latest database state
        """
        with get_db() as db:
            message = db.get(Message, id)
            message.content = form_data.content
            message.data = form_data.data
            message.meta = form_data.meta
            message.updated_at = int(time.time_ns())
            db.commit()
            db.refresh(message)
            return MessageModel.model_validate(message) if message else None

    def add_reaction_to_message(
        self, id: str, user_id: str, name: str
    ) -> Optional[MessageReactionModel]:
        """
        Add a reaction to a specific message.
        
        Adds a new message reaction for a given user and message with a specified reaction name.
        
        Parameters:
            id (str): The unique identifier of the message to which the reaction is being added.
            user_id (str): The unique identifier of the user adding the reaction.
            name (str): The name/type of the reaction (e.g., 'like', 'heart', etc.).
        
        Returns:
            Optional[MessageReactionModel]: The created message reaction model if successful, None otherwise.
        
        Raises:
            SQLAlchemyError: If there are database-related issues during reaction creation.
        
        Example:
            reaction = Messages.add_reaction_to_message('msg123', 'user456', 'heart')
        """
        with get_db() as db:
            reaction_id = str(uuid.uuid4())
            reaction = MessageReactionModel(
                id=reaction_id,
                user_id=user_id,
                message_id=id,
                name=name,
                created_at=int(time.time_ns()),
            )
            result = MessageReaction(**reaction.model_dump())
            db.add(result)
            db.commit()
            db.refresh(result)
            return MessageReactionModel.model_validate(result) if result else None

    def get_reactions_by_message_id(self, id: str) -> list[Reactions]:
        """
        Retrieve all reactions for a specific message.
        
        Aggregates reactions by their name, collecting unique user IDs and counting total reactions.
        
        Parameters:
            id (str): The unique identifier of the message to fetch reactions for.
        
        Returns:
            list[Reactions]: A list of reaction objects, each containing the reaction name, 
            list of user IDs who made the reaction, and total reaction count.
        
        Example:
            # Retrieve reactions for a message with ID 'msg123'
            reactions = Messages.get_reactions_by_message_id('msg123')
            # Result might look like: [
            #     Reactions(name='👍', user_ids=['user1', 'user2'], count=2),
            #     Reactions(name='❤️', user_ids=['user3'], count=1)
            # ]
        """
        with get_db() as db:
            all_reactions = db.query(MessageReaction).filter_by(message_id=id).all()

            reactions = {}
            for reaction in all_reactions:
                if reaction.name not in reactions:
                    reactions[reaction.name] = {
                        "name": reaction.name,
                        "user_ids": [],
                        "count": 0,
                    }
                reactions[reaction.name]["user_ids"].append(reaction.user_id)
                reactions[reaction.name]["count"] += 1

            return [Reactions(**reaction) for reaction in reactions.values()]

    def remove_reaction_by_id_and_user_id_and_name(
        self, id: str, user_id: str, name: str
    ) -> bool:
        """
        Remove a specific reaction from a message.
        
        Deletes a message reaction based on the message ID, user ID, and reaction name.
        
        Parameters:
            id (str): The unique identifier of the message
            user_id (str): The unique identifier of the user who added the reaction
            name (str): The name/type of the reaction to remove
        
        Returns:
            bool: Always returns True after successfully deleting the reaction
        
        Note:
            - Uses a database session to perform the deletion
            - Commits the transaction immediately after deletion
            - Will silently remove the reaction if it exists, or do nothing if no matching reaction is found
        """
        with get_db() as db:
            db.query(MessageReaction).filter_by(
                message_id=id, user_id=user_id, name=name
            ).delete()
            db.commit()
            return True

    def delete_reactions_by_id(self, id: str) -> bool:
        """
        Delete all reactions associated with a specific message.
        
        Parameters:
            id (str): The unique identifier of the message whose reactions are to be deleted.
        
        Returns:
            bool: Always returns True after successfully deleting the reactions.
        
        Side Effects:
            Removes all MessageReaction entries linked to the specified message ID from the database.
        """
        with get_db() as db:
            db.query(MessageReaction).filter_by(message_id=id).delete()
            db.commit()
            return True

    def delete_replies_by_id(self, id: str) -> bool:
        """
        Delete all replies associated with a specific message.
        
        Parameters:
            id (str): The unique identifier of the parent message whose replies are to be deleted.
        
        Returns:
            bool: Always returns True after deleting the replies.
        
        Side Effects:
            Permanently removes all messages in the database that have the specified message ID as their parent.
            Commits the deletion transaction to the database.
        """
        with get_db() as db:
            db.query(Message).filter_by(parent_id=id).delete()
            db.commit()
            return True

    def delete_message_by_id(self, id: str) -> bool:
        """
        Delete a message and all its associated reactions from the database.
        
        This method removes a specific message identified by its ID and all reactions linked to that message. 
        The deletion is performed within a database transaction, ensuring that both the message and its reactions 
        are completely removed.
        
        Parameters:
            id (str): The unique identifier of the message to be deleted.
        
        Returns:
            bool: Always returns True after successful deletion of the message and its reactions.
        
        Side Effects:
            - Removes the message with the specified ID from the Message table
            - Removes all reactions associated with the message from the MessageReaction table
            - Commits the transaction to persist the deletions
        
        Note:
            This method does not check for the existence of the message before deletion.
            If the message does not exist, no error will be raised, and the method will still return True.
        """
        with get_db() as db:
            db.query(Message).filter_by(id=id).delete()

            # Delete all reactions to this message
            db.query(MessageReaction).filter_by(message_id=id).delete()

            db.commit()
            return True


Messages = MessageTable()
