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

import json
from lxml import etree
from keystone import models

Service = models.Service  # TODO(zns): remove; compatibility with logic.types


class Services(object):
    "A collection of services."

    def __init__(self, values, links):
        self.values = values
        self.links = links

    def to_xml(self):
        dom = etree.Element("services")
        dom.set(u"xmlns",
            "http://docs.openstack.org/identity/api/ext/OS-KSADM/v1.0")

        for t in self.values:
            dom.append(t.to_dom())

        for t in self.links:
            dom.append(t.to_dom())

        return etree.tostring(dom)

    def to_json(self):
        services = [t.to_dict()["OS-KSADM:service"] for t in self.values]
        services_links = [t.to_dict()["links"] for t in self.links]
        return json.dumps({"OS-KSADM:services": services,
            "OS-KSADM:services_links": services_links})
