from test.util.abstract_integration_test import AbstractPostgresTest
from test.util.mock_user import mock_webui_user


class TestModels(AbstractPostgresTest):
    BASE_PATH = "/api/v1/models"

    def setup_class(cls):
        """
        Set up the test class by initializing the Model class for testing.
        
        This method performs the following actions:
        - Calls the parent class's setup method to perform base initialization
        - Imports the Model class from the specified module
        - Assigns the Model class to the class-level attribute `models` for use in test methods
        
        Note:
            This method is typically used in test classes to prepare resources and set up the testing environment before running individual test methods.
        """
        super().setup_class()
        from open_webui.models.models import Model

        cls.models = Model

    def test_models(self):
        """
        Test the complete lifecycle of model management through API endpoints.
        
        This test method systematically verifies the functionality of model-related API operations:
        1. Initial state check (empty model list)
        2. Model creation
        3. Verifying model addition
        4. Retrieving a specific model by ID
        5. Deleting a model
        6. Confirming model deletion
        
        The test uses mock authentication and covers the following scenarios:
        - Retrieving an empty model list
        - Adding a new model with specific metadata
        - Checking model list after addition
        - Fetching a specific model by its ID
        - Deleting a model
        - Confirming the model list is empty after deletion
        
        Each step uses a mocked user with ID "2" and validates response status codes and content.
        """
        with mock_webui_user(id="2"):
            response = self.fast_api_client.get(self.create_url("/"))
        assert response.status_code == 200
        assert len(response.json()) == 0

        with mock_webui_user(id="2"):
            response = self.fast_api_client.post(
                self.create_url("/add"),
                json={
                    "id": "my-model",
                    "base_model_id": "base-model-id",
                    "name": "Hello World",
                    "meta": {
                        "profile_image_url": "/static/favicon.png",
                        "description": "description",
                        "capabilities": None,
                        "model_config": {},
                    },
                    "params": {},
                },
            )
        assert response.status_code == 200

        with mock_webui_user(id="2"):
            response = self.fast_api_client.get(self.create_url("/"))
        assert response.status_code == 200
        assert len(response.json()) == 1

        with mock_webui_user(id="2"):
            response = self.fast_api_client.get(
                self.create_url(query_params={"id": "my-model"})
            )
        assert response.status_code == 200
        data = response.json()[0]
        assert data["id"] == "my-model"
        assert data["name"] == "Hello World"

        with mock_webui_user(id="2"):
            response = self.fast_api_client.delete(
                self.create_url("/delete?id=my-model")
            )
        assert response.status_code == 200

        with mock_webui_user(id="2"):
            response = self.fast_api_client.get(self.create_url("/"))
        assert response.status_code == 200
        assert len(response.json()) == 0
