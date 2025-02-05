import io
import os
import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws
from open_webui.storage import provider
from gcp_storage_emulator.server import create_server
from google.cloud import storage


def mock_upload_dir(monkeypatch, tmp_path):
    """
    Fixture to create a temporary uploads directory and monkey-patch the provider module's UPLOAD_DIR attribute.
    
    This fixture creates a new directory named "uploads" within the temporary path provided by pytest's tmp_path fixture. It then uses the monkeypatch fixture to update the UPLOAD_DIR attribute of the provider module to point to this new directory, ensuring that file operations during tests are isolated to a temporary location.
    
    Parameters:
        monkeypatch (pytest.MonkeyPatch): A pytest fixture used for safely patching and restoring environment attributes.
        tmp_path (pathlib.Path): A temporary directory path provided by pytest for file operations.
    
    Returns:
        pathlib.Path: The path object representing the created "uploads" directory.
    """
    directory = tmp_path / "uploads"
    directory.mkdir()
    monkeypatch.setattr(provider, "UPLOAD_DIR", str(directory))
    return directory


def test_imports():
    """
    Test that all required storage provider classes and attributes are accessible from the provider module.
    
    This test verifies the presence of:
      - StorageProvider
      - LocalStorageProvider
      - S3StorageProvider
      - GCSStorageProvider
      - Storage
    
    Successful imports ensure that the module's public API is correctly exposed.
    """
    provider.StorageProvider
    provider.LocalStorageProvider
    provider.S3StorageProvider
    provider.GCSStorageProvider
    provider.Storage


def test_get_storage_provider():
    Storage = provider.get_storage_provider("local")
    assert isinstance(Storage, provider.LocalStorageProvider)
    Storage = provider.get_storage_provider("s3")
    assert isinstance(Storage, provider.S3StorageProvider)
    Storage = provider.get_storage_provider("gcs")
    assert isinstance(Storage, provider.GCSStorageProvider)
    with pytest.raises(RuntimeError):
        provider.get_storage_provider("invalid")


def test_class_instantiation():
    """
    Test the instantiation behavior of storage provider classes.
    
    This test verifies that:
    - Instantiating the abstract StorageProvider class directly raises a TypeError.
    - Instantiating a subclass of StorageProvider without necessary implementations (using a dummy subclass) also raises a TypeError.
    - Concrete implementations (LocalStorageProvider, S3StorageProvider, and GCSStorageProvider) can be instantiated without errors.
    
    Exceptions:
        TypeError: Raised when attempting to instantiate the abstract StorageProvider or an incomplete subclass.
    """
    with pytest.raises(TypeError):
        provider.StorageProvider()
    with pytest.raises(TypeError):

        class Test(provider.StorageProvider):
            pass

        Test()
    provider.LocalStorageProvider()
    provider.S3StorageProvider()
    provider.GCSStorageProvider()


