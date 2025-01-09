from contextlib import contextmanager

from fastapi import FastAPI


@contextmanager
def mock_webui_user(**kwargs):
    """
    A context manager to mock a WebUI user for testing purposes.
    
    This context manager temporarily sets up a mocked user context for the WebUI application
    by utilizing the `mock_user` context manager with the current application instance.
    
    Parameters:
        **kwargs: Optional keyword arguments to customize the mocked user's attributes.
                  These are passed directly to the underlying `mock_user` context manager.
    
    Yields:
        None: Provides a context for executing code with a mocked user authentication.
    
    Example:
        with mock_webui_user(role='admin'):
            # Perform tests with a mocked admin user
            ...
    """
    from open_webui.routers.webui import app

    with mock_user(app, **kwargs):
        yield


@contextmanager
def mock_user(app: FastAPI, **kwargs):
    """
    A context manager for mocking user authentication in a FastAPI application.
    
    This function creates a mock user with configurable parameters and temporarily overrides
    the application's user-related dependency functions to return the mocked user.
    
    Parameters:
        app (FastAPI): The FastAPI application instance to mock user dependencies for
        **kwargs: Optional keyword arguments to customize the mock user's attributes
    
    Yields:
        None: Provides a context for executing code with mocked user authentication
    
    Side Effects:
        - Temporarily replaces user authentication dependency functions
        - Restores original dependency functions after context is exited
    
    Example:
        with mock_user(app, name="Test User", role="admin"):
            # Code executed with a mocked admin user
            ...
    """
    from open_webui.utils.auth import (
        get_current_user,
        get_verified_user,
        get_admin_user,
        get_current_user_by_api_key,
    )
    from open_webui.models.users import User

    def create_user():
        """
        Create a mock user with default or customizable parameters.
        
        This function generates a User instance with predefined default values that can be overridden by additional keyword arguments.
        
        Parameters:
            **kwargs: Optional keyword arguments to customize user attributes. 
                      These will override the default user parameters.
        
        Returns:
            User: A User model instance with specified or default attributes.
        
        Example:
            # Create a default mock user
            default_user = create_user()
        
            # Create a mock user with custom email
            custom_user = create_user(email="custom@example.com", role="admin")
        """
        user_parameters = {
            "id": "1",
            "name": "John Doe",
            "email": "john.doe@openwebui.com",
            "role": "user",
            "profile_image_url": "/user.png",
            "last_active_at": 1627351200,
            "updated_at": 1627351200,
            "created_at": 162735120,
            **kwargs,
        }
        return User(**user_parameters)

    app.dependency_overrides = {
        get_current_user: create_user,
        get_verified_user: create_user,
        get_admin_user: create_user,
        get_current_user_by_api_key: create_user,
    }
    yield
    app.dependency_overrides = {}
