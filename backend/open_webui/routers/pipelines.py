from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
    APIRouter,
)
import os
import logging
import shutil
import requests
from pydantic import BaseModel
from starlette.responses import FileResponse
from typing import Optional

from open_webui.env import SRC_LOG_LEVELS
from open_webui.config import CACHE_DIR
from open_webui.constants import ERROR_MESSAGES


from open_webui.routers.openai import get_all_models_responses

from open_webui.utils.auth import get_admin_user

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MAIN"])


##################################
#
# Pipeline Middleware
#
##################################


def get_sorted_filters(model_id, models):
    """
    Retrieve and sort filters for a specific model based on their priority.
    
    This function filters models to find those configured as pipeline filters that are applicable to the given model ID. 
    Filters are selected based on either being applicable to all pipelines ('*') or explicitly matching the target model ID.
    
    Parameters:
        model_id (str): The identifier of the model for which filters are being retrieved
        models (dict): A dictionary of available models containing pipeline configuration details
    
    Returns:
        list: A sorted list of filter models, ordered by their priority in ascending order
    
    Example:
        >>> models = {
        ...     'filter1': {'pipeline': {'type': 'filter', 'pipelines': ['model1'], 'priority': 2}},
        ...     'filter2': {'pipeline': {'type': 'filter', 'pipelines': ['*'], 'priority': 1}}
        ... }
        >>> get_sorted_filters('model1', models)
        # Returns sorted list of applicable filter models
    """
    filters = [
        model
        for model in models.values()
        if "pipeline" in model
        and "type" in model["pipeline"]
        and model["pipeline"]["type"] == "filter"
        and (
            model["pipeline"]["pipelines"] == ["*"]
            or any(
                model_id == target_model_id
                for target_model_id in model["pipeline"]["pipelines"]
            )
        )
    ]
    sorted_filters = sorted(filters, key=lambda x: x["pipeline"]["priority"])
    return sorted_filters


def process_pipeline_inlet_filter(request, payload, user, models):
    """
    Process inlet filters for a given pipeline model.
    
    This function applies a series of inlet filters to the payload before the main pipeline processing. It retrieves sorted filters for a specific model, including the model itself if a pipeline is defined, and sequentially applies each filter's inlet processing.
    
    Parameters:
        request (Request): The current HTTP request object
        payload (dict): The input payload to be processed through inlet filters
        user (User): The authenticated user making the request
        models (dict): A dictionary of available models
    
    Returns:
        dict: The payload after being processed through all applicable inlet filters
    
    Raises:
        Exception: If a filter returns an error or encounters a connection issue
    
    Notes:
        - Filters are applied in order of their priority
        - Skips filters with empty API keys
        - Modifies the payload in-place by updating it with each filter's response
    """
    user = {"id": user.id, "email": user.email, "name": user.name, "role": user.role}
    model_id = payload["model"]

    sorted_filters = get_sorted_filters(model_id, models)
    model = models[model_id]

    if "pipeline" in model:
        sorted_filters.append(model)

    for filter in sorted_filters:
        r = None
        try:
            urlIdx = filter["urlIdx"]

            url = request.app.state.config.OPENAI_API_BASE_URLS[urlIdx]
            key = request.app.state.config.OPENAI_API_KEYS[urlIdx]

            if key == "":
                continue

            headers = {"Authorization": f"Bearer {key}"}
            r = requests.post(
                f"{url}/{filter['id']}/filter/inlet",
                headers=headers,
                json={
                    "user": user,
                    "body": payload,
                },
            )

            r.raise_for_status()
            payload = r.json()
        except Exception as e:
            # Handle connection error here
            print(f"Connection error: {e}")

            if r is not None:
                res = r.json()
                if "detail" in res:
                    raise Exception(r.status_code, res["detail"])

    return payload


