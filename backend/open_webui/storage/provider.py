import os
import shutil
import json
from abc import ABC, abstractmethod
from typing import BinaryIO, Tuple

import boto3
from botocore.exceptions import ClientError
from open_webui.config import (
    S3_ACCESS_KEY_ID,
    S3_BUCKET_NAME,
    S3_ENDPOINT_URL,
    S3_REGION_NAME,
    S3_SECRET_ACCESS_KEY,
    GCS_BUCKET_NAME,
    GOOGLE_APPLICATION_CREDENTIALS_JSON,
    STORAGE_PROVIDER,
    UPLOAD_DIR,
)
from google.cloud import storage
from google.cloud.exceptions import GoogleCloudError, NotFound
from open_webui.constants import ERROR_MESSAGES


class StorageProvider(ABC):
    @abstractmethod
    def get_file(self, file_path: str) -> str:
        """
        Retrieve a file from the storage backend.
        
        This method defines the contract for obtaining a file from the storage provider.
        Implementations should locate the file using the specified path and return a string
        representing the local path to the file. Depending on the storage provider (local, S3,
        or GCS), this may involve different retrieval mechanisms and error handling.
        
        Parameters:
            file_path (str): The path or identifier of the file to be retrieved.
        
        Returns:
            str: The local file path where the file has been stored or is accessible.
        
        Raises:
            Exception: If the file retrieval operation fails.
        """
        pass

    @abstractmethod
    def upload_file(self, file: BinaryIO, filename: str) -> Tuple[bytes, str]:
        """
        Uploads a file to the storage system.
        
        This method uploads the binary content of the provided file to the configured storage provider
        using the specified filename. The operation typically involves reading the file's content and
        storing it at a target location, which may vary depending on the storage backend (e.g., local
        filesystem, Amazon S3, or Google Cloud Storage). Implementations should return a tuple containing
        the file's bytes and the final storage path or URL.
        
        Parameters:
            file (BinaryIO): A binary stream representing the file to be uploaded.
            filename (str): The name to assign to the file in the storage system.
        
        Returns:
            Tuple[bytes, str]: A tuple where the first element is the file's byte content and the second element
            is the path or URL where the file was stored.
        
        Raises:
            ValueError: If the provided file is empty (applicable in some implementations).
            Exception: If the upload operation fails due to an underlying storage error.
        """
        pass

    @abstractmethod
    def delete_all_files(self) -> None:
        """
        Delete all files from the storage backend.
        
        This method is intended to remove every file stored in the provider's storage medium. Subclasses should override this method to implement the appropriate deletion logic—whether that involves clearing a local directory, removing objects from an Amazon S3 bucket, or deleting files from a Google Cloud Storage bucket. An exception may be raised if the deletion process encounters an error.
        
        Returns:
            None
        
        Raises:
            Exception: If the deletion operation fails.
        """
        pass

    @abstractmethod
    def delete_file(self, file_path: str) -> None:
        """
        Delete a file from the storage.
        
        This method should remove the file located at the given file path from the storage system.
        Concrete implementations are expected to override this method to perform any necessary operations
        required for deleting the file from the underlying storage backend.
        
        Parameters:
            file_path (str): The path of the file to delete.
        
        Raises:
            Exception: If the deletion operation fails. Specific implementations may raise more detailed exceptions.
        """
        pass