class TestLocalStorageProvider:
    Storage = provider.LocalStorageProvider()
    file_content = b"test content"
    file_bytesio = io.BytesIO(file_content)
    filename = "test.txt"
    filename_extra = "test_exyta.txt"
    file_bytesio_empty = io.BytesIO()

    def test_upload_file(self, monkeypatch, tmp_path):
        """
        Test uploading a file using the Storage provider’s upload_file method.
        
        This test verifies that:
        - The file is saved in the correct upload directory.
        - The file's content on disk matches the expected file content.
        - The returned content and file path are correct.
        - Attempting to upload an empty file raises a ValueError.
        
        Parameters:
            monkeypatch: Pytest fixture used to override settings, such as the upload directory.
            tmp_path: Pytest fixture providing a temporary directory path for file operations.
        """
        upload_dir = mock_upload_dir(monkeypatch, tmp_path)
        contents, file_path = self.Storage.upload_file(self.file_bytesio, self.filename)
        assert (upload_dir / self.filename).exists()
        assert (upload_dir / self.filename).read_bytes() == self.file_content
        assert contents == self.file_content
        assert file_path == str(upload_dir / self.filename)
        with pytest.raises(ValueError):
            self.Storage.upload_file(self.file_bytesio_empty, self.filename)

    def test_get_file(self, monkeypatch, tmp_path):
        upload_dir = mock_upload_dir(monkeypatch, tmp_path)
        file_path = str(upload_dir / self.filename)
        file_path_return = self.Storage.get_file(file_path)
        assert file_path == file_path_return

    def test_delete_file(self, monkeypatch, tmp_path):
        """
        Test deletion of a file from local storage.
        
        This test uses a temporary upload directory created via the `mock_upload_dir` fixture to simulate the local storage environment.
        It writes a file with a predefined filename and content, confirms the file's existence, then deletes the file using the provider's
        `delete_file` method and asserts that the file has been successfully removed.
        
        Parameters:
            self: Instance of the test class containing attributes like `filename`, `file_content`, and `Storage`.
            monkeypatch: pytest fixture used for modifying and patching parts of the system during testing.
            tmp_path: pytest fixture that provides a temporary directory unique to the test invocation.
        
        Raises:
            AssertionError: If the file does not exist when expected or still exists after the deletion attempt.
        """
        upload_dir = mock_upload_dir(monkeypatch, tmp_path)
        (upload_dir / self.filename).write_bytes(self.file_content)
        assert (upload_dir / self.filename).exists()
        file_path = str(upload_dir / self.filename)
        self.Storage.delete_file(file_path)
        assert not (upload_dir / self.filename).exists()

    def test_delete_all_files(self, monkeypatch, tmp_path):
        """
        Test deletion of all files from the upload directory.
        
        This test verifies that the Storage provider's delete_all_files() method successfully removes all files from the upload directory. It first sets up a temporary upload directory using the mock_upload_dir fixture, writes two files (self.filename and self.filename_extra) with predetermined content, then calls delete_all_files() and asserts that both files have been removed.
        
        Parameters:
            monkeypatch: Pytest's monkeypatch fixture for temporarily modifying attributes during tests.
            tmp_path: A pathlib.Path object provided by pytest representing a temporary directory for file operations.
        """
        upload_dir = mock_upload_dir(monkeypatch, tmp_path)
        (upload_dir / self.filename).write_bytes(self.file_content)
        (upload_dir / self.filename_extra).write_bytes(self.file_content)
        self.Storage.delete_all_files()
        assert not (upload_dir / self.filename).exists()
        assert not (upload_dir / self.filename_extra).exists()


