import json
import redis
import uuid


class RedisLock:
    def __init__(self, redis_url, lock_name, timeout_secs):
        """
        Initialize a distributed lock using Redis.
        
        Parameters:
            redis_url (str): The URL of the Redis server to connect to.
            lock_name (str): A unique name identifying the specific lock.
            timeout_secs (int): The duration in seconds for which the lock is valid.
        
        Attributes:
            lock_name (str): The name of the lock.
            lock_id (str): A unique identifier generated for this lock instance.
            timeout_secs (int): The expiration time for the lock.
            lock_obtained (bool): Flag indicating whether the lock has been successfully acquired.
            redis (Redis): A Redis connection instance configured with decode_responses.
        """
        self.lock_name = lock_name
        self.lock_id = str(uuid.uuid4())
        self.timeout_secs = timeout_secs
        self.lock_obtained = False
        self.redis = redis.Redis.from_url(redis_url, decode_responses=True)

    def aquire_lock(self):
        # nx=True will only set this key if it _hasn't_ already been set
        """
        Attempt to acquire a distributed lock in Redis.
        
        Tries to set a unique lock key with an expiration time. The lock is only set if it does not already exist.
        
        Parameters:
            None
        
        Returns:
            bool: True if the lock was successfully acquired, False otherwise.
        
        Notes:
            - Uses Redis `set` command with `nx=True` to ensure atomic lock acquisition
            - Sets an expiration time to prevent indefinite locking
            - The lock is identified by `self.lock_name` and `self.lock_id`
            - Stores the lock acquisition status in `self.lock_obtained`
        """
        self.lock_obtained = self.redis.set(
            self.lock_name, self.lock_id, nx=True, ex=self.timeout_secs
        )
        return self.lock_obtained

    def renew_lock(self):
        # xx=True will only set this key if it _has_ already been set
        """
        Renew an existing Redis lock by updating its expiration time.
        
        Attempts to renew the lock by setting the same lock identifier with an updated expiration time. 
        The lock can only be renewed if it already exists in Redis.
        
        Parameters:
            None
        
        Returns:
            bool: True if the lock was successfully renewed, False otherwise
        """
        return self.redis.set(
            self.lock_name, self.lock_id, xx=True, ex=self.timeout_secs
        )

    def release_lock(self):
        """
        Release the Redis lock if the current lock ID matches the stored lock value.
        
        This method checks if the lock is currently held by the current instance by comparing
        the stored lock value with the instance's lock ID. If they match, the lock is deleted
        from Redis, effectively releasing the lock.
        
        Returns:
            None
        
        Note:
            - Only releases the lock if the current instance owns the lock
            - Uses UTF-8 decoding to compare lock values
            - No-op if the lock has already been released or does not exist
        """
        lock_value = self.redis.get(self.lock_name)
        if lock_value and lock_value.decode("utf-8") == self.lock_id:
            self.redis.delete(self.lock_name)


class RedisDict:
    def __init__(self, name, redis_url):
        """
        Initialize a Redis-backed dictionary with a specific name and connection.
        
        Parameters:
            name (str): The unique identifier for the Redis hash to be used as a dictionary
            redis_url (str): The connection URL for the Redis server
        
        Attributes:
            name (str): Stores the dictionary's name for Redis hash identification
            redis (Redis): An active Redis connection with response decoding enabled
        """
        self.name = name
        self.redis = redis.Redis.from_url(redis_url, decode_responses=True)

    def __setitem__(self, key, value):
        serialized_value = json.dumps(value)
        self.redis.hset(self.name, key, serialized_value)

    def __getitem__(self, key):
        value = self.redis.hget(self.name, key)
        if value is None:
            raise KeyError(key)
        return json.loads(value)

    def __delitem__(self, key):
        result = self.redis.hdel(self.name, key)
        if result == 0:
            raise KeyError(key)

    def __contains__(self, key):
        return self.redis.hexists(self.name, key)

    def __len__(self):
        return self.redis.hlen(self.name)

    def keys(self):
        return self.redis.hkeys(self.name)

    def values(self):
        return [json.loads(v) for v in self.redis.hvals(self.name)]

    def items(self):
        return [(k, json.loads(v)) for k, v in self.redis.hgetall(self.name).items()]

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def clear(self):
        self.redis.delete(self.name)

    def update(self, other=None, **kwargs):
        if other is not None:
            for k, v in other.items() if hasattr(other, "items") else other:
                self[k] = v
        for k, v in kwargs.items():
            self[k] = v

    def setdefault(self, key, default=None):
        if key not in self:
            self[key] = default
        return self[key]