class LocalStorageProvider(StorageProvider):
    @staticmethod
    def upload_file(file: BinaryIO, filename: str) -> Tuple[bytes, str]:
        """
        Uploads a file to the local storage directory.
        
        This function reads the entire contents from the provided binary file object and writes it
        to a new file in the designated upload directory, using the specified filename. If the file
        contents are empty, the function raises a ValueError.
        
        Parameters:
            file (BinaryIO): A binary file-like object containing the data to be uploaded.
            filename (str): The name to assign to the uploaded file.
        
        Returns:
            Tuple[bytes, str]: A tuple where the first element is the file's binary contents and the second element
            is the file path where the file was saved.
        
        Raises:
            ValueError: If the file's contents are empty.
        """
        contents = file.read()
        if not contents:
            raise ValueError(ERROR_MESSAGES.EMPTY_CONTENT)
        file_path = f"{UPLOAD_DIR}/{filename}"
        with open(file_path, "wb") as f:
            f.write(contents)
        return contents, file_path

    @staticmethod
    def get_file(file_path: str) -> str:
        """
        Retrieve the local file path for the requested file.
        
        This function simulates downloading from local storage by returning the provided file path. It does not perform any file I/O operations, but simply acts as a placeholder to adhere to the storage provider interface for local file access.
        
        Parameters:
            file_path (str): The path to the file in local storage, which can be a relative or absolute path.
        
        Returns:
            str: The same file path that was provided, representing the location of the file in local storage.
        
        Example:
            >>> get_file('/uploads/example.txt')
            '/uploads/example.txt'
        """
        return file_path

    @staticmethod
    def delete_file(file_path: str) -> None:
        """
        Deletes a file from local storage.
        
        This function extracts the filename from the provided file path, constructs the full path using the designated upload directory, and attempts to remove the file. If the file does not exist at the expected location, an informational message is printed.
        
        Parameters:
            file_path (str): The input file path or identifier. Only the basename (filename) is used to construct the full deletion path.
        
        Returns:
            None
        
        Side Effects:
            - Deletes the file from the local storage if it exists.
            - Prints a message if the file is not found.
        """
        filename = file_path.split("/")[-1]
        file_path = f"{UPLOAD_DIR}/{filename}"
        if os.path.isfile(file_path):
            os.remove(file_path)
        else:
            print(f"File {file_path} not found in local storage.")

    @staticmethod
    def delete_all_files() -> None:
        """
        Delete all files and directories from the local storage upload directory.
        
        This function checks if the upload directory (defined by the global variable UPLOAD_DIR) exists.
        If the directory exists, it iterates over all items within UPLOAD_DIR and deletes them:
        - Regular files and symbolic links are removed using os.unlink.
        - Directories are removed recursively using shutil.rmtree.
        Any exception raised during deletion is caught, and an error message is printed to the console.
        If the upload directory does not exist, a message is printed indicating that the directory was not found.
        
        Returns:
            None
        """
        if os.path.exists(UPLOAD_DIR):
            for filename in os.listdir(UPLOAD_DIR):
                file_path = os.path.join(UPLOAD_DIR, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)  # Remove the file or link
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)  # Remove the directory
                except Exception as e:
                    print(f"Failed to delete {file_path}. Reason: {e}")
        else:
            print(f"Directory {UPLOAD_DIR} not found in local storage.")


class S3StorageProvider(StorageProvider):
    def __init__(self):
        """
        Initialize the S3StorageProvider instance.
        
        This constructor creates a boto3 S3 client using configuration constants for the region name,
        endpoint URL, AWS access key ID, and AWS secret access key. It also sets the S3 bucket name
        for subsequent file operations.
        
        Attributes:
            s3_client (botocore.client.S3): The S3 client used to interact with the Amazon S3 service.
            bucket_name (str): The name of the S3 bucket for file storage operations.
        """
        self.s3_client = boto3.client(
            "s3",
            region_name=S3_REGION_NAME,
            endpoint_url=S3_ENDPOINT_URL,
            aws_access_key_id=S3_ACCESS_KEY_ID,
            aws_secret_access_key=S3_SECRET_ACCESS_KEY,
        )
        self.bucket_name = S3_BUCKET_NAME

    def upload_file(self, file: BinaryIO, filename: str) -> Tuple[bytes, str]:
        """
        Uploads a file to Amazon S3 after first storing it locally.
        
        This method uses the LocalStorageProvider to save the provided binary file locally and then uploads the file to the specified S3 bucket using the S3 client. On successful upload, the method reads the file content from the local storage and returns a tuple containing the binary data and the corresponding S3 URL. The S3 URL is formatted as "s3://<bucket_name>/<filename>".
        
        Parameters:
            file (BinaryIO): A binary file-like object to be uploaded.
            filename (str): The name of the file to be uploaded. This name is used as the key in the S3 bucket.
        
        Returns:
            Tuple[bytes, str]: A tuple where the first element is the binary content of the file (read from local storage) and the second element is the S3 URL of the uploaded file.
        
        Raises:
            RuntimeError: If an error occurs during the S3 upload operation, a RuntimeError is raised with details of the ClientError.
        """
        _, file_path = LocalStorageProvider.upload_file(file, filename)
        try:
            self.s3_client.upload_file(file_path, self.bucket_name, filename)
            return (
                open(file_path, "rb").read(),
                "s3://" + self.bucket_name + "/" + filename,
            )
        except ClientError as e:
            raise RuntimeError(f"Error uploading file to S3: {e}")

    def get_file(self, file_path: str) -> str:
        """
        Download a file from Amazon S3 and save it to the local upload directory.
        
        This method extracts the bucket name and object key from the given S3 file path, downloads the file using the S3 client, and stores it locally under the UPLOAD_DIR directory using the object key as the filename.
        
        Parameters:
            file_path (str): The S3 file path in the format "s3://<bucket_name>/<object_key>".
        
        Returns:
            str: The local file path where the file has been downloaded.
        
        Raises:
            RuntimeError: If an error occurs during the download process (e.g., when a ClientError is raised by the S3 client).
        """
        try:
            bucket_name, key = file_path.split("//")[1].split("/")
            local_file_path = f"{UPLOAD_DIR}/{key}"
            self.s3_client.download_file(bucket_name, key, local_file_path)
            return local_file_path
        except ClientError as e:
            raise RuntimeError(f"Error downloading file from S3: {e}")

    def delete_file(self, file_path: str) -> None:
        """
        Delete a file from Amazon S3 storage and remove it from local storage.
        
        This method extracts the filename from the given file_path and attempts to delete
        the corresponding object from the S3 bucket using the S3 client. If the deletion
        from S3 fails, a RuntimeError is raised with the underlying error message. The file
        is then deleted from local storage by calling LocalStorageProvider.delete_file regardless
        of the S3 deletion outcome.
        
        Parameters:
            file_path (str): The path of the file to delete. Only the basename (extracted from the path)
                             is used to identify the file in the S3 bucket.
        
        Raises:
            RuntimeError: If an error occurs while deleting the file from S3.
        """
        filename = file_path.split("/")[-1]
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=filename)
        except ClientError as e:
            raise RuntimeError(f"Error deleting file from S3: {e}")

        # Always delete from local storage
        LocalStorageProvider.delete_file(file_path)

    def delete_all_files(self) -> None:
        """
        Delete all files from the S3 bucket and local storage.
        
        This method retrieves and deletes every object in the S3 bucket specified by
        `self.bucket_name`. It lists all objects using the S3 client's `list_objects_v2`
        method and deletes each object via `delete_object`. If a ClientError occurs during
        this process, a RuntimeError is raised with the corresponding error message.
        Regardless of the outcome of the S3 deletion, the method also ensures that all
        files in local storage are deleted by invoking `LocalStorageProvider.delete_all_files()`.
        
        Raises:
            RuntimeError: If an error occurs while deleting files from S3 storage.
        
        Returns:
            None
        """
        try:
            response = self.s3_client.list_objects_v2(Bucket=self.bucket_name)
            if "Contents" in response:
                for content in response["Contents"]:
                    self.s3_client.delete_object(
                        Bucket=self.bucket_name, Key=content["Key"]
                    )
        except ClientError as e:
            raise RuntimeError(f"Error deleting all files from S3: {e}")

        # Always delete from local storage
        LocalStorageProvider.delete_all_files()