@mock_aws
class TestS3StorageProvider:

    def __init__(self):
        """
        Initializes the test class for the S3 storage provider.
        
        This constructor sets up required attributes for testing S3 storage interactions. It creates an instance of S3StorageProvider from the provider module and assigns a fixed bucket name ("my-bucket"). Additionally, it initializes an S3 client using boto3 for the "us-east-1" region and sets up test-specific attributes: a byte string for file content, two filename strings for testing file operations, and an empty BytesIO object to simulate empty file uploads. Finally, it calls the superclass initializer to complete the setup.
        """
        self.Storage = provider.S3StorageProvider()
        self.Storage.bucket_name = "my-bucket"
        self.s3_client = boto3.resource("s3", region_name="us-east-1")
        self.file_content = b"test content"
        self.filename = "test.txt"
        self.filename_extra = "test_exyta.txt"
        self.file_bytesio_empty = io.BytesIO()
        super().__init__()

    def test_upload_file(self, monkeypatch, tmp_path):
        """
        Test uploading a file to S3 and local storage.
        
        This test verifies the behavior of the upload_file method in a cloud storage provider by performing the following checks:
        - Ensures that uploading a file without an existing S3 bucket raises an Exception.
        - Creates an S3 bucket and successfully uploads a file, then validates that:
            - The file content stored in S3 matches the expected data.
            - A corresponding local copy is saved in the designated upload directory with matching content.
            - The method returns both the file content and a correctly formatted S3 file path.
        - Verifies that attempting to upload an empty file raises a ValueError.
        
        Parameters:
            monkeypatch (MonkeyPatch): Fixture for patching attributes and functions during the test.
            tmp_path (Path): Temporary directory fixture to simulate a local upload directory.
        
        Raises:
            Exception: When uploading without an existing S3 bucket.
            ValueError: When attempting to upload an empty file.
        """
        upload_dir = mock_upload_dir(monkeypatch, tmp_path)
        # S3 checks
        with pytest.raises(Exception):
            self.Storage.upload_file(io.BytesIO(self.file_content), self.filename)
        self.s3_client.create_bucket(Bucket=self.Storage.bucket_name)
        contents, s3_file_path = self.Storage.upload_file(
            io.BytesIO(self.file_content), self.filename
        )
        object = self.s3_client.Object(self.Storage.bucket_name, self.filename)
        assert self.file_content == object.get()["Body"].read()
        # local checks
        assert (upload_dir / self.filename).exists()
        assert (upload_dir / self.filename).read_bytes() == self.file_content
        assert contents == self.file_content
        assert s3_file_path == "s3://" + self.Storage.bucket_name + "/" + self.filename
        with pytest.raises(ValueError):
            self.Storage.upload_file(self.file_bytesio_empty, self.filename)

    def test_get_file(self, monkeypatch, tmp_path):
        """
        Test retrieval of an uploaded file from S3 storage.
        
        This test verifies that after uploading a file via the Storage provider, the get_file method returns the correct local file path and that the file exists in the temporary upload directory.
        
        Steps:
            1. Set up the temporary upload directory using monkeypatch and tmp_path.
            2. Create the required S3 bucket.
            3. Upload a file using the Storage provider's upload_file method.
            4. Retrieve the file path using the get_file method.
            5. Assert that the returned file path matches the expected path.
            6. Assert that the file exists in the temporary upload directory.
        
        Parameters:
            monkeypatch: pytest fixture for dynamic attribute patching.
            tmp_path: pytest fixture providing a temporary directory for file operations.
        
        Returns:
            None
        
        Raises:
            AssertionError: If the retrieved file path does not match the expected path or the file does not exist.
        """
        upload_dir = mock_upload_dir(monkeypatch, tmp_path)
        self.s3_client.create_bucket(Bucket=self.Storage.bucket_name)
        contents, s3_file_path = self.Storage.upload_file(
            io.BytesIO(self.file_content), self.filename
        )
        file_path = self.Storage.get_file(s3_file_path)
        assert file_path == str(upload_dir / self.filename)
        assert (upload_dir / self.filename).exists()

    def test_delete_file(self, monkeypatch, tmp_path):
        """
        Test deletion of an S3 file from both local storage and S3.
        
        This test verifies that after uploading a file using the S3 storage provider, deleting the file properly removes it from the local upload directory as well as from the S3 bucket. The test performs the following steps:
        1. Sets up a temporary upload directory via monkeypatch.
        2. Creates the S3 bucket.
        3. Uploads a file using the storage provider.
        4. Asserts that the file exists locally after upload.
        5. Deletes the file using the provider's delete_file method.
        6. Asserts that the file is removed from the local directory.
        7. Attempts to load the deleted S3 file, expecting a ClientError with error code "404" and message "Not Found".
        
        Parameters:
            monkeypatch: pytest's fixture for monkey-patching attributes and methods.
            tmp_path (Path): A temporary directory path provided by pytest for file system operations.
        
        Raises:
            ClientError: Raised when attempting to load the S3 object after deletion, confirming that the file has been removed.
        """
        upload_dir = mock_upload_dir(monkeypatch, tmp_path)
        self.s3_client.create_bucket(Bucket=self.Storage.bucket_name)
        contents, s3_file_path = self.Storage.upload_file(
            io.BytesIO(self.file_content), self.filename
        )
        assert (upload_dir / self.filename).exists()
        self.Storage.delete_file(s3_file_path)
        assert not (upload_dir / self.filename).exists()
        with pytest.raises(ClientError) as exc:
            self.s3_client.Object(self.Storage.bucket_name, self.filename).load()
        error = exc.value.response["Error"]
        assert error["Code"] == "404"
        assert error["Message"] == "Not Found"

    def test_delete_all_files(self, monkeypatch, tmp_path):
        upload_dir = mock_upload_dir(monkeypatch, tmp_path)
        # create 2 files
        self.s3_client.create_bucket(Bucket=self.Storage.bucket_name)
        self.Storage.upload_file(io.BytesIO(self.file_content), self.filename)
        object = self.s3_client.Object(self.Storage.bucket_name, self.filename)
        assert self.file_content == object.get()["Body"].read()
        assert (upload_dir / self.filename).exists()
        assert (upload_dir / self.filename).read_bytes() == self.file_content
        self.Storage.upload_file(io.BytesIO(self.file_content), self.filename_extra)
        object = self.s3_client.Object(self.Storage.bucket_name, self.filename_extra)
        assert self.file_content == object.get()["Body"].read()
        assert (upload_dir / self.filename).exists()
        assert (upload_dir / self.filename).read_bytes() == self.file_content

        self.Storage.delete_all_files()
        assert not (upload_dir / self.filename).exists()
        with pytest.raises(ClientError) as exc:
            self.s3_client.Object(self.Storage.bucket_name, self.filename).load()
        error = exc.value.response["Error"]
        assert error["Code"] == "404"
        assert error["Message"] == "Not Found"
        assert not (upload_dir / self.filename_extra).exists()
        with pytest.raises(ClientError) as exc:
            self.s3_client.Object(self.Storage.bucket_name, self.filename_extra).load()
        error = exc.value.response["Error"]
        assert error["Code"] == "404"
        assert error["Message"] == "Not Found"

        self.Storage.delete_all_files()
        assert not (upload_dir / self.filename).exists()
        assert not (upload_dir / self.filename_extra).exists()


