#!/usr/bin/env python


"""
@file ion/services/dm/preservation/preservation_registry.py
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

class PreservationRegistryService(registry.BaseRegistryService):
    """
    @brief Preservation registry service interface
    """

     # Declaration of service
    declare = ServiceProcess.service_declare(name='preservation_registry', version='0.1.0', dependencies=[])

    op_define_archive = registry.BaseRegistryService.base_register_resource
    """
    Service operation: Create or update a archive resource.
    """
    op_get_archive = registry.BaseRegistryService.base_get_resource
    """
    Service operation: Get an archive resource
    """
    op_find_archive = registry.BaseRegistryService.base_find_resource
    """
    Service operation: Find an archive resource by characteristics
    """

# Spawn of the process using the module name
factory = ProcessFactory(PreservationRegistryService)


class PreservationRegistryClient(registry.BaseRegistryClient):
    """
    Class for the client accessing the Preservation registry.
    """
    def __init__(self, proc=None, **kwargs):
        if not 'targetname' in kwargs:
            kwargs['targetname'] = 'preservation_registry'
        ServiceClient.__init__(self, proc, **kwargs)


    def clear_registry(self):
        return self.base_clear_registry('clear_registry')


    def define_archive(self,archive):
        """
        @brief Client method to Register an archive

        @param archive is an instance of a Archive Resource
        """
        return  self.base_register_resource('define_archive', archive)


    def get_archive(self,archive_reference):
        """
        @brief Get a archive by reference
        @param archive_reference is the unique reference object for a registered
        archive
        """
        return self.base_get_resource('get_archive',archive_reference)

    def find_archive(self, description,regex=True,ignore_defaults=True,attnames=[]):
        """
        @brief find all registered archive which match the attributes of description
        @param see the registry docs for params
        """
        return self.base_find_resource('find_archive',description,regex,ignore_defaults,attnames)
