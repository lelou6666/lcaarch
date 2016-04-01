#!/usr/bin/env python

"""
@file ion/services/cei/provisioner/core.py
@author David LaBissoniere
@brief Starts, stops, and tracks instance and context state.
"""

import os
import time
import ion.util.ionlog
log = ion.util.ionlog.getLogger(__name__)

from itertools import izip
from twisted.internet import defer, threads

from nimboss.node import NimbusNodeDriver
from nimboss.ctx import ContextClient, BrokerError
from nimboss.cluster import ClusterDriver
from nimboss.nimbus import NimbusClusterDocument, ValidationError
from libcloud.types import NodeState as NimbossNodeState
from libcloud.base import Node as NimbossNode
from libcloud.drivers.ec2 import EC2NodeDriver, EC2USWestNodeDriver
<<<<<<< HEAD:ion/services/cei/provisioner/core.py
from ion.services.cei.provisioner.store import group_records, calc_record_age
=======
from ion.services.cei.provisioner.store import group_records
>>>>>>> refs/remotes/nimbusproject/cei:ion/services/cei/provisioner/core.py
from ion.services.cei.dtrs import DeployableTypeLookupError
from ion.services.cei import states
from ion.services.cei import cei_events

from ion.services.cei.provisioner.store import CassandraProvisionerStore

__all__ = ['ProvisionerCore', 'ProvisioningError']

_NIMBOSS_STATE_MAP = {
        NimbossNodeState.RUNNING : states.STARTED,
        NimbossNodeState.REBOOTING : states.STARTED, #TODO hmm
        NimbossNodeState.PENDING : states.PENDING,
        NimbossNodeState.TERMINATED : states.TERMINATED,
        NimbossNodeState.UNKNOWN : states.ERROR_RETRYING}

# Window of time in which nodes are allowed to be launched
# but not returned in queries to the IaaS. After this, nodes
# are assumed to be terminated out of band and marked FAILED
_IAAS_NODE_QUERY_WINDOW_SECONDS = 60

