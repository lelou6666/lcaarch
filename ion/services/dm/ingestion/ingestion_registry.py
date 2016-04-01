#!/usr/bin/env python


"""
@file ion/services/dm/ingestion/ingestion_registry.py
@author David Stuebe
@brief registry for preservation service resources
"""

import ion.util.ionlog
log = ion.util.ionlog.getLogger(__name__)
from twisted.internet import defer
from twisted.python import reflect

from ion.data import dataobject
from ion.data.datastore import registry
from ion.data import store

from ion.core import ioninit
from ion.core.process.process import ProcessFactory, Process
from ion.core.process.service_process import ServiceProcess, ServiceClient
import ion.util.procutils as pu

from ion.resources import dm_resource_descriptions

CONF = ioninit.config(__name__)

class IngestionRegistryService(registry.BaseRegistryService):
    """
    @brief Ingestion registry service interface
    """

     # Declaration of service
    declare = ServiceProcess.service_declare(name='ingestion_registry', version='0.1.0', dependencies=[])

    op_define_ingestion_stream = registry.BaseRegistryService.base_register_resource
    """
    Service operation: Create or update a ingestion_stream resource.
    """
    op_get_ingestion_stream = registry.BaseRegistryService.base_get_resource
    """
    Service operation: Get an ingestion_stream resource
    """
    op_find_ingestion_stream = registry.BaseRegistryService.base_find_resource
    """
    Service operation: Find an ingestion_stream resource by characteristics
    """

# Spawn of the process using the module name
factory = ProcessFactory(IngestionRegistryService)


class IngestionRegistryClient(registry.BaseRegistryClient):
    """
    Class for the client accessing the ingestion registry.
    """
    def __init__(self, proc=None, **kwargs):
        if not 'targetname' in kwargs:
            kwargs['targetname'] = 'ingestion_registry'
        ServiceClient.__init__(self, proc, **kwargs)


    def clear_registry(self):
        return self.base_clear_registry('clear_registry')


    def define_ingestion_stream(self,ingestion_stream):
        """
        @brief Client method to Register an ingestion_stream

        @param ingestion_stream is an instance of a Ingestion Stream Resource
        """
        return  self.base_register_resource('ingestion_stream', ingestion_stream)


    def get_ingestion_stream(self,ingestion_stream_reference):
        """
        @brief Get a ingestion_stream by reference
        @param ingestion_stream_reference is the unique reference object for a registered
        ingestion_stream
        """
        return self.base_get_resource('get_ingestion_stream',archive_reference)

    def find_ingestion_stream(self, description,regex=True,ignore_defaults=True,attnames=[]):
        """
        @brief find all registered ingestion streams which match the attributes of description
        @param see the registry docs for params
        """
        return self.base_find_resource('find_ingestion_stream',description,regex,ignore_defaults,attnames)
