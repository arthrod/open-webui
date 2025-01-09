from typing import Optional, Union, List, Dict, Any
from open_webui.models.users import Users, UserModel
from open_webui.models.groups import Groups
import json


def get_permissions(
    user_id: str,
    default_permissions: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Get all permissions for a user by combining the permissions of all groups the user is a member of.
    
    This function aggregates permissions from all groups a user belongs to, using a recursive merging strategy that prioritizes the most permissive values. Nested permission dictionaries are deeply merged, with boolean values resolved to the most permissive option (True takes precedence over False).
    
    Parameters:
        user_id (str): The unique identifier of the user whose permissions are being retrieved.
        default_permissions (Dict[str, Any]): A dictionary of default permissions to use as the initial permission set.
    
    Returns:
        Dict[str, Any]: A comprehensive permissions dictionary combining group-level permissions with default permissions.
    
    Notes:
        - Permissions are merged recursively for nested dictionary structures
        - If a permission exists in multiple groups, the most permissive value is retained
        - The function creates a deep copy of default_permissions to prevent unintended modifications
    """

    def combine_permissions(
        permissions: Dict[str, Any], group_permissions: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Combine permissions from multiple groups by taking the most permissive value."""
        for key, value in group_permissions.items():
            if isinstance(value, dict):
                if key not in permissions:
                    permissions[key] = {}
                permissions[key] = combine_permissions(permissions[key], value)
            else:
                if key not in permissions:
                    permissions[key] = value
                else:
                    permissions[key] = permissions[key] or value
        return permissions

    user_groups = Groups.get_groups_by_member_id(user_id)

    # deep copy default permissions to avoid modifying the original dict
    permissions = json.loads(json.dumps(default_permissions))

    for group in user_groups:
        group_permissions = group.permissions
        permissions = combine_permissions(permissions, group_permissions)

    return permissions


def has_permission(
    user_id: str,
    permission_key: str,
    default_permissions: Dict[str, bool] = {},
) -> bool:
    """
    Check if a user has a specific permission by checking the group permissions
    and falls back to default permissions if not found in any group.

    Permission keys can be hierarchical and separated by dots ('.').
    """

    def get_permission(permissions: Dict[str, bool], keys: List[str]) -> bool:
        """Traverse permissions dict using a list of keys (from dot-split permission_key)."""
        for key in keys:
            if key not in permissions:
                return False  # If any part of the hierarchy is missing, deny access
            permissions = permissions[key]  # Go one level deeper

        return bool(permissions)  # Return the boolean at the final level

    permission_hierarchy = permission_key.split(".")

    # Retrieve user group permissions
    user_groups = Groups.get_groups_by_member_id(user_id)

    for group in user_groups:
        group_permissions = group.permissions
        if get_permission(group_permissions, permission_hierarchy):
            return True

    # Check default permissions afterwards if the group permissions don't allow it
    return get_permission(default_permissions, permission_hierarchy)


def has_access(
    user_id: str,
    type: str = "write",
    access_control: Optional[dict] = None,
) -> bool:
    """
    Determine if a user has access to a resource based on specified access type.
    
    Parameters:
        user_id (str): The unique identifier of the user requesting access.
        type (str, optional): The type of access to check. Defaults to "write".
        access_control (dict, optional): A dictionary defining access control rules. 
            If None, defaults to read-only access.
    
    Returns:
        bool: True if the user has access, False otherwise.
    
    Description:
        Checks user access by:
        - Returning True for read access if no access control is specified
        - Checking if the user is directly permitted by user ID
        - Checking if any of the user's groups are permitted
    
    Examples:
        # Allow read access by default
        has_access("user123")  # Returns True
    
        # Specific access control
        access_rules = {
            "write": {
                "user_ids": ["admin123"],
                "group_ids": ["editors"]
            }
        }
        has_access("user123", "write", access_rules)  # Depends on user's groups/ID
    """
    if access_control is None:
        return type == "read"

    user_groups = Groups.get_groups_by_member_id(user_id)
    user_group_ids = [group.id for group in user_groups]
    permission_access = access_control.get(type, {})
    permitted_group_ids = permission_access.get("group_ids", [])
    permitted_user_ids = permission_access.get("user_ids", [])

    return user_id in permitted_user_ids or any(
        group_id in permitted_group_ids for group_id in user_group_ids
    )


# Get all users with access to a resource
def get_users_with_access(
    type: str = "write", access_control: Optional[dict] = None
) -> List[UserModel]:
    """
    Retrieve users with access to a resource based on specified access type and control settings.
    
    Determines user access by checking both explicitly permitted user IDs and group memberships. 
    If no access control is provided, returns all users in the system.
    
    Parameters:
        type (str, optional): Access type to check, defaults to "write".
        access_control (dict, optional): Dictionary defining access permissions for groups and users.
    
    Returns:
        List[UserModel]: List of users with access to the specified resource.
    
    Examples:
        # Get all users with write access
        users = get_users_with_access()
    
        # Get users with access based on specific access control
        custom_access = {
            "write": {
                "group_ids": ["admin_group"],
                "user_ids": ["special_user"]
            }
        }
        users = get_users_with_access(type="write", access_control=custom_access)
    """
    if access_control is None:
        return Users.get_users()

    permission_access = access_control.get(type, {})
    permitted_group_ids = permission_access.get("group_ids", [])
    permitted_user_ids = permission_access.get("user_ids", [])

    user_ids_with_access = set(permitted_user_ids)

    for group_id in permitted_group_ids:
        group_user_ids = Groups.get_group_user_ids_by_id(group_id)
        if group_user_ids:
            user_ids_with_access.update(group_user_ids)

    return Users.get_users_by_user_ids(list(user_ids_with_access))