def process_pipeline_outlet_filter(request, payload, user, models):
    """
    Process outlet filters for a pipeline model.
    
    Applies a series of outlet filters to the payload for a specific model. Filters are sorted by priority and include the model's pipeline filter if defined.
    
    Parameters:
        request (Request): The current HTTP request object
        payload (dict): The payload to be processed through outlet filters
        user (User): The authenticated user object
        models (dict): Dictionary of available models
    
    Returns:
        dict: The processed payload after applying all outlet filters
    
    Raises:
        Exception: If a filter returns an error response or a connection error occurs
    
    Notes:
        - Extracts user details for filter processing
        - Retrieves and sorts filters for the specified model
        - Sends filter requests to each filter's API endpoint
        - Updates payload with each filter's response
        - Handles potential connection and API errors
    """
    user = {"id": user.id, "email": user.email, "name": user.name, "role": user.role}
    model_id = payload["model"]

    sorted_filters = get_sorted_filters(model_id, models)
    model = models[model_id]

    if "pipeline" in model:
        sorted_filters = [model] + sorted_filters

    for filter in sorted_filters:
        r = None
        try:
            urlIdx = filter["urlIdx"]

            url = request.app.state.config.OPENAI_API_BASE_URLS[urlIdx]
            key = request.app.state.config.OPENAI_API_KEYS[urlIdx]

            if key != "":
                r = requests.post(
                    f"{url}/{filter['id']}/filter/outlet",
                    headers={"Authorization": f"Bearer {key}"},
                    json={
                        "user": user,
                        "body": payload,
                    },
                )

                r.raise_for_status()
                data = r.json()
                payload = data
        except Exception as e:
            # Handle connection error here
            print(f"Connection error: {e}")

            if r is not None:
                try:
                    res = r.json()
                    if "detail" in res:
                        return Exception(r.status_code, res)
                except Exception:
                    pass

            else:
                pass

    return payload


##################################
#
# Pipelines Endpoints
#
##################################

router = APIRouter()


@router.get("/list")
async def get_pipelines_list(request: Request, user=Depends(get_admin_user)):
    """
    Retrieves a list of available pipelines from configured API endpoints.
    
    This asynchronous function fetches pipeline information from multiple configured API URLs and returns a list of available pipeline sources.
    
    Parameters:
        request (Request): The incoming HTTP request object
        user (dict, optional): Authenticated admin user, obtained via dependency injection
    
    Returns:
        dict: A dictionary containing a list of pipeline sources with their URL and index, where:
            - 'url' is the base URL of the API endpoint
            - 'idx' is the index of the URL in the configuration
    
    Raises:
        HTTPException: If there are issues retrieving pipeline information or authentication fails
    
    Notes:
        - Requires admin user authentication
        - Filters out API endpoints that do not support pipelines
        - Logs debug information about retrieved model responses
    """
    responses = await get_all_models_responses(request)
    log.debug(f"get_pipelines_list: get_openai_models_responses returned {responses}")

    urlIdxs = [
        idx
        for idx, response in enumerate(responses)
        if response is not None and "pipelines" in response
    ]

    return {
        "data": [
            {
                "url": request.app.state.config.OPENAI_API_BASE_URLS[urlIdx],
                "idx": urlIdx,
            }
            for urlIdx in urlIdxs
        ]
    }


