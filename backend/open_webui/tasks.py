# tasks.py
import asyncio
from typing import Dict
from uuid import uuid4

# A dictionary to keep track of active tasks
tasks: Dict[str, asyncio.Task] = {}


def cleanup_task(task_id: str):
    """
    Remove a completed or canceled task from the global tasks dictionary.
    
    This method safely removes a task from the tasks dictionary using the provided task ID. If the task ID does not exist, no error is raised due to the use of the default `None` value.
    
    Args:
        task_id (str): The unique identifier of the task to be removed from the tasks dictionary.
    """
    tasks.pop(task_id, None)  # Remove the task if it exists


def create_task(coroutine):
    """
    Create a new asyncio task with a unique identifier and manage its lifecycle.
    
    This function generates a unique task ID, creates an asyncio task from the provided coroutine,
    and registers the task in the global tasks dictionary. A cleanup callback is automatically
    added to remove the task when it completes.
    
    Parameters:
        coroutine (Coroutine): An asynchronous coroutine to be executed as a task.
    
    Returns:
        tuple: A tuple containing:
            - task_id (str): A unique identifier for the created task
            - task (asyncio.Task): The created asyncio task object
    
    Example:
        async def example_coroutine():
            await asyncio.sleep(1)
            return "Task completed"
    
        task_id, task = create_task(example_coroutine())
    """
    task_id = str(uuid4())  # Generate a unique ID for the task
    task = asyncio.create_task(coroutine)  # Create the task

    # Add a done callback for cleanup
    task.add_done_callback(lambda t: cleanup_task(task_id))

    tasks[task_id] = task
    return task_id, task


def get_task(task_id: str):
    """
    Retrieve a task from the global tasks dictionary by its unique identifier.
    
    Parameters:
        task_id (str): The unique identifier of the task to retrieve.
    
    Returns:
        asyncio.Task or None: The task associated with the given task_id, or None if no task is found.
    """
    return tasks.get(task_id)


def list_tasks():
    """
    List all currently active task IDs.
    
    Returns:
        list: A list of unique task identifiers (strings) for all currently active tasks in the tasks dictionary.
    
    Example:
        active_tasks = list_tasks()
        print(f"Currently active tasks: {active_tasks}")
    """
    return list(tasks.keys())


async def stop_task(task_id: str):
    """
    Asynchronously stop a running task by its unique identifier.
    
    Attempts to cancel a specific task and remove it from the global task registry. 
    Provides detailed status information about the task cancellation process.
    
    Args:
        task_id (str): Unique identifier of the task to be stopped.
    
    Returns:
        dict: A status dictionary containing:
            - 'status' (bool): Indicates whether task cancellation was successful
            - 'message' (str): Descriptive message about the task cancellation result
    
    Raises:
        ValueError: If no task is found with the provided task_id
    
    Behavior:
        - Retrieves task from global tasks dictionary
        - Requests task cancellation
        - Waits for task to handle cancellation
        - Removes task from dictionary if successfully canceled
        - Returns status indicating success or failure of cancellation
    
    Example:
        result = await stop_task('abc123')
        # Possible results:
        # {'status': True, 'message': 'Task abc123 successfully stopped.'}
        # {'status': False, 'message': 'Failed to stop task abc123.'}
    """
    task = tasks.get(task_id)
    if not task:
        raise ValueError(f"Task with ID {task_id} not found.")

    task.cancel()  # Request task cancellation
    try:
        await task  # Wait for the task to handle the cancellation
    except asyncio.CancelledError:
        # Task successfully canceled
        tasks.pop(task_id, None)  # Remove it from the dictionary
        return {"status": True, "message": f"Task {task_id} successfully stopped."}

    return {"status": False, "message": f"Failed to stop task {task_id}."}