class ProvisionerCore(object):
    """Provisioner functionality that is not specific to the service.
    """

    def __init__(self, store, notifier, dtrs, site_drivers=None, context=None):
        self.store = store
        self.notifier = notifier
        self.dtrs = dtrs

        #TODO how about a config file (soon, soon...)
        self.site_drivers = site_drivers or self.setup_drivers()
        self.context = context or self._setup_context_client()

        self.cluster_driver = ClusterDriver()

    def setup_drivers(self):
        nimbus_key = os.environ['NIMBUS_KEY']
        nimbus_secret = os.environ['NIMBUS_SECRET']
        nimbus_test_driver = NimbusNodeDriver(nimbus_key, secret=nimbus_secret,
                                              host='nimbus.ci.uchicago.edu', port=8444)
        nimbus_uc_driver = NimbusNodeDriver(nimbus_key, secret=nimbus_secret,
                                            host='tp-vm1.ci.uchicago.edu', port=8445)
        nimbus_magellan_drv = NimbusNodeDriver(nimbus_key, secret=nimbus_secret,
                                               host='user04', port=8444)
        ec2_key = os.environ['AWS_ACCESS_KEY_ID']
        ec2_secret = os.environ['AWS_SECRET_ACCESS_KEY']
        ec2_east_driver = EC2NodeDriver(ec2_key, ec2_secret)
        ec2_west_driver = EC2USWestNodeDriver(ec2_key, ec2_secret)
        node_drivers = {
            'nimbus-test': nimbus_test_driver,
            'nimbus-uc': nimbus_uc_driver,
            'ec2-east': ec2_east_driver,
            'ec2-west': ec2_west_driver,
            'magellan': nimbus_magellan_drv,
        }
        return node_drivers

    def _setup_context_client(self):
        nimbus_key = os.environ['NIMBUS_KEY']
        nimbus_secret = os.environ['NIMBUS_SECRET']
        return ProvisionerContextClient(
                'https://nimbus.ci.uchicago.edu:8888/ContextBroker/ctx/',
                nimbus_key, nimbus_secret)

    @defer.inlineCallbacks
    def recover(self):
        """Finishes any incomplete launches or terminations
        """
        incomplete_launches = yield self.store.get_launches(
                state=states.REQUESTED)
        for launch in incomplete_launches:
            nodes = yield self._get_nodes_by_id(launch['node_ids'])

            log.info('Attempting recovery of incomplete launch: %s', 
                     launch['launch_id'])
            yield self.execute_provision(launch, nodes)

        terminating_launches = yield self.store.get_launches(
                state=states.TERMINATING)
        for launch in terminating_launches:
            log.info('Attempting recovery of incomplete launch termination: %s',
                     launch['launch_id'])
            yield self.terminate_launch(launch['launch_id'])

        terminating_nodes = yield self.store.get_nodes(
                state=states.TERMINATING)
        node_ids = [node['node_id'] for node in terminating_nodes]
        log.info('Attempting recovery of incomplete node terminations: %s',
                     ','.join(node_ids))
        yield self.terminate_nodes(node_ids)

    @defer.inlineCallbacks
    def prepare_provision(self, request):
        """Validates request and commits to datastore.

        If the request has subscribers, they are notified with the
        node state records.

        If the request is invalid and doesn't contain enough information
        to notify subscribers via normal channels, a ProvisioningError
        is raised. This is almost certainly a client programming error.

        If the request is well-formed but invalid, for example if the
        deployable type does not exist in the DTRS, FAILED records are
        recorded in data store and subscribers are notified.

        Returns a tuple (launch record, node records).
        """

        try:
            deployable_type = request['deployable_type']
            launch_id = request['launch_id']
            subscribers = request['subscribers']
            nodes = request['nodes']
        except KeyError,e:
            raise ProvisioningError('Invalid request. Missing key: ' + str(e))

        if not (isinstance(nodes, dict) and len(nodes) > 0):
            raise ProvisioningError('Invalid request. nodes must be a non-empty dict')

        # optional variables to sub into ctx document template
        vars = request.get('vars')

        #validate nodes and build DTRS request
        dtrs_nodes = {}
        for node_name, node in nodes.iteritems():
            try:
                dtrs_nodes[node_name] = {
                        'count' : len(node['ids']),
                        'site' : node['site'],
                        'allocation' : node['allocation']}
            except (KeyError, ValueError):
                raise ProvisioningError('Invalid request. Node %s spec is invalid' %
                        node_name)

        # from this point on, errors result in failure records, not exceptions.
        # except for, you know, bugs.
        state = states.REQUESTED
        state_description = None
        try:
            dt = yield self.dtrs.lookup(deployable_type, dtrs_nodes, vars)
            document = dt['document']
            dtrs_nodes = dt['nodes']
            log.debug('got dtrs nodes: ' + str(dtrs_nodes))
        except DeployableTypeLookupError, e:
            log.error('Failed to lookup deployable type "%s" in DTRS: %s',
                    deployable_type, str(e))
            state = states.FAILED
            state_description = "DTRS_LOOKUP_FAILED " + str(e)
            document = "N/A"

        context = None
        try:
            if state == states.REQUESTED:
                context = yield self.context.create()
                log.debug('Created new context: ' + context.uri)
        except BrokerError, e:
            log.warn('Error while creating new context for launch: %s', e)
            state = states.FAILED
            state_description = "CONTEXT_CREATE_FAILED " + str(e)

        all_node_ids = []
        launch_record = {
                'launch_id' : launch_id,
                'document' : document,
                'deployable_type' : deployable_type,
                'context' : context,
                'subscribers' : subscribers,
                'state' : state,
                'node_ids' : all_node_ids}

        node_records = []
        index = 0
        for (group_name, group) in nodes.iteritems():

            # idempotency client token. We don't have a unique identifier 
            # per launch group, so we concatenate the launch_id with an index
            token = '_'.join((str(launch_id), str(index), str(group_name)))
            index += 1

            node_ids = group['ids']
            all_node_ids.extend(node_ids)
            for node_id in node_ids:
                record = {'launch_id' : launch_id,
                        'node_id' : node_id,
                        'state' : state,
                        'state_desc' : state_description,
                        'site' : group['site'],
                        'allocation' : group['allocation'],
                        'ctx_name' : group_name,
                        'client_token' : token,
                        }
                #DTRS returns a bunch of IaaS specific info:
                # ssh key name, "real" allocation name, etc.
                # we fold it in blindly
                record.update(dtrs_nodes[group_name])
                node_records.append(record)

        yield self.store.put_launch(launch_record)
        yield self.store_and_notify(node_records, subscribers)

        defer.returnValue((launch_record, node_records))

    @defer.inlineCallbacks
    def execute_provision(self, launch, nodes):
        """Brings a launch to the PENDING state.

        Any errors or problems will result in FAILURE states
        which will be recorded in datastore and sent to subscribers.
        """

        error_state = None
        error_description = None
        try:
            yield self._really_execute_provision_request(launch, nodes)

        except ProvisioningError, e:
            log.error('Failed to execute launch. Problem: ' + str(e))
            error_state = states.FAILED
            error_description = e.message

        except Exception, e: # catch all exceptions, need to ensure nodes are marked FAILED
            log.error('Launch failed due to an unexpected error. '+
                    'This is likely a bug and should be reported. Problem: ' +
                    str(e))
            error_state = states.FAILED
            error_description = 'PROGRAMMER_ERROR '+str(e)

        if error_state:
            launch['state'] = error_state
            launch['state_desc'] = error_description

            for node in nodes:
                # some groups may have been successfully launched.
                # only mark others as failed  
                if node['state'] < states.PENDING:
                    node['state'] = error_state
                    node['state_desc'] = error_description

            #store and notify launch and nodes with FAILED states
            yield self.store.put_launch(launch)
            yield self.store_and_notify(nodes, launch['subscribers'])

    @defer.inlineCallbacks
    def _really_execute_provision_request(self, launch, nodes):
        """Brings a launch to the PENDING state.
        """
        subscribers = launch['subscribers']
        docstr = launch['document']
        context = launch['context']

        try:
            doc = NimbusClusterDocument(docstr)
        except ValidationError, e:
            raise ProvisioningError('CONTEXT_DOC_INVALID '+str(e))

        launch_groups = group_records(nodes, 'ctx_name')

        specs = doc.build_specs(context)

        # we want to fail early, before we launch anything if possible
        launch_pairs = self._validate_launch_groups(launch_groups, specs)

        has_failed = False
        #launch_pairs is a list of (spec, node list) tuples
        for launch_spec, launch_nodes in launch_pairs:

            # for recovery case
            if not any(node['state'] < states.PENDING for node in launch_nodes):
                log.info('Skipping launch group %s -- all nodes started',
                         launch_spec.name)
                continue

            newstate = None
            try:
                log.info("Launching group:\nlaunch_spec: '%s'\nlaunch_nodes: '%s'",
                         launch_spec, launch_nodes)
                yield self._launch_one_group(launch_spec, launch_nodes)

            except Exception,e:
                log.exception('Problem launching group %s: %s',
                        launch_spec.name, str(e))
                newstate = states.FAILED
                has_failed = True
                # should we have a backout of earlier groups here? or just leave it up
                # to EPU controller to decide what to do?

            if newstate:
                for node in launch_nodes:
                    node['state'] = newstate
            yield self.store_and_notify(launch_nodes, subscribers)

            if has_failed:
                break

        if has_failed:
            launch['state'] = states.FAILED
        else:
            launch['state'] = states.PENDING
        self.store.put_launch(launch)

    def _validate_launch_groups(self, groups, specs):
        if len(specs) != len(groups):
            raise ProvisioningError('INVALID_REQUEST group count mismatch '+
                    'between cluster document and request')
        pairs = []
        for spec in specs:
            group = groups.get(spec.name)
            if not group:
                raise ProvisioningError('INVALID_REQUEST missing \''+ spec.name +
                        '\' node group, present in cluster document')
            if spec.count != len(group):
                raise ProvisioningError('INVALID_REQUEST node group \''+
                        spec.name + '\' specifies ' + len(group) +
                        ' nodes, but cluster document has '+ spec.count)
            pairs.append((spec, group))
        return pairs

    @defer.inlineCallbacks
    def _launch_one_group(self, spec, nodes):
        """Launches a single group: a single IaaS request.
        """

        #assumption here is that a launch group does not span sites or
        #allocations. That may be a feature for later.

        one_node = nodes[0]
        site = one_node['site']
        driver = self.site_drivers[site]

        #set some extras in the spec
        allocstring = "default"
        allocation = one_node.get('iaas_allocation')
        if allocation:
            spec.size = allocation
            allocstring = str(allocation)
        keystring = "default"
        sshkeyname = one_node.get('iaas_sshkeyname')
        if sshkeyname:
            spec.keyname = sshkeyname
            keystring = str(sshkeyname)

        client_token = one_node.get('client_token')

        log.debug('Launching group %s - %s nodes (keypair=%s) (allocation=%s)',
                spec.name, spec.count, keystring, allocstring)

        try:
            iaas_nodes = yield threads.deferToThread(
                    self.cluster_driver.launch_node_spec, spec, driver,
                    ex_clienttoken=client_token)
        except Exception, e:
            log.exception('Error launching nodes: ' + str(e))
            # wrap this up?
            raise

        # underlying node driver may return a list or an object
        if not hasattr(iaas_nodes, '__iter__'):
            iaas_nodes = [iaas_nodes]

        if len(iaas_nodes) != len(nodes):
            message = '%s nodes from IaaS launch but %s were expected' % (
                    len(iaas_nodes), len(nodes))
            log.error(message)
            raise ProvisioningError('IAAS_PROBLEM '+ message)

        for node_rec, iaas_node in izip(nodes, iaas_nodes):
            node_rec['iaas_id'] = iaas_node.id
            # for some reason, ec2 libcloud driver places IP in a list
            #
            # if we support drivers that actually have multiple
            # public and private IPs, we will need to revisit this
            public_ip = iaas_node.public_ip
            if isinstance(public_ip, list):
                public_ip = public_ip[0]
            private_ip = iaas_node.private_ip
            if isinstance(private_ip, list):
                private_ip = private_ip[0]
            node_rec['public_ip'] = public_ip
            node_rec['private_ip'] = private_ip
            node_rec['extra'] = iaas_node.extra.copy()
            node_rec['state'] = states.PENDING
            node_rec['pending_timestamp'] = time.time()

            extradict = {'public_ip': public_ip, 'iaas_id': iaas_node.id}
            cei_events.event("provisioner", "new_node",
                             log, extra=extradict)

    @defer.inlineCallbacks
    def store_and_notify(self, records, subscribers):
        """Convenience method to store records and notify subscribers.
        """
        yield self.store.put_nodes(records)
        yield self.notifier.send_records(records, subscribers)

    @defer.inlineCallbacks
    def query_nodes(self, request):
        """Performs queries of IaaS and broker, sends updates to subscribers.
        """
        # Right now we just query everything. Could be made more granular later

        nodes = yield self.store.get_nodes(max_state=states.TERMINATING)
        site_nodes = group_records(nodes, 'site')

        for site in site_nodes:
            yield self.query_one_site(site, site_nodes[site])

        yield self.query_contexts()

    @defer.inlineCallbacks
    def query_one_site(self, site, nodes, driver=None):
        node_driver = driver or self.site_drivers[site]

        log.info('Querying site "%s"', site)
        nimboss_nodes = yield threads.deferToThread(node_driver.list_nodes)
        nimboss_nodes = dict((node.id, node) for node in nimboss_nodes)

        # note we are walking the nodes from datastore, NOT from nimboss
        for node in nodes:
            state = node['state']
            if state < states.PENDING or state >= states.TERMINATED:
                continue

            nimboss_id = node.get('iaas_id')
            nimboss_node = nimboss_nodes.pop(nimboss_id, None)
            if not nimboss_node:
                # this state is unknown to underlying IaaS. What could have
                # happened? IaaS error? Recovery from loss of net to IaaS?

                # Or lazily-updated records. On EC2, there can be a short
                # window where pending instances are not included in query
                # response

                start_time = node.get('pending_timestamp')
                now = time.time()

                if start_time and (now - start_time) <= _IAAS_NODE_QUERY_WINDOW_SECONDS:
                    log.debug('node %s: not in query of IaaS, but within '+
                            'allowed startup window (%d seconds)',
                            node['node_id'], _IAAS_NODE_QUERY_WINDOW_SECONDS)
                else:
                    log.warn('node %s: in data store but unknown to IaaS. '+
                            'Marking as terminated.', node['node_id'])

                    node['state'] = states.FAILED
                    node['state_desc'] = 'NODE_DISAPPEARED'

                    launch = yield self.store.get_launch(node['launch_id'])
                    yield self.store_and_notify([node], launch['subscribers'])
            else:
                nimboss_state = _NIMBOSS_STATE_MAP[nimboss_node.state]
                if nimboss_state > node['state']:
                    #TODO nimboss could go backwards in state.
                    node['state'] = nimboss_state

                    public_ip = nimboss_node.public_ip
                    if isinstance(public_ip, list):
                        public_ip = public_ip[0]
                    private_ip = nimboss_node.private_ip
                    if isinstance(private_ip, list):
                        private_ip = private_ip[0]
                    node['public_ip'] = public_ip
                    node['private_ip'] = private_ip

                    if nimboss_state == states.STARTED:
                        extradict = {'node_id': nimboss_id,
                                     'public_ip': public_ip,
                                     'private_ip': private_ip }
                        cei_events.event("provisioner", "node_started",
                                         log, extra=extradict)

                    launch = yield self.store.get_launch(node['launch_id'])
                    yield self.store_and_notify([node], launch['subscribers'])
        #TODO nimboss_nodes now contains any other running instances that
        # are unknown to the datastore (or were started after the query)
        # Could do some analysis of these nodes

    @defer.inlineCallbacks
    def _get_nodes_by_id(self, node_ids, skip_missing=True):
        """Helper method tp retrieve node records from a list of IDs
        """
        nodes = []
        for node_id in node_ids:
            node = yield self.store.get_node(node_id)
            # when skip_missing is false, include a None entry for missing nodes
            if node or not skip_missing:
                nodes.append(node)
        defer.returnValue(nodes)

    @defer.inlineCallbacks
    def query_contexts(self):
        """Queries all open launch contexts and sends node updates.
        """
        #grab all the launches in the pending state
        launches = yield self.store.get_launches(state=states.PENDING)

        for launch in launches:
            context = launch.get('context')
            launch_id = launch['launch_id']
            if not context:
                log.warn('Launch %s is in %s state but it has no context!',
                        launch['launch_id'], launch['state'])
                continue

            ctx_uri = context['uri']
            log.debug('Querying context %s for launch %s ', ctx_uri, launch_id)
            context_status = yield self.context.query(ctx_uri)

            ctx_nodes = context_status.nodes
            if not ctx_nodes:
                log.debug('Launch %s context has no nodes (yet)', launch_id)
                continue

            nodes = yield self._get_nodes_by_id(launch['node_ids'])
            updated_nodes = update_nodes_from_context(nodes, ctx_nodes)

            if updated_nodes:
                log.debug("%d nodes need to be updated as a result of the context query" %
                        len(updated_nodes))
                yield self.store_and_notify(updated_nodes, launch['subscribers'])

            all_done = True
            for ctx_node in ctx_nodes:
                if not (ctx_node.ok_occurred or ctx_node.error_occurred):
                    all_done = False
                    break

            if context_status.complete and all_done:
                log.info('Launch %s context is "all-ok": done!', launch_id)
                # update the launch record so this context won't be re-queried
                launch['state'] = states.RUNNING
                extradict = {'launch_id': launch_id, 'node_ids': launch['node_ids']}
                cei_events.event("provisioner", "launch_ctx_done",
                                 log, extra=extradict)
                yield self.store.put_launch(launch)

            elif context_status.complete:
                log.info('Launch %s context is "complete" (all checked in, but not all-ok)', launch_id)
            else:
                log.debug('Launch %s context is incomplete: %s of %s nodes',
                        launch_id, len(context_status.nodes),
                        context_status.expected_count)

    @defer.inlineCallbacks
    def mark_launch_terminating(self, launch_id):
        """Mark a launch as Terminating in data store.
        """
        launch = yield self.store.get_launch(launch_id)
        nodes = yield self._get_nodes_by_id(launch['node_ids'])
        updated = []
        for node in nodes:
            if node['state'] < states.TERMINATING:
                node['state'] = states.TERMINATING
                updated.append(node)
        if updated:
            yield self.store_and_notify(nodes, launch['subscribers'])
        launch['state'] = states.TERMINATING
        yield self.store.put_launch(launch)

    @defer.inlineCallbacks
    def terminate_launch(self, launch_id):
        """Destroy all nodes in a launch and mark as terminated in store.
        """
        launch = yield self.store.get_launch(launch_id)
        nodes = yield self._get_nodes_by_id(launch['node_ids'])

        for node in nodes:
            state = node['state']
            if state < states.PENDING or state >= states.TERMINATED:
                continue
            #would be nice to do this as a batch operation
            yield self._terminate_node(node, launch)

        launch['state'] = states.TERMINATED
        yield self.store.put_launch(launch)

    @defer.inlineCallbacks
    def terminate_launches(self, launch_ids):
        """Destroy all node in a set of launches.
        """
        for launch in launch_ids:
            yield self.terminate_launch(launch)

    @defer.inlineCallbacks
    def terminate_all(self):
        """Terminate all running nodes
        """
        launches = yield self.store.get_launches(max_state=states.TERMINATING)
        for launch in launches:
            yield self.mark_launch_terminating(launch['launch_id'])
            yield self.terminate_launch(launch['launch_id'])
            log.critical("terminate-all for launch '%s'" % launch['launch_id'])

    @defer.inlineCallbacks
    def mark_nodes_terminating(self, node_ids):
        """Mark a set of nodes as terminating in the data store
        """
        nodes = yield self._get_nodes_by_id(node_ids)

        launches = group_records(nodes, 'launch_id')
        for launch_id, launch_nodes in launches:
            launch = yield self.store.get_launch(launch_id)
            if not launch:
                log.warn('Failed to find launch record %s', launch_id)
                continue
            for node in launch_nodes:
                if node['state'] < states.TERMINATING:
                    node['state'] = states.TERMINATING
            yield self.store_and_notify(launch_nodes, launch['subscribers'])

    @defer.inlineCallbacks
    def terminate_nodes(self, node_ids):
        """Destroy all specified nodes.
        """
        nodes = yield self._get_nodes_by_id(node_ids, skip_missing=False)
        for node_id, node in izip(node_ids, nodes):
            if not node:
                #maybe an error should make it's way to controller from here?
                log.warn('Node %s unknown but requested for termination',
                        node_id)
                continue
            launch = yield self.store.get_launch(node['launch_id'])
            yield self._terminate_node(node, launch)

    @defer.inlineCallbacks
    def _terminate_node(self, node, launch):
        nimboss_node = self._to_nimboss_node(node)
        driver = self.site_drivers[node['site']]
        yield threads.deferToThread(driver.destroy_node, nimboss_node)
        node['state'] = states.TERMINATED

        yield self.store_and_notify([node], launch['subscribers'])

    def _to_nimboss_node(self, node):
        """Nimboss drivers need a Node object for termination.
        """
        #this is unfortunately tightly coupled with EC2 libcloud driver
        # right now. We are building a fake Node object that only has the
        # attribute needed for termination (id). Would need to be fleshed out
        # to work with other drivers.
        return NimbossNode(id=node['iaas_id'], name=None, state=None,
                public_ip=None, private_ip=None,
                driver=self.site_drivers[node['site']])

