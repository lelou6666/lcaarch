#!/usr/bin/env python

"""
@file ion/services/dm/distribution/test/test_baseconsumer.py
@author David Stuebe
@brief test cases for the base consumer process
"""

import ion.util.ionlog
log = ion.util.ionlog.getLogger(__name__)

#import time
from twisted.internet import defer
from twisted.trial import unittest

from ion.core.process.process import ProcessFactory
from ion.core import bootstrap
from ion.core.exception import ReceivedError
#from ion.core.process.process import Process, ProcessDesc
from ion.test.iontest import IonTestCase
import ion.util.procutils as pu

from ion.data import dataobject
from ion.resources.dm_resource_descriptions import \
    DataMessageObject, DictionaryMessageObject, StringMessageObject

from ion.services.dm.distribution import base_consumer

class BaseConsumerTest(IonTestCase):
    '''
    Test cases for the base consumer method. They examine the message based
    control of the child processes and ensure that ondata is called properly
    '''


    @defer.inlineCallbacks
    def setUp(self):
        yield self._start_container()
        #self.sup = yield self._spawn_processes(services)

        #Create two test queues
        queue1=dataobject.create_unique_identity()
        queue_properties = {queue1:{'name_type':'fanout', 'args':{'scope':'global'}}}
        yield bootstrap.declare_messaging(queue_properties)
        self.queue1 = queue1

        queue2=dataobject.create_unique_identity()
        queue_properties = {queue2:{'name_type':'fanout', 'args':{'scope':'global'}}}
        yield bootstrap.declare_messaging(queue_properties)
        self.queue2 = queue2

        queue3=dataobject.create_unique_identity()
        queue_properties = {queue3:{'name_type':'fanout', 'args':{'scope':'global'}}}
        yield bootstrap.declare_messaging(queue_properties)
        self.queue3 = queue3


    @defer.inlineCallbacks
    def tearDown(self):
        yield self._stop_container()
        # Kill the queues?


    @defer.inlineCallbacks
    def test_spawn_attach_args(self):

        pd1={'name':'consumer_number_1',
                 'module':'ion.services.dm.distribution.consumers.forwarding_consumer',
                 'procclass':'ForwardingConsumer',
                 'spawnargs':{'attach':[self.queue1]}}
        child1 = base_consumer.ConsumerDesc(**pd1)

        child1_id = yield self.test_sup.spawn_child(child1)

        # Don't do this - you can only get the instance in a test case -
        # this is not a valid pattern in OTP
        dc1 = self._get_procinstance(child1_id)

        self.assertIn(self.queue1,dc1.dataReceivers)


    @defer.inlineCallbacks
    def test_spawn_attach_msg(self):

        pd1={'name':'consumer_number_1', \
                 'module':'ion.services.dm.distribution.consumers.forwarding_consumer',
                 'procclass':'ForwardingConsumer',}
        child1 = base_consumer.ConsumerDesc(**pd1)

        child1_id = yield self.test_sup.spawn_child(child1)

        res = yield child1.attach(self.queue1)
        self.assertEqual(res,'OK')
        #self.assertEqual(child.proc_attached,self.queue1)


        try:
            res = yield child1.attach(None)
            self.fail("ReceivedError expected")
        except ReceivedError, re:
            pass
        #self.assertEqual(child.proc_attached,None)

        yield child1.shutdown()

    @defer.inlineCallbacks
    def test_spawn_attach_inst(self):

        pd1={'name':'consumer_number_1', \
                 'module':'ion.services.dm.distribution.consumers.forwarding_consumer',
                 'procclass':'ForwardingConsumer',}
        child1 = base_consumer.ConsumerDesc(**pd1)

        child1_id = yield self.test_sup.spawn_child(child1)

        # NOT VALID IN OTP TO GET THE INSTANCE ONLY FOR TEST CASE
        dc1 = self._get_procinstance(child1_id)

        res = yield dc1.attach(self.queue1)
        #@todo Assert what?
        self.assert_(res)
        #self.assertEqual(child.proc_attached,self.queue1)

        yield dc1.shutdown()



    @defer.inlineCallbacks
    def test_params(self):

        pd1={'name':'consumer_number_1', \
                 'module':'ion.services.dm.distribution.consumers.forwarding_consumer',
                 'procclass':'ForwardingConsumer',}
        child1 = base_consumer.ConsumerDesc(**pd1)

        child1_id = yield self.test_sup.spawn_child(child1)

        # Send a dictionary
        params={'Junk':'Trunk'}
        res = yield child1.set_process_parameters(params)
        self.assertEqual(res,'OK')

        res = yield child1.get_process_parameters()

        self.assertEqual(res,params)

        params2 = {'more junk':'my trunk'}
        res = yield child1.set_process_parameters(params2)
        self.assertEqual(res,'OK')

        res = yield child1.get_process_parameters()

        ptest = dict(params)
        ptest.update(params2)
        self.assertEqual(res,ptest)
        yield child1.shutdown()


    @defer.inlineCallbacks
    def test_send(self):
        pd1={'name':'consumer_number_1',
                 'module':'ion.services.dm.distribution.consumers.forwarding_consumer',
                 'procclass':'ForwardingConsumer',
                 'spawnargs':{'attach':self.queue1,\
                              'process parameters':{},
                              'delivery queues':{'queues':[self.queue2]}}\
                    }
        child1 = base_consumer.ConsumerDesc(**pd1)

        child1_id = yield self.test_sup.spawn_child(child1)

        dmsg = DataMessageObject()
        dmsg.notifcation = 'Junk'
        dmsg.timestamp = pu.currenttime()
        dmsg = dmsg.encode()

        yield self.test_sup.send(self.queue1, 'data', dmsg)

        yield pu.asleep(1)
        msg_cnt = yield child1.get_msg_count()
        received = msg_cnt.get('received',{})
        sent = msg_cnt.get('sent',{})
        self.assertEqual(sent.get(self.queue2),1)
        self.assertEqual(received.get(self.queue1),1)


    @defer.inlineCallbacks
    def test_send_chain(self):
        pd1={'name':'consumer_number_1',
                 'module':'ion.services.dm.distribution.consumers.forwarding_consumer',
                 'procclass':'ForwardingConsumer',
                 'spawnargs':{'attach':self.queue1,\
                              'process parameters':{},\
                              'delivery queues':{'queues':[self.queue2]}}\
                    }
        child1 = base_consumer.ConsumerDesc(**pd1)

        child1_id = yield self.test_sup.spawn_child(child1)

        dmsg = DataMessageObject()
        dmsg.notifcation = 'Junk'
        dmsg.timestamp = pu.currenttime()
        dmsg = dmsg.encode()

        yield self.test_sup.send(self.queue1, 'data', dmsg)

        yield pu.asleep(1)

        msg_cnt = yield child1.get_msg_count()
        received = msg_cnt.get('received',{})
        sent = msg_cnt.get('sent',{})
        self.assertEqual(sent.get(self.queue2),1)
        self.assertEqual(received.get(self.queue1),1)


        #Spawn another process to listen to queue 2
        pd2={'name':'consumer_number_2', \
                 'module':'ion.services.dm.distribution.consumers.forwarding_consumer',
                 'procclass':'ForwardingConsumer',\
                 'spawnargs':{'attach':self.queue2}}

        child2 = base_consumer.ConsumerDesc(**pd2)

        child2_id = yield self.test_sup.spawn_child(child2)

        # Tell the first consumer to pass results to the second!
        #res = yield child1.set_params({'queues':[self.queue2]})

        yield self.test_sup.send(self.queue1, 'data', dmsg)

        yield pu.asleep(1)

        msg_cnt = yield child1.get_msg_count()
        received = msg_cnt.get('received',{})
        sent = msg_cnt.get('sent',{})
        self.assertEqual(sent.get(self.queue2),2)
        self.assertEqual(received.get(self.queue1),2)


        msg_cnt = yield child2.get_msg_count()
        received = msg_cnt.get('received',{})
        sent = msg_cnt.get('sent')
        self.assertEqual(sent,{})
        self.assertEqual(received.get(self.queue2),1)


        yield child1.shutdown()
        yield child2.shutdown()




    @defer.inlineCallbacks
    def test_attach2_send(self):

        pd1={'name':'consumer_number_1',
                 'module':'ion.services.dm.distribution.consumers.forwarding_consumer',
                 'procclass':'ForwardingConsumer',
                 'spawnargs':{'attach':[self.queue1, self.queue2],\
                    'process parameters':{},\
                    'delivery queues':{'queues':[self.queue3]}}\
            }

        child1 = base_consumer.ConsumerDesc(**pd1)

        child1_id = yield self.test_sup.spawn_child(child1)

        dc1 = self._get_procinstance(child1_id)

        self.assertIn(self.queue1,dc1.dataReceivers)
        self.assertIn(self.queue2,dc1.dataReceivers)

        dmsg = DataMessageObject()
        dmsg.notifcation = 'Junk'
        dmsg.timestamp = pu.currenttime()
        dmsg = dmsg.encode()

        # Send to queue1
        yield self.test_sup.send(self.queue1, 'data', dmsg)

        yield pu.asleep(1)

        msg_cnt = yield child1.get_msg_count()
        received = msg_cnt.get('received',{})
        sent = msg_cnt.get('sent',{})
        self.assertEqual(sent.get(self.queue3),1)
        self.assertEqual(received.get(self.queue1),1)

        # Send to queue2
        yield self.test_sup.send(self.queue2, 'data', dmsg)

        yield pu.asleep(1)

        msg_cnt = yield child1.get_msg_count()
        received = msg_cnt.get('received',{})
        sent = msg_cnt.get('sent',{})
        self.assertEqual(sent.get(self.queue3),2)
        self.assertEqual(received.get(self.queue1),1)
        self.assertEqual(received.get(self.queue2),1)

        yield child1.shutdown()



    @defer.inlineCallbacks
    def test_deattach(self):

        raise unittest.SkipTest("Magnet does not yet support deattach.")

        pd1={'name':'consumer_number_1',
                 'module':'ion.services.dm.distribution.consumers.forwarding_consumer',
                 'procclass':'ForwardingConsumer',
                 'spawnargs':{'attach':[self.queue1],\
                              'process parameters':{},\
                              'delivery queues':{'queues':[self.queue2]}}\
                    }
        child1 = base_consumer.ConsumerDesc(**pd1)

        child1_id = yield self.test_sup.spawn_child(child1)

        dmsg = DataMessageObject()
        dmsg.notifcation = 'Junk'
        dmsg.timestamp = pu.currenttime()
        dmsg = dmsg.encode()

        yield self.test_sup.send(self.queue1, 'data', dmsg)

        msg_cnt = yield child1.get_msg_count()
        received = msg_cnt.get('received',{})
        sent = msg_cnt.get('sent',{})
        self.assertEqual(sent.get(self.queue2),1)
        self.assertEqual(received.get(self.queue1),1)

        res = yield child1.deattach(self.queue1)
        self.assertEqual(res,'OK')

        yield self.test_sup.send(self.queue1, 'data', dmsg)

        msg_cnt = yield child1.get_msg_count()
        received = msg_cnt.get('received',{})
        sent = msg_cnt.get('sent',{})
        self.assertEqual(sent.get(self.queue2),1)
        self.assertEqual(received.get(self.queue1),1)


    @defer.inlineCallbacks
    def test_digest_latest(self):
        pd1={'name':'consumer_number_1',
                 'module':'ion.services.dm.distribution.consumers.latest_consumer',
                 'procclass':'LatestConsumer',
                 'spawnargs':{'attach':self.queue1,
                              'process parameters':{},
                              'delivery queues':{'queues':[self.queue2]},
                              'delivery interval':2}
                    }
        child1 = base_consumer.ConsumerDesc(**pd1)

        child1_id = yield self.test_sup.spawn_child(child1)

        dmsg = DataMessageObject()
        dmsg.notifcation = 'Junk'
        dmsg.timestamp = pu.currenttime()
        dmsg = dmsg.encode()

        yield self.test_sup.send(self.queue1, 'data', dmsg)

        yield self.test_sup.send(self.queue1, 'data', dmsg)

        yield self.test_sup.send(self.queue1, 'data', dmsg)

        yield self.test_sup.send(self.queue1, 'data', dmsg)

        yield pu.asleep(3)

        msg_cnt = yield child1.get_msg_count()
        received = msg_cnt.get('received',{})
        sent = msg_cnt.get('sent',{})
        self.assertEqual(sent.get(self.queue2),1)
        self.assertEqual(received.get(self.queue1),4)