@router.post("/upload")
async def upload_pipeline(
    request: Request,
    urlIdx: int = Form(...),
    file: UploadFile = File(...),
    user=Depends(get_admin_user),
):
    """
    Upload a Python pipeline file to a specified API endpoint.
    
    This asynchronous function handles the upload of a Python pipeline file, performing several key operations:
    - Validates that only Python (.py) files are uploaded
    - Saves the uploaded file to a temporary cache directory
    - Sends the file to a specified API endpoint for pipeline registration
    - Handles potential errors during file upload and API communication
    - Ensures the uploaded file is deleted after processing
    
    Parameters:
        request (Request): The incoming HTTP request object
        urlIdx (int): Index of the API URL to use for pipeline upload
        file (UploadFile): The uploaded Python file to be processed
        user (dict, optional): Admin user authentication dependency
    
    Returns:
        dict: Response data from the pipeline upload API endpoint
    
    Raises:
        HTTPException: 
            - 400 Bad Request if the file is not a Python file
            - 404 Not Found if the pipeline cannot be uploaded
            - Other status codes based on API response errors
    """
    print("upload_pipeline", urlIdx, file.filename)
    # Check if the uploaded file is a python file
    if not (file.filename and file.filename.endswith(".py")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only Python (.py) files are allowed.",
        )

    upload_folder = f"{CACHE_DIR}/pipelines"
    os.makedirs(upload_folder, exist_ok=True)
    file_path = os.path.join(upload_folder, file.filename)

    r = None
    try:
        # Save the uploaded file
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        url = request.app.state.config.OPENAI_API_BASE_URLS[urlIdx]
        key = request.app.state.config.OPENAI_API_KEYS[urlIdx]

        with open(file_path, "rb") as f:
            files = {"file": f}
            r = requests.post(
                f"{url}/pipelines/upload",
                headers={"Authorization": f"Bearer {key}"},
                files=files,
            )

        r.raise_for_status()
        data = r.json()

        return {**data}
    except Exception as e:
        # Handle connection error here
        print(f"Connection error: {e}")

        detail = None
        status_code = status.HTTP_404_NOT_FOUND
        if r is not None:
            status_code = r.status_code
            try:
                res = r.json()
                if "detail" in res:
                    detail = res["detail"]
            except Exception:
                pass

        raise HTTPException(
            status_code=status_code,
            detail=detail if detail else "Pipeline not found",
        )
    finally:
        # Ensure the file is deleted after the upload is completed or on failure
        if os.path.exists(file_path):
            os.remove(file_path)


class AddPipelineForm(BaseModel):
    url: str
    urlIdx: int


@router.post("/add")
async def add_pipeline(
    request: Request, form_data: AddPipelineForm, user=Depends(get_admin_user)
):
    """
    Add a new pipeline to the system by sending a request to the specified API endpoint.
    
    This asynchronous function allows an admin user to add a new pipeline by providing a URL. It uses the configured API base URL and key corresponding to the specified URL index to make the request.
    
    Parameters:
        request (Request): The incoming HTTP request object
        form_data (AddPipelineForm): Form data containing the pipeline URL and URL index
        user (dict, optional): Admin user authentication dependency
    
    Returns:
        dict: The response data from the pipeline addition request
    
    Raises:
        HTTPException: If there's an error adding the pipeline, with appropriate status code and error details
    """
    r = None
    try:
        urlIdx = form_data.urlIdx

        url = request.app.state.config.OPENAI_API_BASE_URLS[urlIdx]
        key = request.app.state.config.OPENAI_API_KEYS[urlIdx]

        r = requests.post(
            f"{url}/pipelines/add",
            headers={"Authorization": f"Bearer {key}"},
            json={"url": form_data.url},
        )

        r.raise_for_status()
        data = r.json()

        return {**data}
    except Exception as e:
        # Handle connection error here
        print(f"Connection error: {e}")

        detail = None
        if r is not None:
            try:
                res = r.json()
                if "detail" in res:
                    detail = res["detail"]
            except Exception:
                pass

        raise HTTPException(
            status_code=(r.status_code if r is not None else status.HTTP_404_NOT_FOUND),
            detail=detail if detail else "Pipeline not found",
        )


class DeletePipelineForm(BaseModel):
    id: str
    urlIdx: int


