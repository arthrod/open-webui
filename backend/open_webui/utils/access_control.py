from typing import Optional, Union, List, Dict, Any
from open_webui.models.users import Users, UserModel
from open_webui.models.groups import Groups


from open_webui.config import DEFAULT_USER_PERMISSIONS
import json


def fill_missing_permissions(
    permissions: Dict[str, Any], default_permissions: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Recursively fill in missing keys in the permissions dictionary using the default permissions template.
    
    This function examines each key in the default permissions dictionary and ensures that it is present
    in the provided permissions dictionary. If a key is missing, it is added along with its default value.
    If the value corresponding to a key in both dictionaries is itself a dictionary, the function
    recursively updates the nested permissions. This approach maintains existing permission settings
    while ensuring that all expected keys are present.
    
    Parameters:
        permissions (Dict[str, Any]): A dictionary representing the current permission settings, which
            may include nested dictionaries.
        default_permissions (Dict[str, Any]): A dictionary containing the template of default permission values.
    
    Returns:
        Dict[str, Any]: The updated permissions dictionary with any missing keys filled in from the default permissions.
    
    Example:
        >>> current = {"read": True, "edit": {"update": False}}
        >>> defaults = {"read": False, "edit": {"update": True, "delete": False}, "admin": False}
        >>> fill_missing_permissions(current, defaults)
        {'read': True, 'edit': {'update': False, 'delete': False}, 'admin': False}
    """
    for key, value in default_permissions.items():
        if key not in permissions:
            permissions[key] = value
        elif isinstance(value, dict) and isinstance(
            permissions[key], dict
        ):  # Both are nested dictionaries
            permissions[key] = fill_missing_permissions(permissions[key], value)

    return permissions


def get_permissions(
    user_id: str,
    default_permissions: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Retrieve and merge effective permissions for a given user.
    
    This function computes the user's permissions by combining the default permissions with those
    granted by all groups to which the user belongs. It creates a deep copy of the default permissions,
    then iterates over each user group (retrieved via Groups.get_groups_by_member_id) and recursively merges
    the group's permissions using a "most permissive" strategy (i.e. a boolean True overrides False for
    non-dictionary values). Nested permission dictionaries are merged recursively. Finally, the function
    ensures that all keys defined in the default permissions are present in the final result by invoking
    fill_missing_permissions.
    
    Parameters:
        user_id (str): A unique identifier representing the user.
        default_permissions (Dict[str, Any]): A dictionary of the base permissions (which can include nested
            dictionaries) used as a default/fallback when a permission is not explicitly set.
    
    Returns:
        Dict[str, Any]: A dictionary containing the effective permissions for the user, with all keys from
        default_permissions ensured to be present.
    
    Example:
        >>> default = {"read": False, "write": False, "admin": {"access": False, "modify": False}}
        >>> effective = get_permissions("user123", default)
        >>> print(effective)
        {"read": True, "write": False, "admin": {"access": True, "modify": False}}
    
    Note:
        This function uses json.loads(json.dumps(...)) to deep copy the default permissions, which may
        impact performance for very large permission dictionaries.
    """

    def combine_permissions(
        permissions: Dict[str, Any], group_permissions: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Recursively combine two permissions dictionaries by merging nested permissions and selecting the most permissive value.
        
        This function iterates over keys in the provided `group_permissions` and merges them into the `permissions` dictionary. If a value is a dictionary, it recursively calls itself to merge nested permissions. For non-dictionary values, it uses the logical OR to ensure that a True (more permissive) value overrides a False value.
        
        Note:
            The input dictionary `permissions` is modified in place and also returned.
        
        Parameters:
            permissions (Dict[str, Any]): The base permissions dictionary to update.
            group_permissions (Dict[str, Any]): A dictionary containing permissions from a user group to merge.
        
        Returns:
            Dict[str, Any]: The updated permissions dictionary reflecting the combined permissions.
        
        Example:
            >>> base_permissions = {'read': False, 'write': False, 'admin': {'delete': False, 'update': False}}
            >>> group_permissions = {'read': True, 'admin': {'delete': True}}
            >>> combine_permissions(base_permissions, group_permissions)
            {'read': True, 'write': False, 'admin': {'delete': True, 'update': False}}
        """
        for key, value in group_permissions.items():
            if isinstance(value, dict):
                if key not in permissions:
                    permissions[key] = {}
                permissions[key] = combine_permissions(permissions[key], value)
            else:
                if key not in permissions:
                    permissions[key] = value
                else:
                    permissions[key] = (
                        permissions[key] or value
                    )  # Use the most permissive value (True > False)
        return permissions

    user_groups = Groups.get_groups_by_member_id(user_id)

    # Deep copy default permissions to avoid modifying the original dict
    permissions = json.loads(json.dumps(default_permissions))

    # Combine permissions from all user groups
    for group in user_groups:
        group_permissions = group.permissions
        permissions = combine_permissions(permissions, group_permissions)

    # Ensure all fields from default_permissions are present and filled in
    permissions = fill_missing_permissions(permissions, default_permissions)

    return permissions


def has_permission(
    user_id: str,
    permission_key: str,
    default_permissions: Dict[str, Any] = {},
) -> bool:
    """
    Determine whether a user has a specified permission.
    
    This function checks if the user identified by `user_id` has the given permission by traversing the hierarchical permission key (separated by dots) through the permissions defined in the user's groups. If any group grants the permission, the function returns True. If not, it falls back to checking the default permissions after filling in any missing permission keys from the global defaults.
    
    Parameters:
        user_id (str): The unique identifier for the user.
        permission_key (str): A dot-separated string representing the hierarchical permission to check (e.g., "read.article" or "write.profile").
        default_permissions (Dict[str, Any], optional): A dictionary representing default permissions. Missing keys in this dictionary are filled using `DEFAULT_USER_PERMISSIONS`. Defaults to an empty dictionary.
    
    Returns:
        bool: True if the permission is granted either by any user group or via the default permissions; False otherwise.
    
    Notes:
        - The function uses a nested helper function to traverse permission dictionaries according to the hierarchical keys.
        - It relies on `Groups.get_groups_by_member_id` to retrieve the groups associated with the user.
        - The default permissions are enhanced with missing keys by calling `fill_missing_permissions` before performing the final check.
    """

    def get_permission(permissions: Dict[str, Any], keys: List[str]) -> bool:
        """
        Traverse a nested permissions dictionary using a sequence of keys and return the effective permission.
        
        This function iterates through a list of keys—typically derived from splitting a dot-separated permission string—to progressively
        access nested levels of the permissions dictionary. If any key in the hierarchy is missing, the function immediately returns False,
        indicating that the permission is not granted. Otherwise, it converts the final value at the deepest level to a boolean and returns it.
        
        Parameters:
            permissions (Dict[str, Any]): A nested dictionary representing permission settings.
            keys (List[str]): A list of keys specifying the permission hierarchy.
        
        Returns:
            bool: True if the final permission value is truthy; False if any key is missing or if the final value is not truthy.
        """
        for key in keys:
            if key not in permissions:
                return False  # If any part of the hierarchy is missing, deny access
            permissions = permissions[key]  # Traverse one level deeper

        return bool(permissions)  # Return the boolean at the final level

    permission_hierarchy = permission_key.split(".")

    # Retrieve user group permissions
    user_groups = Groups.get_groups_by_member_id(user_id)

    for group in user_groups:
        group_permissions = group.permissions
        if get_permission(group_permissions, permission_hierarchy):
            return True

    # Check default permissions afterward if the group permissions don't allow it
    default_permissions = fill_missing_permissions(
        default_permissions, DEFAULT_USER_PERMISSIONS
    )
    return get_permission(default_permissions, permission_hierarchy)


def has_access(
    user_id: str,
    type: str = "write",
    access_control: Optional[dict] = None,
) -> bool:
    """
    Check if a user has the required access based on the provided access control settings.
    
    If no access control dictionary is provided, the function allows access only for "read" operations. Otherwise, it retrieves the groups associated with the user and verifies if either the user ID or any of the user's group IDs are explicitly permitted for the specified access type.
    
    Parameters:
        user_id (str): Unique identifier for the user.
        type (str, optional): The access type to check (e.g., "write", "read"). Defaults to "write".
        access_control (Optional[dict], optional): A dictionary defining access control rules. It should map access types (str) to sub-dictionaries containing:
            - "group_ids" (list): List of permitted group identifiers.
            - "user_ids" (list): List of permitted user identifiers.
            Defaults to None.
    
    Returns:
        bool: True if the user has access according to the access control rules; otherwise, False.
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
