# vim: tabstop=4 shiftwidth=4 softtabstop=4
# Copyright (c) 2010-2011 OpenStack, LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import unittest2 as unittest

from keystone.test.functional import common
from keystone.backends import models
from keystone.backends import api
from keystone import utils


class ActiveDirectoryBackendTest(common.FunctionalTestCase):
    def setUp(self, *args, **kwargs):
        super(ActiveDirectoryBackendTest, self).setUp(*args, **kwargs)
        backend_module = utils.import_module('keystone.backends'
                                             '.activedirectory')
        self.assertIsInstance(backend_module,
                              keystone.backends.activedirectory)
        # Add 184.106.145.140 to hosts as AD-SQL-STUB.openstack.local for SSL
        # matching
        settings = {'server': 'AD-SQL-STUB.openstack.local',
                    'use_ssl': True,
                    'cacertfile': 'AD-SQL-STUB.pem',
                    'use_port': 636,
                    'user': 'openstack\keystone',
                    'password': 'Password1',
                    'root': 'ou=tenants,dc=openstack,dc=local',
                    'role_map': "'Admin':"
                        "'cn=Domain Admins,cn=Users,dc=openstack,dc=local'",
                    'backend_entities': "['Tenant']"}
        backend_module.configure_backend(settings)


if __name__ == '__main__':
    unittest.main()
