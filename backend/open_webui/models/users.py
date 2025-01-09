import time
from typing import Optional

from open_webui.internal.db import Base, JSONField, get_db
from open_webui.models.chats import Chats
from pydantic import BaseModel, ConfigDict
from sqlalchemy import BigInteger, Column, String, Text

####################
# User DB Schema
####################


class User(Base):
    __tablename__ = "user"

    id = Column(String, primary_key=True)
    name = Column(String)
    email = Column(String)
    role = Column(String)
    profile_image_url = Column(Text)

    last_active_at = Column(BigInteger)
    updated_at = Column(BigInteger)
    created_at = Column(BigInteger)

    api_key = Column(String, nullable=True, unique=True)
    settings = Column(JSONField, nullable=True)
    info = Column(JSONField, nullable=True)

    oauth_sub = Column(Text, unique=True)


class UserSettings(BaseModel):
    ui: Optional[dict] = {}
    model_config = ConfigDict(extra="allow")
    pass


class UserModel(BaseModel):
    id: str
    name: str
    email: str
    role: str = "pending"
    profile_image_url: str

    last_active_at: int  # timestamp in epoch
    updated_at: int  # timestamp in epoch
    created_at: int  # timestamp in epoch

    api_key: Optional[str] = None
    settings: Optional[UserSettings] = None
    info: Optional[dict] = None

    oauth_sub: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


####################
# Forms
####################


class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    role: str
    profile_image_url: str


class UserNameResponse(BaseModel):
    id: str
    name: str
    role: str
    profile_image_url: str


class UserRoleUpdateForm(BaseModel):
    id: str
    role: str


class UserUpdateForm(BaseModel):
    name: str
    email: str
    profile_image_url: str
    password: Optional[str] = None


