"""
@file ion/data/store.py
@package ion.data.IStore Pure virtual base class for CRUD
@package ion.data.Store In-memory implementation of ion.data.IStore
@author Michael Meisinger
@author David Stuebe
@author Dorian Raymer
@brief base interface for all key-value stores in the system and default
        in memory implementation
"""

from zope.interface import Interface
from zope.interface import implements

from twisted.internet import defer

import ion.util.ionlog
log = ion.util.ionlog.getLogger(__name__)



class IStore(Interface):
    """
    Interface all store backend implementations.
    All operations are returning deferreds and operate asynchronously.

    @var namespace
    """

    def get(key):
        """
        @param key  an immutable key associated with a value
        @retval Deferred, for value associated with key, or None if not existing.
        """

    def put(key, value):
        """
        @param key  an immutable key to be associated with a value
        @param value  an object to be associated with the key. The caller must
                not modify this object after it was
        @retval Deferred, for success of this operation
        """

    def remove(key):
        """
        @param key  an immutable key associated with a value
        @retval Deferred, for success of this operation
     
        """

class Store(object):
    """
    Memory implementation of an asynchronous key/value store, using a dict.
    Simulates typical usage of using a client connection to a backend
    technology.
    """
    implements(IStore)

    def __init__(self, *args, **kwargs):
        self.kvs = {}

    def get(self, key):
        """
        @see IStore.get
        """
        return defer.maybeDeferred(self.kvs.get, key, None)

    def put(self, key, value):
        """
        @see IStore.put
        """
        return defer.maybeDeferred(self.kvs.update, {key:value})

    def remove(self, key):
        """
        @see IStore.remove
        """
        # could test for existance of key. this will error otherwise
        if self.kvs.has_key(key):
            del self.kvs[key]
        return defer.succeed(None)

class IDataManager(Interface):
    """
    @note Proposed class to fulfill preservation service management?
    @brief Administrative functionality for backend store configuration. 
    """
    def create_persistent_archive(self, persistent_archive):
        """
        @brief Create a separate organizational instance in the backend
        @param persistent_archive is the name of the organization
        @retval succeed or fail
        """
        
        
    def remove_persistent_archive(self, persistent_archive):
        """
        @brief Remove an organizational instance in the backend
        @param persistent_archive is the name of the organization
        """
        
    def update_persistent_archive(self, persistent_archive):
        """
        @brief changes the configuration of the persistent archive
        @param persistent_archive the name and configuration of the persistent archive.
        This is represented as an OOI resource.
        """
        
    def create_cache(self, persistent_archive, cache):
        """
        @brief creates a new cache in Cassandra this creates a new column family
        @param persistent_archive the archive in which the cache resides
        @param cache a resource representation of the cache, this includes its name and configuration
        """
    
    def update_cache(self, cache):
        """
        @brief changes the configuration of the current cache
        @param a resource representation of the cache
        """
        
    def remove_cache(self, cache):
        """
        @brief remove the current cache
        @param a resource representation of the cache
        """



class DataManager(object):
    """
    Memory implementation of the IDataManager interface. This conforms to the interface,
    but does nothing.
    """
    implements(IDataManager)

    def create_persistent_archive(self, persistent_archive):
        """
        @brief Create a separate organizational instance in the backend
        @param persistent_archive the name and configuration of the persistent archive.
        @retval succeed or fail
        """
        
        
    def remove_persistent_archive(self, persistent_archive):
        """
        @brief Remove an organizational instance in the backend
        @param persistent_archive is the name of the organization
        """
        
    def update_persistent_archive(self, persistent_archive):
        """
        @brief changes the configuration of the persistent archive
        @param persistent_archive the name and configuration of the persistent archive.
        This is represented as an OOI resource.
        """
        
    def create_cache(self, persistent_archive, cache):
        """
        @brief creates a new cache in Cassandra this creates a new column family
        @param persistent_archive the archive in which the cache resides
        @param cache a resource representation of the cache, this includes its name and configuration
        """
    
    def update_cache(self, cache):
        """
        @brief changes the configuration of the current cache
        @param a resource representation of the cache
        """
        
    def remove_cache(self, persistent_archive, cache):
        """
        @brief remove the current cache
        @param persistent_archive the name and configuration of the persistent archive.
        @param a resource representation of the cache
        """
    
    
    
class BackendBuilder(object):
    """
    All store client connections need:
        - host
        - port
    All stores have:
        - namespace

    See if a generic process TCP connector makes sense.
    Any implementation of IStore must operate in the ion framework, and
    therefore it only makes sense for the life cycle of the class instance
    and the connection of the backend client to be carried out in concert
    with an ion process.
    """

    def __init__(self, host, port, process):
        """
        @param process the process instance
        """
        self.host = host
        self.port = port
        self.process = process
        
        






