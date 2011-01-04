#!/usr/bin/env python

import ion.util.ionlog
log = ion.util.ionlog.getLogger(__name__)

from twisted.internet import defer #, reactor
from ion.core.process.service_process import ServiceProcess, ServiceClient
from ion.core.process.process import ProcessFactory
from ion.services.cei.provisioner.store import ProvisionerStore
from ion.services.cei.provisioner.core import ProvisionerCore
from ion.services.cei.dtrs import DeployableTypeRegistryClient
from ion.services.cei import cei_events

class ProvisionerService(ServiceProcess):
    """Provisioner service interface
    """

    # Declaration of service
    declare = ServiceProcess.service_declare(name='provisioner', version='0.1.0', dependencies=[])

    def slc_init(self):
        cei_events.event("provisioner", "init_begin", log)
        self.store = ProvisionerStore()
        notifier = self.spawn_args.get('notifier')
        self.notifier = notifier or ProvisionerNotifier(self)
        self.dtrs = DeployableTypeRegistryClient(self)
        self.core = ProvisionerCore(self.store, self.notifier, self.dtrs)
        cei_events.event("provisioner", "init_end", log)

    @defer.inlineCallbacks
    def op_provision(self, content, headers, msg):
        """Service operation: Provision a taskable resource
        """
        log.debug("op_provision content:"+str(content))

        launch, nodes = yield self.core.prepare_provision(content)

        # now we can ACK the request as it is safe in datastore

        # set up a callLater to fulfill the request after the ack. Would be
        # cleaner to have explicit ack control.
        #reactor.callLater(0, self.core.execute_provision_request, launch, nodes)
        yield self.core.execute_provision(launch, nodes)

    @defer.inlineCallbacks
    def op_terminate_nodes(self, content, headers, msg):
        """Service operation: Terminate one or more nodes
        """
        log.debug('op_terminate_nodess content:'+str(content))

        #expecting one or more node IDs
        if not isinstance(content, list):
            content = [content]

        #TODO yield self.core.mark_nodes_terminating(content)

        #reactor.callLater(0, self.core.terminate_nodes, content)
        yield self.core.terminate_nodes(content)

    @defer.inlineCallbacks
    def op_terminate_launches(self, content, headers, msg):
        """Service operation: Terminate one or more launches
        """
        log.debug('op_terminate_launches content:'+str(content))

        #expecting one or more launch IDs
        if not isinstance(content, list):
            content = [content]

        for launch in content:
            yield self.core.mark_launch_terminating(launch)

        #reactor.callLater(0, self.core.terminate_launches, content)
        yield self.core.terminate_launches(content)

    @defer.inlineCallbacks
    def op_query(self, content, headers, msg):
        """Service operation: query IaaS  and send updates to subscribers.
        """
        # immediate ACK is desired
        #reactor.callLater(0, self.core.query_nodes, content)
        yield self.core.query_nodes(content)
        if msg:
            yield self.reply_ok(msg)


class ProvisionerClient(ServiceClient):
    """
    Client for provisioning deployable types
    """
    def __init__(self, proc=None, **kwargs):
        if not 'targetname' in kwargs:
            kwargs['targetname'] = "provisioner"
        ServiceClient.__init__(self, proc, **kwargs)

    @defer.inlineCallbacks
    def provision(self, launch_id, deployable_type, launch_description, vars=None):
        """Provisions a deployable type
        """
        yield self._check_init()

        nodes = {}
        for nodename, item in launch_description.iteritems():
            nodes[nodename] = {'ids' : item.instance_ids,
                    'site' : item.site,
                    'allocation' : item.allocation_id,
                    'data' : item.data}
        sa = yield self.proc.get_scoped_name('system', 'sensor_aggregator')
        request = {'deployable_type' : deployable_type,
                'launch_id' : launch_id,
                'nodes' : nodes,
                'subscribers' : [sa],
                'vars' : vars}
        log.debug('Sending provision request: ' + str(request))
        yield self.send('provision', request)

    @defer.inlineCallbacks
    def query(self, rpc=False):
        """Triggers a query operation in the provisioner. Node updates
        are not sent in reply, but are instead sent to subscribers
        (most likely a sensor aggregator).
        """
        yield self._check_init()
        log.debug('Sending query request to provisioner')
        
        # optionally send query in rpc-style, in which case this method's 
        # Deferred will not be fired util provisioner has a response from
        # all underlying IaaS. Right now this is only used in tests.
        if rpc:
            yield self.rpc_send('query', None)
        else:
            yield self.send('query', None)

    @defer.inlineCallbacks
    def terminate_launches(self, launches):
        """Terminates one or more launches
        """
        yield self._check_init()
        log.debug('Sending terminate_launches request to provisioner')
        yield self.send('terminate_launches', launches)

    @defer.inlineCallbacks
    def terminate_nodes(self, nodes):
        """Terminates one or more nodes
        """
        yield self._check_init()
        log.debug('Sending terminate_nodes request to provisioner')
        yield self.send('terminate_nodes', nodes)

class ProvisionerNotifier(object):
    """Abstraction for sending node updates to subscribers.
    """
    def __init__(self, process):
        self.process = process

    @defer.inlineCallbacks
    def send_record(self, record, subscribers, operation='node_status'):
        """Send a single node record to all subscribers.
        """
        log.debug('Sending status record about node %s to %s',
                record['node_id'], repr(subscribers))
        for sub in subscribers:
            yield self.process.send(sub, operation, record)

    @defer.inlineCallbacks
    def send_records(self, records, subscribers, operation='node_status'):
        """Send a set of node records to all subscribers.
        """
        for rec in records:
            yield self.send_record(rec, subscribers, operation)

# Spawn of the process using the module name
factory = ProcessFactory(ProvisionerService)
