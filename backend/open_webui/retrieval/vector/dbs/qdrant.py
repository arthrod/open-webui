from qdrant_client import QdrantClient as Client, models
from qdrant_client.http.models import (
    Distance,
    PointStruct,
    VectorParams,
    Filter,
    FieldCondition,
    MatchValue,
)


from typing import Optional

from open_webui.retrieval.vector.main import VectorItem, SearchResult, GetResult
from open_webui.config import (
    QDRANT_API_KEY,
    QDRANT_TIMEOUT_SECONDS,
    QDRANT_URL,
)


class QdrantClient:
    def __init__(self):
        """
        Initializes the QdrantClient instance.
        
        This constructor sets up the underlying client used to interact with the Qdrant database by 
        instantiating a Client object with configuration parameters:
            - QDRANT_URL: The URL of the Qdrant server.
            - QDRANT_API_KEY: The API key for authentication.
            - QDRANT_TIMEOUT_SECONDS: The timeout (in seconds) for requests, converted to an integer.
        
        Attributes:
            client (Client): A client instance configured for communication with the Qdrant database.
        """
        self.client = Client(
            url=QDRANT_URL, api_key=QDRANT_API_KEY, timeout=int(QDRANT_TIMEOUT_SECONDS)
        )

    def _result_to_get_result(self, result) -> GetResult:
        """
        Converts a raw query result into a GetResult object.
        
        This method processes the first element of the provided result tuple, iterating over each record to extract
        the record's id, text, and metadata from its payload. The id, text, and metadata are wrapped in single-element lists
        and aggregated into corresponding lists which are used to instantiate and return a GetResult object.
        
        Parameters:
            result (tuple): A tuple where the first element is an iterable of record objects. Each record must have:
                - an `id` attribute
                - a `payload` dictionary with the keys "text" (str) and "metadata" (any)
        
        Returns:
            GetResult: An object containing three lists:
                - ids: A list of single-element lists containing record IDs.
                - documents: A list of single-element lists containing record text.
                - metadatas: A list of single-element lists containing record metadata.
        """
        ids = []
        documents = []
        metadatas = []

        # Iterate over the tuple of records
        for record in result[0]:
            ids.append([record.id])
            documents.append([record.payload["text"]])
            metadatas.append([record.payload["metadata"]])

        return GetResult(
            **{
                "ids": ids,
                "documents": documents,
                "metadatas": metadatas,
            }
        )

    def _result_to_search_result(self, result) -> SearchResult:
        """
        Convert a raw search result into a structured SearchResult object.
        
        This internal helper method processes the result from a Qdrant search query by iterating over the
        points in the result and extracting relevant attributes. For each point, it collects the point's
        identifier, score, document text (from the "text" key in the payload), and additional metadata (from
        the "metadata" key in the payload). The collected data is organized into lists (each wrapped in its own 
        list) and used to instantiate a SearchResult object.
        
        Parameters:
            result (object): The raw search result returned by a Qdrant query. It must have an attribute 
                             'points', where each point is expected to have the following attributes:
                                   - id: The unique identifier of the point.
                                   - score (float): The similarity score of the point.
                                   - payload (dict): A dictionary containing at least the keys:
                                         "text" (str): The document text.
                                         "metadata": Additional metadata related to the point.
        
        Returns:
            SearchResult: A structured object containing the search results with the following fields:
                          - ids (list): A list of lists, each containing a point's identifier.
                          - distances (list): A list of lists, each containing the score associated with a point.
                          - documents (list): A list of lists, each containing the document text from a point.
                          - metadatas (list): A list of lists, each containing the metadata from a point.
        """
        ids = []
        distances = []
        documents = []
        metadatas = []

        for point in result.points:
            ids.append([point.id])
            distances.append([point.score])
            documents.append([point.payload["text"]])
            metadatas.append([point.payload["metadata"]])

        return SearchResult(
            **{
                "ids": ids,
                "distances": distances,
                "documents": documents,
                "metadatas": metadatas,
            }
        )

    def has_collection(self, collection_name: str) -> bool:
        # Check if the collection exists based on the collection name.
        """
        Check if the specified collection exists in the Qdrant database.
        
        Parameters:
            collection_name (str): The name of the collection to check.
        
        Returns:
            bool: True if the collection exists, False otherwise.
        """
        return self.client.collection_exists(collection_name=collection_name)

    def delete_collection(self, collection_name: str):
        # Delete the collection based on the collection name.
        """
            Delete a collection from the Qdrant database.
        
            This method delegates the deletion task to the underlying client by
            calling its `delete_collection` method with the specified collection name.
        
            Parameters:
                collection_name (str): The name of the collection to delete.
        
            Returns:
                The result of the delete operation as provided by the underlying client.
                The exact type and structure of the result depend on the client's implementation.
        
            Raises:
                Any exceptions raised by the underlying client during the deletion process.
            """
        return self.client.delete_collection(collection_name=collection_name)

    def search(
        self, collection_name: str, vectors: list[list[float | int]], limit: int
    ) -> Optional[SearchResult]:
        # Search for the nearest neighbor items based on the vectors and return 'limit' number of results.
        """
        Search for the nearest neighbor items in the specified collection.
        
        This method uses the provided query vectors to perform a nearest neighbor search on the given collection.
        It delegates the search execution to the underlying Qdrant client's `query_points` method and processes
        the returned data into a structured `SearchResult` object via the `_result_to_search_result` helper.
        
        Parameters:
            collection_name (str): The name of the collection to search.
            vectors (list[list[float | int]]): A list of query vectors used for searching.
            limit (int): The maximum number of search results to return.
        
        Returns:
            Optional[SearchResult]: A SearchResult object containing the matched items with their IDs, distances, documents, 
            and metadata if the search is successful; otherwise, None.
        
        Example:
            search_result = client.search("my_collection", [[0.1, 0.2, 0.3]], 5)
        """
        result = self.client.query_points(
            collection_name=collection_name,
            query=vectors,
            limit=limit,
            with_payload=True,
        )

        return self._result_to_search_result(result)

    def query(
        self, collection_name: str, filter: dict, limit: Optional[int] = None
    ) -> Optional[GetResult]:
        """
        Query a specified collection in Qdrant using an optional filter and limit.
        
        This method attempts to scroll through the specified collection in the Qdrant database. If a filter is provided,
        it constructs Qdrant conditions using FieldCondition and MatchValue, and creates a Filter object. The method then
        fetches points using the client's scroll method and converts the result into a GetResult object. If the collection
        does not exist or an error occurs during the query, the method returns None.
        
        Parameters:
            collection_name (str): The name of the collection to query.
            filter (dict): A dictionary of field-value pairs used to filter the query. If empty, no filtering is applied.
            limit (Optional[int]): The maximum number of records to retrieve. Defaults to 1 if not specified.
        
        Returns:
            Optional[GetResult]: The result of the query as a GetResult object if successful; otherwise, None.
        """
        try:
            if not self.client.collection_exists(collection_name=collection_name):
                return None

            # Build the conditions if a filter is provided.
            qdrant_filter = None
            if filter:
                conditions = [
                    FieldCondition(key=key, match=MatchValue(value=value))
                    for key, value in filter.items()
                ]
                qdrant_filter = Filter(must=conditions)

            points, _ = self.client.scroll(
                collection_name=collection_name,
                scroll_filter=qdrant_filter,
                limit=limit or 1,
            )

            return self._result_to_get_result(points)

        except Exception as e:
            print(f"Error querying Qdrant: {e}")
            return None

    def get(self, collection_name: str) -> Optional[GetResult]:
        """
        Retrieve all items from the specified collection.
        
        This method first determines the number of items in the collection by calling the client's count method. If the collection contains any items, it uses a scroll operation with a limit equal to the count to retrieve all items along with their associated payloads. The raw result is then converted into a GetResult object using the _result_to_get_result helper method. If the collection is empty, the method returns None.
        
        Parameters:
            collection_name (str): The name of the collection to retrieve items from.
        
        Returns:
            Optional[GetResult]: A GetResult object containing the retrieved items if the collection is non-empty; otherwise, None.
        """
        points = self.client.count(
            collection_name=collection_name,
        )
        if points.count:
            # Get all the items in the collection.
            result = self.client.scroll(
                collection_name=collection_name,
                with_payload=True,
                limit=points.count,
            )

            return self._result_to_get_result(result)

        return None

    def insert(self, collection_name: str, items: list[VectorItem]):
        """
        Insert items into the specified collection by delegating to the upsert method.
        
        This method provides a convenient alias for inserting or updating vector items. It calls the upsert method to add the given items to the collection, creating the collection if it does not already exist.
        
        Parameters:
            collection_name (str): The name of the collection where items will be inserted.
            items (list[VectorItem]): A list of vector items to be inserted or updated in the collection.
        
        Returns:
            The result of the upsert operation.
        """
        return self.upsert(collection_name=collection_name, items=items)

    def upsert(self, collection_name: str, items: list[VectorItem]):
        # Update the items in the collection, if the items are not present, insert them. If the collection does not exist, it will be created.
        """
        Upsert vector items into the specified collection in Qdrant.
        
        This method updates existing items in the collection and inserts new ones if they are not already present.
        If the collection does not exist, it will be created with a vector configuration derived from the first item's vector length,
        using COSINE as the distance metric and a predefined multivector configuration.
        
        Parameters:
            collection_name (str): The name of the collection to upsert items into.
            items (list[VectorItem]): A list of dictionaries representing vector items. Each dictionary must include:
                - "id": A unique identifier for the item.
                - "vector": A list of numerical values representing the vector.
                - "text": The text data associated with the item.
                - "metadata": Additional metadata related to the item.
        
        Returns:
            The result of the upsert operation as returned by the underlying Qdrant client.
        """
        if not self.client.collection_exists(collection_name=collection_name):
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=len(items[0]["vector"]),
                    distance=Distance.COSINE,
                    multivector_config=models.MultiVectorConfig(
                        comparator=models.MultiVectorComparator.MAX_SIM
                    ),
                ),
            )

        points = [
            PointStruct(
                id=item["id"],
                vector=item["vector"],
                payload={"text": item["text"], "metadata": item["metadata"]},
            )
            for item in items
        ]

        return self.client.upsert(
            collection_name=collection_name,
            points=points,
        )

    def delete(
        self,
        collection_name: str,
        ids: Optional[list[str]] = None,
        filter: Optional[dict] = None,
    ):
        # Delete the items from the collection based on the ids.
        """
        Delete items from a specified collection in the Qdrant database using item IDs or filter conditions.
        
        Parameters:
            collection_name (str): Name of the collection from which to delete items.
            ids (Optional[List[str]]): List of item identifiers to be deleted. If provided, these take precedence over the filter.
            filter (Optional[dict]): Dictionary of filter conditions where keys are field names and values are the corresponding match values. Used only if `ids` is not provided.
        
        Returns:
            The response from the client's delete operation, confirming the deletion action.
        
        Note:
            Either `ids` or `filter` must be provided. If both are provided, only `ids` will be used.
        """
        if ids:
            selector = ids
        elif filter:
            conditions = [
                FieldCondition(key=key, match=MatchValue(value=value))
                for key, value in filter.items()
            ]
            selector = Filter(must=conditions)

        return self.client.delete(
            collection_name=collection_name,
            points_selector=selector,
        )

    def reset(self):
        # Resets the database. This will delete all collections and item entries.

        """
        Resets the Qdrant database by deleting all collections and their entries.
        
        This method retrieves all existing collections using the client’s `get_collections` method and iteratively
        deletes each collection by invoking `delete_collection` with the collection's name. Use with caution, as this
        operation is destructive and irreversible.
        
        Raises:
            Exception: Propagates any exceptions raised by the client during retrieval or deletion of collections.
        """
        collection_response = self.client.get_collections()

        for collection in collection_response.collections:
            self.client.delete_collection(collection_name=collection.name)