class GCSStorageProvider(StorageProvider):
    def __init__(self):
        """
        Initialize a GCSStorageProvider instance.
        
        This constructor sets up the Google Cloud Storage client and associates it with a specific bucket.
        If a JSON-formatted credentials string is provided via GOOGLE_APPLICATION_CREDENTIALS_JSON, the 
        client is initialized using those credentials. Otherwise, the client defaults to using credentials 
        sourced from the environment (which may be user credentials locally or metadata server credentials 
        on Compute Engine instances). The bucket corresponding to GCS_BUCKET_NAME is then retrieved and 
        stored.
        
        Attributes:
            bucket_name (str): The name of the Google Cloud Storage bucket.
            gcs_client (storage.Client): The client used to interact with Google Cloud Storage.
            bucket (Bucket): The bucket instance associated with the specified bucket name.
        """
        self.bucket_name = GCS_BUCKET_NAME

        if GOOGLE_APPLICATION_CREDENTIALS_JSON:
            self.gcs_client = storage.Client.from_service_account_info(
                info=json.loads(GOOGLE_APPLICATION_CREDENTIALS_JSON)
            )
        else:
            # if no credentials json is provided, credentials will be picked up from the environment
            # if running on local environment, credentials would be user credentials
            # if running on a Compute Engine instance, credentials would be from Google Metadata server
            self.gcs_client = storage.Client()
        self.bucket = self.gcs_client.bucket(GCS_BUCKET_NAME)

    def upload_file(self, file: BinaryIO, filename: str) -> Tuple[bytes, str]:
        """
        Uploads a file to Google Cloud Storage (GCS) after saving it locally.
        
        This method first delegates the file writing process to the LocalStorageProvider,
        which saves the file locally and returns its contents along with the local file path.
        It then uploads the locally saved file to a GCS bucket by creating a blob with the
        given filename. Upon successful upload, it returns the file's contents and the
        GCS URI in the format "gs://<bucket_name>/<filename>".
        
        Parameters:
            file (BinaryIO): A binary stream representing the file to be uploaded.
            filename (str): The name of the file to use for storage and access.
        
        Returns:
            Tuple[bytes, str]: A tuple where the first element is the file's contents as bytes,
                and the second element is the GCS URI of the uploaded file.
        
        Raises:
            RuntimeError: If an error occurs during the upload process to GCS.
        """
        contents, file_path = LocalStorageProvider.upload_file(file, filename)
        try:
            blob = self.bucket.blob(filename)
            blob.upload_from_filename(file_path)
            return contents, "gs://" + self.bucket_name + "/" + filename
        except GoogleCloudError as e:
            raise RuntimeError(f"Error uploading file to GCS: {e}")

    def get_file(self, file_path: str) -> str:
        """
        Downloads a file from Google Cloud Storage (GCS) and saves it to a local directory.
        
        This method extracts the filename from the provided GCS file path by removing the "gs://" prefix
        and splitting the remainder using "/" as the delimiter. It then constructs a local file path using
        the UPLOAD_DIR constant and downloads the corresponding blob from the GCS bucket to this location.
        
        Parameters:
            file_path (str): The full GCS file path (e.g., "gs://bucket_name/filename").
        
        Returns:
            str: The local file path where the file has been successfully downloaded.
        
        Raises:
            RuntimeError: If the file is not found in the GCS bucket or if an error occurs during download.
        """
        try:
            filename = file_path.removeprefix("gs://").split("/")[1]
            local_file_path = f"{UPLOAD_DIR}/{filename}"
            blob = self.bucket.get_blob(filename)
            blob.download_to_filename(local_file_path)

            return local_file_path
        except NotFound as e:
            raise RuntimeError(f"Error downloading file from GCS: {e}")

    def delete_file(self, file_path: str) -> None:
        """
        Delete a file from Google Cloud Storage (GCS) and remove its local copy.
        
        This method attempts to delete the specified file from the GCS bucket. The expected
        file_path should be a valid GCS URL (e.g., "gs://bucket-name/filename"). The deletion process:
        1. Parses the file name from the provided GCS URL.
        2. Retrieves the corresponding blob from the GCS bucket and attempts to delete it.
        3. If the blob is not found, a RuntimeError is raised with the underlying error message.
        4. Regardless of the outcome of the GCS deletion, the method proceeds to delete the local
           copy of the file via the LocalStorageProvider.
        
        Parameters:
            file_path (str): The full GCS URL of the file to be deleted.
        
        Raises:
            RuntimeError: If the file deletion from GCS fails (e.g., the file is not found).
        """
        try:
            filename = file_path.removeprefix("gs://").split("/")[1]
            blob = self.bucket.get_blob(filename)
            blob.delete()
        except NotFound as e:
            raise RuntimeError(f"Error deleting file from GCS: {e}")

        # Always delete from local storage
        LocalStorageProvider.delete_file(file_path)

    def delete_all_files(self) -> None:
        """
        Deletes all files from the Google Cloud Storage (GCS) bucket and ensures local storage is also cleared.
        
        This method retrieves all blobs in the configured GCS bucket and attempts to delete each one. If a blob deletion results in a NotFound error, the method raises a RuntimeError with the error details. Regardless of any issues encountered during the GCS deletion process, local storage cleanup is always performed by invoking LocalStorageProvider.delete_all_files().
        
        Raises:
            RuntimeError: If one or more blobs cannot be deleted from the GCS bucket due to a NotFound error.
        """
        try:
            blobs = self.bucket.list_blobs()

            for blob in blobs:
                blob.delete()

        except NotFound as e:
            raise RuntimeError(f"Error deleting all files from GCS: {e}")

        # Always delete from local storage
        LocalStorageProvider.delete_all_files()


def get_storage_provider(storage_provider: str):
    """
    Return an instance of a storage provider based on the specified type.
    
    This function initializes and returns a concrete storage provider instance corresponding to the
    requested storage type. Supported values for the provider are:
      - "local": Returns a LocalStorageProvider instance for local file storage.
      - "s3": Returns a S3StorageProvider instance for interacting with Amazon S3.
      - "gcs": Returns a GCSStorageProvider instance for interacting with Google Cloud Storage.
    
    Parameters:
        storage_provider (str): The type of storage provider requested. Valid options are "local", "s3", and "gcs".
    
    Returns:
        An instance of the corresponding storage provider.
    
    Raises:
        RuntimeError: If an unsupported storage provider type is specified.
    """
    if storage_provider == "local":
        Storage = LocalStorageProvider()
    elif storage_provider == "s3":
        Storage = S3StorageProvider()
    elif storage_provider == "gcs":
        Storage = GCSStorageProvider()
    else:
        raise RuntimeError(f"Unsupported storage provider: {storage_provider}")
    return Storage


Storage = get_storage_provider(STORAGE_PROVIDER)
