import json
import time
import uuid
from typing import Optional

from open_webui.internal.db import Base, get_db
from open_webui.utils.access_control import has_access

from pydantic import BaseModel, ConfigDict
from sqlalchemy import BigInteger, Boolean, Column, String, Text, JSON
from sqlalchemy import or_, func, select, and_, text
from sqlalchemy.sql import exists

####################
# Channel DB Schema
####################


class Channel(Base):
    __tablename__ = "channel"

    id = Column(Text, primary_key=True)
    user_id = Column(Text)
    type = Column(Text, nullable=True)

    name = Column(Text)
    description = Column(Text, nullable=True)

    data = Column(JSON, nullable=True)
    meta = Column(JSON, nullable=True)
    access_control = Column(JSON, nullable=True)

    created_at = Column(BigInteger)
    updated_at = Column(BigInteger)


class ChannelModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    type: Optional[str] = None

    name: str
    description: Optional[str] = None

    data: Optional[dict] = None
    meta: Optional[dict] = None
    access_control: Optional[dict] = None

    created_at: int  # timestamp in epoch
    updated_at: int  # timestamp in epoch


####################
# Forms
####################


class ChannelForm(BaseModel):
    name: str
    description: Optional[str] = None
    data: Optional[dict] = None
    meta: Optional[dict] = None
    access_control: Optional[dict] = None


class ChannelTable:
    def insert_new_channel(
        self, type: Optional[str], form_data: ChannelForm, user_id: str
    ) -> Optional[ChannelModel]:
        """
        Insert a new channel into the database.
        
        Creates a new channel with a unique identifier, associating it with a specific user and channel type.
        
        Parameters:
            type (Optional[str]): The type of the channel (e.g., 'chat', 'group')
            form_data (ChannelForm): Form data containing channel details like name, description, etc.
            user_id (str): Unique identifier of the user creating the channel
        
        Returns:
            Optional[ChannelModel]: The newly created channel model, or None if insertion fails
        
        Notes:
            - Generates a unique UUID for the channel
            - Converts channel name to lowercase
            - Sets creation and update timestamps in nanoseconds
            - Commits the new channel to the database
        """
        with get_db() as db:
            channel = ChannelModel(
                **{
                    **form_data.model_dump(),
                    "type": type,
                    "name": form_data.name.lower(),
                    "id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "created_at": int(time.time_ns()),
                    "updated_at": int(time.time_ns()),
                }
            )

            new_channel = Channel(**channel.model_dump())

            db.add(new_channel)
            db.commit()
            return channel

    def get_channels(self) -> list[ChannelModel]:
        """
        Retrieve all channels from the database.
        
        Retrieves a list of all channel records and converts them into Pydantic models for serialization.
        
        Returns:
            list[ChannelModel]: A list of channel models representing all channels in the database.
        
        Example:
            channels = Channels.get_channels()  # Returns all channel records
        """
        with get_db() as db:
            channels = db.query(Channel).all()
            return [ChannelModel.model_validate(channel) for channel in channels]

    def get_channels_by_user_id(
        self, user_id: str, permission: str = "read"
    ) -> list[ChannelModel]:
        """
        Retrieve channels accessible to a specific user based on their ID and permission level.
        
        Parameters:
            user_id (str): The unique identifier of the user requesting channel access.
            permission (str, optional): The type of access to check. Defaults to "read".
        
        Returns:
            list[ChannelModel]: A list of channels that either belong to the user or 
            the user has the specified permission to access.
        
        Notes:
            - Uses the `has_access()` function to check access control permissions
            - Returns all channels owned by the user and channels they have permission to access
            - Filters channels from the complete list of channels in the system
        """
        channels = self.get_channels()
        return [
            channel
            for channel in channels
            if channel.user_id == user_id
            or has_access(user_id, permission, channel.access_control)
        ]

    def get_channel_by_id(self, id: str) -> Optional[ChannelModel]:
        """
        Retrieve a channel by its unique identifier.
        
        Parameters:
            id (str): The unique identifier of the channel to fetch.
        
        Returns:
            Optional[ChannelModel]: The channel model if found, otherwise None.
        
        Raises:
            SQLAlchemyError: Potential database query error (implicitly).
        
        Example:
            channel = Channels.get_channel_by_id("channel_123")
            if channel:
                print(f"Channel found: {channel.name}")
        """
        with get_db() as db:
            channel = db.query(Channel).filter(Channel.id == id).first()
            return ChannelModel.model_validate(channel) if channel else None

    def update_channel_by_id(
        self, id: str, form_data: ChannelForm
    ) -> Optional[ChannelModel]:
        """
        Update an existing channel in the database by its unique identifier.
        
        Parameters:
            id (str): The unique identifier of the channel to be updated.
            form_data (ChannelForm): A form containing the updated channel details.
        
        Returns:
            Optional[ChannelModel]: The updated channel model if the channel exists and is successfully updated, 
            otherwise None.
        
        Raises:
            SQLAlchemy exceptions: Potential database-related errors during update operation.
        
        Notes:
            - Updates channel name, data, metadata, and access control
            - Automatically sets the updated_at timestamp to the current nanosecond timestamp
            - Requires an active database session
        """
        with get_db() as db:
            channel = db.query(Channel).filter(Channel.id == id).first()
            if not channel:
                return None

            channel.name = form_data.name
            channel.data = form_data.data
            channel.meta = form_data.meta
            channel.access_control = form_data.access_control
            channel.updated_at = int(time.time_ns())

            db.commit()
            return ChannelModel.model_validate(channel) if channel else None

    def delete_channel_by_id(self, id: str):
        """
        Delete a channel from the database by its unique identifier.
        
        Parameters:
            id (str): The unique identifier of the channel to be deleted.
        
        Returns:
            bool: Always returns True after successfully deleting the channel.
        
        Raises:
            SQLAlchemyError: Potential database-related exceptions during deletion.
        
        Notes:
            - This method permanently removes the channel from the database.
            - Uses a database session to perform the deletion.
            - Commits the transaction immediately after deletion.
        """
        with get_db() as db:
            db.query(Channel).filter(Channel.id == id).delete()
            db.commit()
            return True


Channels = ChannelTable()