class TestGCSStorageProvider:
    Storage = provider.GCSStorageProvider()
    Storage.bucket_name = "my-bucket"
    file_content = b"test content"
    filename = "test.txt"
    filename_extra = "test_exyta.txt"
    file_bytesio_empty = io.BytesIO()

    @pytest.fixture(scope="class")
    def setup(self):
        """
        Set up an in-memory Google Cloud Storage emulator for testing.
        
        This method performs the following steps:
        1. Starts an in-memory GCS server on localhost:9023.
        2. Sets the "STORAGE_EMULATOR_HOST" environment variable to point to the running emulator.
        3. Initializes a Google Cloud Storage client and creates a bucket using the name specified in self.Storage.bucket_name.
        4. Yields control to allow tests to run with the emulator environment.
        5. After yielding, force-deletes the created bucket and stops the emulator server as part of the teardown.
        
        Yields:
            None
        
        Raises:
            Exceptions from server startup, bucket creation, or cleanup will propagate.
        """
        host, port = "localhost", 9023

        server = create_server(host, port, in_memory=True)
        server.start()
        os.environ["STORAGE_EMULATOR_HOST"] = f"http://{host}:{port}"

        gcs_client = storage.Client()
        bucket = gcs_client.bucket(self.Storage.bucket_name)
        bucket.create()
        self.Storage.gcs_client, self.Storage.bucket = gcs_client, bucket
        yield
        bucket.delete(force=True)
        server.stop()

    def test_upload_file(self, monkeypatch, tmp_path, setup):
        upload_dir = mock_upload_dir(monkeypatch, tmp_path)
        # catch error if bucket does not exist
        with pytest.raises(Exception):
            self.Storage.bucket = monkeypatch(self.Storage, "bucket", None)
            self.Storage.upload_file(io.BytesIO(self.file_content), self.filename)
        contents, gcs_file_path = self.Storage.upload_file(
            io.BytesIO(self.file_content), self.filename
        )
        object = self.Storage.bucket.get_blob(self.filename)
        assert self.file_content == object.download_as_bytes()
        # local checks
        assert (upload_dir / self.filename).exists()
        assert (upload_dir / self.filename).read_bytes() == self.file_content
        assert contents == self.file_content
        assert gcs_file_path == "gs://" + self.Storage.bucket_name + "/" + self.filename
        # test error if file is empty
        with pytest.raises(ValueError):
            self.Storage.upload_file(self.file_bytesio_empty, self.filename)

    def test_get_file(self, monkeypatch, tmp_path, setup):
        """
        Test retrieval of an uploaded file using the storage provider's get_file method.
        
        This test performs the following steps:
        1. Sets up a temporary upload directory by monkey-patching the UPLOAD_DIR using the provided monkeypatch and tmp_path fixtures.
        2. Uploads a file with content from self.file_content and name self.filename using the storage provider's upload_file method.
        3. Retrieves the file path via the get_file method.
        4. Asserts that the returned file path matches the expected location within the temporary upload directory and that the file exists on disk.
        
        Parameters:
            monkeypatch (MonkeyPatch): Pytest fixture for modifying or simulating environments.
            tmp_path (Path): Temporary directory path provided by pytest.
            setup: Fixture used to set up the GCS emulator needed for the test.
        
        Raises:
            AssertionError: If the file path does not match the expected location or the file is not found.
        """
        upload_dir = mock_upload_dir(monkeypatch, tmp_path)
        contents, gcs_file_path = self.Storage.upload_file(
            io.BytesIO(self.file_content), self.filename
        )
        file_path = self.Storage.get_file(gcs_file_path)
        assert file_path == str(upload_dir / self.filename)
        assert (upload_dir / self.filename).exists()

    def test_delete_file(self, monkeypatch, tmp_path, setup):
        """
        Test deletion of a file from GCS storage and ensure its removal from the local upload directory.
        
        This test uploads a file using the GCS storage provider, verifying that the file is present in both the GCS bucket and the locally uploaded directory. After deleting the file via the storage provider's delete_file method, the test asserts that the file is removed from both locations.
        
        Parameters:
            self: Instance of the test class.
            monkeypatch: pytest fixture for safely patching attributes.
            tmp_path: pytest fixture that provides a temporary directory for file storage.
            setup: Fixture that sets up the GCS emulator and bucket for testing.
        
        Raises:
            AssertionError: If the file is not properly uploaded or removed from either storage location.
        """
        upload_dir = mock_upload_dir(monkeypatch, tmp_path)
        contents, gcs_file_path = self.Storage.upload_file(
            io.BytesIO(self.file_content), self.filename
        )
        # ensure that local directory has the uploaded file as well
        assert (upload_dir / self.filename).exists()
        assert self.Storage.bucket.get_blob(self.filename).name == self.filename
        self.Storage.delete_file(gcs_file_path)
        # check that deleting file from gcs will delete the local file as well
        assert not (upload_dir / self.filename).exists()
        assert self.Storage.bucket.get_blob(self.filename) == None

    def test_delete_all_files(self, monkeypatch, tmp_path, setup):
        """
        Test deletion of all files from storage.
        
        This test verifies that the delete_all_files() method of the storage provider
        properly removes all uploaded files from both the temporary local upload directory
        and the remote storage bucket. It performs the following steps:
        1. Sets up a temporary upload directory using the monkeypatch and tmp_path fixtures.
        2. Uploads two files with known content to the storage provider.
        3. Asserts that the uploaded files exist in the local directory and the corresponding
           blobs in the remote bucket contain the expected names and byte content.
        4. Calls delete_all_files() to remove all files.
        5. Confirms that both the local files and the remote blobs have been deleted.
        """
        upload_dir = mock_upload_dir(monkeypatch, tmp_path)
        # create 2 files
        self.Storage.upload_file(io.BytesIO(self.file_content), self.filename)
        object = self.Storage.bucket.get_blob(self.filename)
        assert (upload_dir / self.filename).exists()
        assert (upload_dir / self.filename).read_bytes() == self.file_content
        assert self.Storage.bucket.get_blob(self.filename).name == self.filename
        assert self.file_content == object.download_as_bytes()
        self.Storage.upload_file(io.BytesIO(self.file_content), self.filename_extra)
        object = self.Storage.bucket.get_blob(self.filename_extra)
        assert (upload_dir / self.filename_extra).exists()
        assert (upload_dir / self.filename_extra).read_bytes() == self.file_content
        assert (
            self.Storage.bucket.get_blob(self.filename_extra).name
            == self.filename_extra
        )
        assert self.file_content == object.download_as_bytes()

        self.Storage.delete_all_files()
        assert not (upload_dir / self.filename).exists()
        assert not (upload_dir / self.filename_extra).exists()
        assert self.Storage.bucket.get_blob(self.filename) == None
        assert self.Storage.bucket.get_blob(self.filename_extra) == None
