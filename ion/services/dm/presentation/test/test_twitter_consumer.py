#!/usr/bin/env python
"""
@file ion/services/dm/presentation/test/test_twitter_consumer.py
@author David Stuebe
@brief test for the twitter consumer process
"""

from twisted.trial import unittest

import ion.util.ionlog
log = ion.util.ionlog.getLogger(__name__)
from ion.test.iontest import IonTestCase

from ion.services.dm.presentation import twitter_consumer
from twisted.internet import defer

from urllib2 import HTTPError

import random

class TestTwitterConsumer(IonTestCase):
    '''
    @brief Test case for Twitter.
    '''
    def setUp(self):
        self.tc = twitter_consumer.TwitterConsumer()

    def test_password_fails(self):
        raise unittest.SkipTest('Not everyone has the twitter library')
        self.failUnlessRaises(HTTPError, self.tc.ondata, 'data','note', 1.0, uname='ooidx', pword='wrong')

    def test_uname_password_fails(self):
        raise unittest.SkipTest('Not everyone has the twitter library')
        self.failUnlessRaises(HTTPError, self.tc.ondata, 'data','note', 1.0, uname='ooidx_!@#$%', pword='wrong')

    def test_tweet(self):
        val = random.randint(10000,100000) # Need to change the message
        self.tc.ondata('junk data', 'another note to tweet'+str(val), 1.0, uname='ooidx',pword='yeahright')