@router.delete("/delete")
async def delete_pipeline(
    request: Request, form_data: DeletePipelineForm, user=Depends(get_admin_user)
):
    """
    Delete a specific pipeline from the configured API endpoint.
    
    Sends a delete request to the specified pipeline URL with admin authentication. 
    Handles potential connection errors and returns the API response or raises an HTTPException.
    
    Parameters:
        request (Request): The incoming HTTP request containing application configuration
        form_data (DeletePipelineForm): Form data containing pipeline ID and URL index
        user (dict, optional): Admin user authentication dependency
    
    Returns:
        dict: API response data from the pipeline deletion request
    
    Raises:
        HTTPException: If the pipeline deletion fails, with appropriate status code and error details
    """
    r = None
    try:
        urlIdx = form_data.urlIdx

        url = request.app.state.config.OPENAI_API_BASE_URLS[urlIdx]
        key = request.app.state.config.OPENAI_API_KEYS[urlIdx]

        r = requests.delete(
            f"{url}/pipelines/delete",
            headers={"Authorization": f"Bearer {key}"},
            json={"id": form_data.id},
        )

        r.raise_for_status()
        data = r.json()

        return {**data}
    except Exception as e:
        # Handle connection error here
        print(f"Connection error: {e}")

        detail = None
        if r is not None:
            try:
                res = r.json()
                if "detail" in res:
                    detail = res["detail"]
            except Exception:
                pass

        raise HTTPException(
            status_code=(r.status_code if r is not None else status.HTTP_404_NOT_FOUND),
            detail=detail if detail else "Pipeline not found",
        )


@router.get("/")
async def get_pipelines(
    request: Request, urlIdx: Optional[int] = None, user=Depends(get_admin_user)
):
    """
    Retrieve all pipelines from a specified API endpoint.
    
    This asynchronous function fetches pipelines from a configured API URL, requiring admin user authentication.
    
    Parameters:
        request (Request): The incoming HTTP request object
        urlIdx (Optional[int], optional): Index of the API URL to query. Defaults to None.
        user: Admin user dependency for authentication
    
    Returns:
        dict: A dictionary containing the retrieved pipelines
    
    Raises:
        HTTPException: If there's an error connecting to the API or retrieving pipelines
            - status_code: HTTP status code of the error (404 if no response)
            - detail: Specific error message from the API or a default message
    """
    r = None
    try:
        url = request.app.state.config.OPENAI_API_BASE_URLS[urlIdx]
        key = request.app.state.config.OPENAI_API_KEYS[urlIdx]

        r = requests.get(f"{url}/pipelines", headers={"Authorization": f"Bearer {key}"})

        r.raise_for_status()
        data = r.json()

        return {**data}
    except Exception as e:
        # Handle connection error here
        print(f"Connection error: {e}")

        detail = None
        if r is not None:
            try:
                res = r.json()
                if "detail" in res:
                    detail = res["detail"]
            except Exception:
                pass

        raise HTTPException(
            status_code=(r.status_code if r is not None else status.HTTP_404_NOT_FOUND),
            detail=detail if detail else "Pipeline not found",
        )


@router.get("/{pipeline_id}/valves")
async def get_pipeline_valves(
    request: Request,
    urlIdx: Optional[int],
    pipeline_id: str,
    user=Depends(get_admin_user),
):
    """
    Retrieve valves for a specific pipeline from an external API.
    
    This asynchronous function fetches the valves configuration for a given pipeline by making a GET request
    to an external API endpoint. It requires admin user authentication and supports multiple API base URLs.
    
    Parameters:
        request (Request): The incoming HTTP request object
        urlIdx (Optional[int]): Index of the API base URL to use
        pipeline_id (str): Unique identifier of the pipeline
        user: Admin user dependency for authentication
    
    Returns:
        dict: A dictionary containing the pipeline's valve configurations
    
    Raises:
        HTTPException: If there's an error connecting to the API or retrieving the valves
            - status_code 404 if pipeline is not found
            - status_code from the external API response if available
            - Includes detailed error message if provided by the external API
    """
    r = None
    try:
        url = request.app.state.config.OPENAI_API_BASE_URLS[urlIdx]
        key = request.app.state.config.OPENAI_API_KEYS[urlIdx]

        r = requests.get(
            f"{url}/{pipeline_id}/valves", headers={"Authorization": f"Bearer {key}"}
        )

        r.raise_for_status()
        data = r.json()

        return {**data}
    except Exception as e:
        # Handle connection error here
        print(f"Connection error: {e}")

        detail = None
        if r is not None:
            try:
                res = r.json()
                if "detail" in res:
                    detail = res["detail"]
            except Exception:
                pass

        raise HTTPException(
            status_code=(r.status_code if r is not None else status.HTTP_404_NOT_FOUND),
            detail=detail if detail else "Pipeline not found",
        )


