# vim: tabstop=4 shiftwidth=4 softtabstop=4
#
# Copyright (C) 2011 OpenStack LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

""" Tenant manager module

TODO: move functionality into here. Ex:

    def get_tenant(self, context, tenant_id):
        '''Return info for a tenant if it is valid.'''
        return self.driver.get(tenant_id)
"""

import keystone.backends.api as api


class Manager(object):
    def __init__(self, options):
        self.options = options
        self.driver = api.TENANT
