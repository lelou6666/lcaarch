#!/usr/bin/env python

"""
@file ion/core/process/test/life_cycle_process.py
@author David Stuebe
@brief test case for process base class
"""

import os
import hashlib

from twisted.trial import unittest
from twisted.internet import defer

import ion.util.ionlog
log = ion.util.ionlog.getLogger(__name__)

from ion.core import ioninit
from ion.core.messaging import ion_reply_codes
from ion.core.process.process import Process, ProcessDesc, ProcessFactory
from ion.core.cc.container import Container
from ion.core.exception import ReceivedError
from ion.core.messaging.receiver import Receiver, WorkerReceiver
from ion.core.id import Id
from ion.test.iontest import IonTestCase, ReceiverProcess
import ion.util.procutils as pu
from ion.util import state_object



class LifeCycleObject(state_object.BasicLifecycleObject):
    
    def on_initialize(self, *args, **kwargs):
        log.info('LifeCycleObject on_initialize')

    def on_activate(self, *args, **kwargs):
        log.info('LifeCycleObject on_activate')

    def on_deactivate(self, *args, **kwargs):
        log.info('LifeCycleObject on_deactivate')

    def on_terminate(self, *args, **kwargs):
        log.info('LifeCycleObject on_terminate')

    def on_error(self, *args, **kwargs):
        log.info('LifeCycleObject on_error')



class LCOProcess(Process):
    """
    This process is for testing only. Do not pass an object to the init of a process.
    """

    def __init__(self, lco, spawnargs=None):
        """
        Initialize a process with an additional Life Cycle object
        """
        Process.__init__(self, spawnargs)
        
        self.add_life_cycle_object(lco)
        
        
        #self.register_life_cycle_object(lco)

# Spawn of the process using the module name
factory = ProcessFactory(LCOProcess)