def update_nodes_from_context(nodes, ctx_nodes):
    updated_nodes = []
    for ctx_node in ctx_nodes:
        for ident in ctx_node.identities:

            match_reason = None
            match_node = None
            for node in nodes:
                if ident.ip and ident.ip == node['public_ip']:
                    match_node = node
                    match_reason = 'public IP match'
                    break
                elif ident.hostname and ident.hostname == node['public_ip']:
                    match_node = node
                    match_reason = 'nimboss IP matches ctx hostname'
                # can add more matches if needed

            if match_node:
                log.debug('Matched ctx identity to node by: ' + match_reason)

                if _update_one_node_from_ctx(match_node, ctx_node, ident):
                    updated_nodes.append(match_node)
                    break

            else:
                # this isn't necessarily an exceptional condition. could be a private
                # IP for example. Right now we are only matching against public
                log.debug('Context identity has unknown IP (%s) and hostname (%s)',
                        ident.ip, ident.hostname)
    return updated_nodes

def _update_one_node_from_ctx(node, ctx_node, identity):
    node_done = ctx_node.ok_occurred or ctx_node.error_occurred
    if not node_done or node['state'] >= states.RUNNING:
        return False
    if ctx_node.ok_occurred:
        node['state'] = states.RUNNING
        node['pubkey'] = identity.pubkey
    else:
        node['state'] = states.STARTED # should be a separate error state?
        node['state_desc'] = "CTX_ERROR"
        node['ctx_error_code'] = ctx_node.error_code
        node['ctx_error_message'] = ctx_node.error_message
    return True


class ProvisionerContextClient(object):
    """Provisioner calls to context broker.
    """
    def __init__(self, broker_uri, key, secret):
        self.client = ContextClient(broker_uri, key, secret)

    def create(self):
        """Creates a new context with the broker
        """
        return threads.deferToThread(self.client.create_context)

    def query(self, resource):
        """Queries an existing context.

        resource is the uri returned by create operation
        """
        return threads.deferToThread(self.client.get_status, resource)


class ProvisioningError(Exception):
    pass