class UsersTable:
    def insert_new_user(
        self,
        id: str,
        name: str,
        email: str,
        profile_image_url: str = "/user.png",
        role: str = "pending",
        oauth_sub: Optional[str] = None,
    ) -> Optional[UserModel]:
        with get_db() as db:
            user = UserModel(
                **{
                    "id": id,
                    "name": name,
                    "email": email,
                    "role": role,
                    "profile_image_url": profile_image_url,
                    "last_active_at": int(time.time()),
                    "created_at": int(time.time()),
                    "updated_at": int(time.time()),
                    "oauth_sub": oauth_sub,
                }
            )
            result = User(**user.model_dump())
            db.add(result)
            db.commit()
            db.refresh(result)
            if result:
                return user
            else:
                return None

    def get_user_by_id(self, id: str) -> Optional[UserModel]:
        try:
            with get_db() as db:
                user = db.query(User).filter_by(id=id).first()
                return UserModel.model_validate(user)
        except Exception:
            return None

    def get_user_by_api_key(self, api_key: str) -> Optional[UserModel]:
        try:
            with get_db() as db:
                user = db.query(User).filter_by(api_key=api_key).first()
                return UserModel.model_validate(user)
        except Exception:
            return None

    def get_user_by_email(self, email: str) -> Optional[UserModel]:
        try:
            with get_db() as db:
                user = db.query(User).filter_by(email=email).first()
                return UserModel.model_validate(user)
        except Exception:
            return None

    def get_user_by_oauth_sub(self, sub: str) -> Optional[UserModel]:
        """
        Retrieve a user by their OAuth subscription identifier.
        
        Parameters:
            sub (str): The OAuth subscription identifier to search for.
        
        Returns:
            Optional[UserModel]: The user model if found, otherwise None.
        
        Raises:
            No explicit exceptions are raised; errors result in returning None.
        
        Description:
            Queries the database to find a user with the matching OAuth subscription ID.
            Uses a database session to perform a single query filtering by oauth_sub.
            Returns a validated UserModel if a matching user is found, otherwise returns None.
        """
        try:
            with get_db() as db:
                user = db.query(User).filter_by(oauth_sub=sub).first()
                return UserModel.model_validate(user)
        except Exception:
            return None

    def get_users(
        self, skip: Optional[int] = None, limit: Optional[int] = None
    ) -> list[UserModel]:
        """
        Retrieve a list of users from the database with optional pagination.
        
        Fetches users ordered by creation time in descending order, with optional skip and limit parameters
        for pagination control.
        
        Parameters:
            skip (Optional[int], optional): Number of users to skip before starting to return results.
                Defaults to None.
            limit (Optional[int], optional): Maximum number of users to return. Defaults to None.
        
        Returns:
            list[UserModel]: A list of user models, sorted by creation time from newest to oldest.
        
        Example:
            # Retrieve first 10 users
            users = users_table.get_users(limit=10)
        
            # Retrieve users starting from the 20th user
            users = users_table.get_users(skip=20)
        
            # Retrieve 5 users after skipping the first 10
            users = users_table.get_users(skip=10, limit=5)
        """
        with get_db() as db:

            query = db.query(User).order_by(User.created_at.desc())

            if skip:
                query = query.offset(skip)
            if limit:
                query = query.limit(limit)

            users = query.all()

            return [UserModel.model_validate(user) for user in users]

    def get_users_by_user_ids(self, user_ids: list[str]) -> list[UserModel]:
        """
        Retrieve users from the database based on a list of user IDs.
        
        Parameters:
            user_ids (list[str]): A list of user IDs to fetch.
        
        Returns:
            list[UserModel]: A list of UserModel instances corresponding to the provided user IDs. 
            Returns an empty list if no users are found matching the given IDs.
        
        Example:
            # Fetch users with specific IDs
            user_ids = ['user1', 'user2', 'user3']
            users = users_table.get_users_by_user_ids(user_ids)
        """
        with get_db() as db:
            users = db.query(User).filter(User.id.in_(user_ids)).all()
            return [UserModel.model_validate(user) for user in users]

    def get_num_users(self) -> Optional[int]:
        """
        Retrieve the total number of users in the database.
        
        Returns:
            Optional[int]: The total count of users in the database, or None if an error occurs during the query.
        
        Raises:
            SQLAlchemyError: Potential database-related exceptions are implicitly handled, returning None in case of errors.
        """
        with get_db() as db:
            return db.query(User).count()

    def get_first_user(self) -> UserModel:
        """
        Retrieve the first user from the database based on creation timestamp.
        
        This method queries the database to find the earliest created user, sorted by the 'created_at' timestamp.
        
        Returns:
            UserModel: The first user in the database, converted to a Pydantic model, or None if no users exist or an error occurs.
        
        Raises:
            No explicit exceptions are raised; errors result in returning None.
        """
        try:
            with get_db() as db:
                user = db.query(User).order_by(User.created_at).first()
                return UserModel.model_validate(user)
        except Exception:
            return None

    def get_user_webhook_url_by_id(self, id: str) -> Optional[str]:
        """
        Retrieve the webhook URL from a user's settings by their user ID.
        
        This method attempts to fetch the webhook URL from the user's settings, navigating through nested dictionaries.
        If the user is not found, the settings are None, or the webhook URL is not configured, it returns None.
        
        Parameters:
            id (str): The unique identifier of the user.
        
        Returns:
            Optional[str]: The configured webhook URL if found, otherwise None.
        
        Raises:
            No explicit exceptions are raised; any errors result in returning None.
        """
        try:
            with get_db() as db:
                user = db.query(User).filter_by(id=id).first()

                if user.settings is None:
                    return None
                else:
                    return (
                        user.settings.get("ui", {})
                        .get("notifications", {})
                        .get("webhook_url", None)
                    )
        except Exception:
            return None

    def update_user_role_by_id(self, id: str, role: str) -> Optional[UserModel]:
        """
        Update a user's role by their unique identifier.
        
        Parameters:
            id (str): The unique identifier of the user to update.
            role (str): The new role to assign to the user.
        
        Returns:
            Optional[UserModel]: The updated user model if the role update is successful, 
            otherwise None if an error occurs during the update process.
        
        Raises:
            No explicit exceptions are raised; errors are silently handled by returning None.
        
        Example:
            # Update a user's role to 'admin'
            updated_user = users_table.update_user_role_by_id('user123', 'admin')
        """
        try:
            with get_db() as db:
                db.query(User).filter_by(id=id).update({"role": role})
                db.commit()
                user = db.query(User).filter_by(id=id).first()
                return UserModel.model_validate(user)
        except Exception:
            return None

    def update_user_profile_image_url_by_id(
        self, id: str, profile_image_url: str
    ) -> Optional[UserModel]:
        try:
            with get_db() as db:
                db.query(User).filter_by(id=id).update(
                    {"profile_image_url": profile_image_url}
                )
                db.commit()

                user = db.query(User).filter_by(id=id).first()
                return UserModel.model_validate(user)
        except Exception:
            return None

    def update_user_last_active_by_id(self, id: str) -> Optional[UserModel]:
        try:
            with get_db() as db:
                db.query(User).filter_by(id=id).update(
                    {"last_active_at": int(time.time())}
                )
                db.commit()

                user = db.query(User).filter_by(id=id).first()
                return UserModel.model_validate(user)
        except Exception:
            return None

    def update_user_oauth_sub_by_id(
        self, id: str, oauth_sub: str
    ) -> Optional[UserModel]:
        try:
            with get_db() as db:
                db.query(User).filter_by(id=id).update({"oauth_sub": oauth_sub})
                db.commit()

                user = db.query(User).filter_by(id=id).first()
                return UserModel.model_validate(user)
        except Exception:
            return None

    def update_user_by_id(self, id: str, updated: dict) -> Optional[UserModel]:
        try:
            with get_db() as db:
                db.query(User).filter_by(id=id).update(updated)
                db.commit()

                user = db.query(User).filter_by(id=id).first()
                return UserModel.model_validate(user)
                # return UserModel(**user.dict())
        except Exception:
            return None

    def delete_user_by_id(self, id: str) -> bool:
        try:
            # Delete User Chats
            result = Chats.delete_chats_by_user_id(id)

            if result:
                with get_db() as db:
                    # Delete User
                    db.query(User).filter_by(id=id).delete()
                    db.commit()

                return True
            else:
                return False
        except Exception:
            return False

    def update_user_api_key_by_id(self, id: str, api_key: str) -> str:
        try:
            with get_db() as db:
                result = db.query(User).filter_by(id=id).update({"api_key": api_key})
                db.commit()
                return True if result == 1 else False
        except Exception:
            return False

    def get_user_api_key_by_id(self, id: str) -> Optional[str]:
        try:
            with get_db() as db:
                user = db.query(User).filter_by(id=id).first()
                return user.api_key
        except Exception:
            return None


Users = UsersTable()
