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

""" User manager module """

import logging

import keystone.backends.api as api

logger = logging.getLogger(__name__)


class Manager(object):
    def __init__(self, options):
        self.options = options
        self.driver = api.USER

    def create(self, user):
        return self.driver.create(user)

    def get(self, user_id):
        """ Returns user by ID """
        return self.driver.get(user_id)

    def get_by_name(self, name):
        """ Returns user by name """
        return self.driver.get_by_name(name=name)

    def get_by_email(self, email):
        """ Returns user by email """
        return self.driver.get_by_email(email=email)

    def users_get_page(self, marker, limit):
        return self.driver.users_get_page(marker, limit)

    def users_get_page_markers(self, marker, limit):
        return self.driver.users_get_page_markers(marker, limit)

    def users_get_by_tenant_get_page(self, 
            tenant_id, role_id, marker, limit):
        return self.driver.users_get_by_tenant_get_page(
            tenant_id, role_id, marker, limit)

    def users_get_by_tenant_get_page_markers(self, 
                    tenant_id, role_id, marker, limit):
        return self.driver.users_get_by_tenant_get_page_markers(
                    tenant_id, role_id, marker, limit)

    def update(self, user):
        """ Update user """
        return self.driver.update(user['id'], user)

    def delete(self, user_id):
        self.driver.delete(user_id)