@router.get("/{pipeline_id}/valves/spec")
async def get_pipeline_valves_spec(
    request: Request,
    urlIdx: Optional[int],
    pipeline_id: str,
    user=Depends(get_admin_user),
):
    """
    Retrieve the valve specifications for a specific pipeline.
    
    This asynchronous function fetches the valve specifications from a specified pipeline API endpoint. It requires admin user authentication and supports multiple API base URLs.
    
    Parameters:
        request (Request): The incoming HTTP request object
        urlIdx (Optional[int]): Index of the API base URL to use
        pipeline_id (str): Unique identifier of the pipeline
        user: Admin user dependency for authentication
    
    Returns:
        dict: A dictionary containing the valve specifications for the specified pipeline
    
    Raises:
        HTTPException: If there is an error connecting to the pipeline API or retrieving the valve specifications
            - status_code: HTTP status code of the error (404 if no response, otherwise from the API)
            - detail: Detailed error message from the API or a default "Pipeline not found" message
    """
    r = None
    try:
        url = request.app.state.config.OPENAI_API_BASE_URLS[urlIdx]
        key = request.app.state.config.OPENAI_API_KEYS[urlIdx]

        r = requests.get(
            f"{url}/{pipeline_id}/valves/spec",
            headers={"Authorization": f"Bearer {key}"},
        )

        r.raise_for_status()
        data = r.json()

        return {**data}
    except Exception as e:
        # Handle connection error here
        print(f"Connection error: {e}")

        detail = None
        if r is not None:
            try:
                res = r.json()
                if "detail" in res:
                    detail = res["detail"]
            except Exception:
                pass

        raise HTTPException(
            status_code=(r.status_code if r is not None else status.HTTP_404_NOT_FOUND),
            detail=detail if detail else "Pipeline not found",
        )


@router.post("/{pipeline_id}/valves/update")
async def update_pipeline_valves(
    request: Request,
    urlIdx: Optional[int],
    pipeline_id: str,
    form_data: dict,
    user=Depends(get_admin_user),
):
    """
    Update pipeline valves for a specific pipeline by sending a POST request to the specified API endpoint.
    
    This asynchronous function allows updating valve configurations for a given pipeline. It requires admin user authentication
    and handles potential connection errors during the API request.
    
    Parameters:
        request (Request): The incoming HTTP request object
        urlIdx (Optional[int]): Index of the API base URL to use
        pipeline_id (str): Unique identifier of the pipeline to update
        form_data (dict): Dictionary containing valve configuration data to update
        user: Admin user dependency for authentication (default: Depends(get_admin_user))
    
    Returns:
        dict: Updated pipeline valve configuration data returned from the API
    
    Raises:
        HTTPException: If there's an error connecting to the API or updating the pipeline valves
            - status_code: HTTP status code from the response or 404 if no response
            - detail: Specific error message from the API or a generic "Pipeline not found" message
    """
    r = None
    try:
        url = request.app.state.config.OPENAI_API_BASE_URLS[urlIdx]
        key = request.app.state.config.OPENAI_API_KEYS[urlIdx]

        r = requests.post(
            f"{url}/{pipeline_id}/valves/update",
            headers={"Authorization": f"Bearer {key}"},
            json={**form_data},
        )

        r.raise_for_status()
        data = r.json()

        return {**data}
    except Exception as e:
        # Handle connection error here
        print(f"Connection error: {e}")

        detail = None

        if r is not None:
            try:
                res = r.json()
                if "detail" in res:
                    detail = res["detail"]
            except Exception:
                pass

        raise HTTPException(
            status_code=(r.status_code if r is not None else status.HTTP_404_NOT_FOUND),
            detail=detail if detail else "Pipeline not found",
        )
