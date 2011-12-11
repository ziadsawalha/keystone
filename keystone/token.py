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

""" Token manager module """

from keystone import utils
import keystone.backends.api as api


class Manager(object):
    def __init__(self, options):
        self.options = options
        self.driver = api.TOKEN

    def get_token(self, context, token_id):
        """Return info for a token if it is valid."""
        return self.driver.get(token_id)
