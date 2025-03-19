import base64
import os
import random
from pathlib import Path

import typer
import uvicorn
from typing import Optional
from typing_extensions import Annotated

app = typer.Typer()

KEY_FILE = Path.cwd() / ".webui_secret_key"


def version_callback(value: bool):
    """
    Callback function to print the current Open WebUI version and exit the application.
    
    This function is designed to be used as a Typer callback for the --version option. When the provided value is True,
    it imports the VERSION from the open_webui.env module, prints the version information using typer.echo, and then exits
    the application by raising a typer.Exit exception.
    
    Parameters:
        value (bool): A flag indicating whether to display the version. If True, the version is printed and the application exits.
    
    Raises:
        typer.Exit: Always raised when value is True to terminate the application after displaying the version.
    """
    if value:
        from open_webui.env import VERSION

        typer.echo(f"Open WebUI version: {VERSION}")
        raise typer.Exit()


@app.command()
def main(
    version: Annotated[
        Optional[bool], typer.Option("--version", callback=version_callback)
    ] = None,
):
    """
    Main entry point for the CLI application.
    
    This command acts as the central point of execution for the Typer-based CLI. When the 
    optional "--version" flag is provided, the associated callback, `version_callback`, is 
    invoked to print the current version of the application and exit. If the flag is not set, 
    this function can be extended to perform additional CLI operations.
    
    Parameters:
        version (Optional[bool]): A flag that, when set to True via the "--version" option, triggers 
            the version output logic. Defaults to None.
    
    Returns:
        None
    """
    pass


@app.command()
def serve(
    host: str = "0.0.0.0",
    port: int = 8080,
):
    """
    Start the web server with proper configuration and environment variables.
    
    This function initializes the web server and prepares the necessary environment to run the application.
    It performs the following actions:
    - Sets the "FROM_INIT_PY" environment variable to "true".
    - Checks if the "WEBUI_SECRET_KEY" environment variable is set. If not, it attempts to load the key from a file
      defined by KEY_FILE. If the file does not exist, a new 12-byte random key is generated, encoded in base64,
      and saved to the file.
    - If the "USE_CUDA_DOCKER" environment variable is set to "true", it appends specific directories to the
      LD_LIBRARY_PATH to include CUDA-related libraries, then verifies CUDA availability using the torch library.
      If an error occurs during this check, the function resets "USE_CUDA_DOCKER" to "false" and restores the original
      LD_LIBRARY_PATH.
    - Finally, it imports the main web application and starts the uvicorn server with the specified host and port.
    
    Parameters:
        host (str): Hostname or IP address on which the server will run (default "0.0.0.0").
        port (int): Port number on which the server will listen (default 8080).
    
    Returns:
        None
    
    Side Effects:
        - Modifies several environment variables (FROM_INIT_PY, WEBUI_SECRET_KEY, USE_CUDA_DOCKER, LD_LIBRARY_PATH).
        - May create and write a new secret key file if it does not exist.
        - Initiates a blocking call to start the uvicorn web server.
    
    Exceptions:
        - Exceptions raised during the CUDA check are caught internally, and the environment is reset accordingly.
        - Other exceptions (e.g., import errors or runtime errors during server startup) are not handled within this function.
    """
    os.environ["FROM_INIT_PY"] = "true"
    if os.getenv("WEBUI_SECRET_KEY") is None:
        typer.echo(
            "Loading WEBUI_SECRET_KEY from file, not provided as an environment variable."
        )
        if not KEY_FILE.exists():
            typer.echo(f"Generating a new secret key and saving it to {KEY_FILE}")
            KEY_FILE.write_bytes(base64.b64encode(random.randbytes(12)))
        typer.echo(f"Loading WEBUI_SECRET_KEY from {KEY_FILE}")
        os.environ["WEBUI_SECRET_KEY"] = KEY_FILE.read_text()

    if os.getenv("USE_CUDA_DOCKER", "false") == "true":
        typer.echo(
            "CUDA is enabled, appending LD_LIBRARY_PATH to include torch/cudnn & cublas libraries."
        )
        LD_LIBRARY_PATH = os.getenv("LD_LIBRARY_PATH", "").split(":")
        os.environ["LD_LIBRARY_PATH"] = ":".join(
            LD_LIBRARY_PATH
            + [
                "/usr/local/lib/python3.11/site-packages/torch/lib",
                "/usr/local/lib/python3.11/site-packages/nvidia/cudnn/lib",
            ]
        )
        try:
            import torch

            assert torch.cuda.is_available(), "CUDA not available"
            typer.echo("CUDA seems to be working")
        except Exception as e:
            typer.echo(
                "Error when testing CUDA but USE_CUDA_DOCKER is true. "
                "Resetting USE_CUDA_DOCKER to false and removing "
                f"LD_LIBRARY_PATH modifications: {e}"
            )
            os.environ["USE_CUDA_DOCKER"] = "false"
            os.environ["LD_LIBRARY_PATH"] = ":".join(LD_LIBRARY_PATH)

    import open_webui.main  # we need set environment variables before importing main

    uvicorn.run(open_webui.main.app, host=host, port=port, forwarded_allow_ips="*")


@app.command()
def dev(
    host: str = "0.0.0.0",
    port: int = 8080,
    reload: bool = True,
):
    uvicorn.run(
        "open_webui.main:app",
        host=host,
        port=port,
        reload=reload,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    app()
