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

""" Module that contains all object models

The models are used to hold Keystone 'business' objects and their validation,
serialization, and backend interaction code.

The models are based off of python's dict.

The uses supported are:
    # can be initialized with static properties
    tenant = Tenant(name='A1000')

    # handles writing to correct backend
    tenant.save()

    # static properties
    id = tenant.id
    tenant = None

    # can be retrieved by static property
    tenant_by_name = Tenant.get(name='A1000')

    # can be retrieved  by id default, so name not needed
    tenant_by_id = Tenant.get(id)
    assertIsEquals(tenant_by_id, tenant_by_name)

    # handles serialization
    print tenant_by_id
    print tenant_by_id.to_json()    # Keystone latest contract
    print tenant_by_id.to_json_20()  # Keystone 2.0 contract

    Serialization routines can take hints in this format:
        {"attribute": value}
        attribute/value can be:
        contract_attributes: list of contract attributeds (see initializer)
            format is an array of attributes (ex ['id', 'name'])
"""

import json
from lxml import etree


class Resource(dict):
    """ Base class for models

    Provides basic functionality that can be overridden """

    def __init__(self, *args, **kw):
        """ Initialize object
        kwargs contain static properties
        """
        super(Resource, self).__init__(*args, **kw)
        # attributes that can be used as attributes. Example:
        #    tenant.id  - here id is a contract atribute
        super(Resource, self).__setattr__("contract_attributes", [])
        if kw:
            self.contract_attributes.extend(kw.keys())
            for name, value in kw.iteritems():
                if value:
                    self.__setattr__(name, value)
                else:
                    if name in self:
                        del self[name]

    def __getattr__(self, name):
        """ Supports reading contract attributes (ex. tenant.id) """
        if name in self.contract_attributes:
            if name in self:
                return self[name]
            return None
        else:
            raise AttributeError("'%s' not found on object of class '%s'" % \
                                 (name, self.__class__.__name__))

    def __setattr__(self, name, value):
        """ Supports setting contract attributes (ex. tenant.name = 'A1') """
        if name in self.contract_attributes:
            # Go all the way back to dict and set the value
            super(dict, self).__setattr__(name, value)
        else:
            raise AttributeError("'%s' not found on object of class '%s'" % \
                                 (name, self.__class__.__name__))

    def to_json(self, hints=None):
        """ Serializes object to json - implies latest Keystone contract """
        return json.dumps(self)

    def to_xml(self, hints=None):
        """ Serializes object to XML - implies latest Keystone contract """
        dom = etree.Element(self.__class__.__name__)
        for attribute in self.contract_attributes:
            dom.set(attribute, str(self.__getattr__(attribute) or ''))
        return etree.tostring(dom)

    def to_json_20(self, hints=None):
        """ Serializes object to json - always returns Keystone 2.0
        contract """
        return self.to_json(hints=hints)

    def to_xml_20(self, hints=None):
        """ Serializes object to XML - always returns Keystone 2.0 contract """
        return self.to_xml(hints=hints)

    @classmethod
    def from_json(cls, json_str, hints=None):
        """ Deserializes object from json - assumes latest Keystone
        contract
        """
        object = json.loads(json_str)
        model_object = None
        if hints:
            for hint in hints:
                if 'contract_attributes' in hint:
                    # build mapping and instantiate object with
                    # contract_attributes provided
                    params = {}
                    for name in hint['contract_attributes']:
                        if name in object:
                            params[name] = object[name]
                        else:
                            params[name] = None
                    model_object = cls(**params)
        if model_object is None:
            model_object = cls()
        model_object.update(object)
        return model_object

    @classmethod
    def from_xml_20(cls, hints=None):
        """ Deserializes object from XML - assumes latest Keystone
        contract """
        return cls()

    @classmethod
    def from_json_20(cls, json_str, hints=None):
        """ Deserializes object from json - assumes Keystone 2.0 contract """
        return cls()

    @classmethod
    def from_xml_20(cls, hints=None):
        """ Deserializes object from XML - assumes Keystone 2.0 contract """
        return cls()

    def save(self):
        """ Handles finding correct backend and writing to it
        Supports both saving new object (create) and updating an existing one
        """
        #if self.id:
        #    #backends[find the class].create(self)
        #elif old:
        #    #backends[find the class].update(self)
        pass

    def delete(self):
        """ Handles finding correct backend and deleting object from it """
        pass

    def validate(self):
        """ Validates object attributes. Raises error if object not valid """
        errors = self.inspect(fail_fast=True)
        if errors:
            raise errors[0][0](errors[0][1])
        return errors is None

    def inspect(self, fail_fast=None):
        """ Validates and retuns validation results without raising any errors
        :param fail_fast" return after first validation failure
        results: [(faultClass, message), ...], ordered by user relevance
        """
        return None

    @classmethod
    def get(cls, id=None, *args, **kw):
        # backends[find the class].get(id, *args, **kw)
        return cls(*args, **kw)

class Service(Resource):
    def __init__(self, id=None, type=None, name=None, *args, **kw):
        super(Service, self).__init__(id=id, type=type, name=name, *args, **kw)

    def to_json_20(self):
        return super(Service, self).to_json_20()

    def inspect(self, fail_fast=None):
        result = super(Service, self).inspect(fail_fast)
        if fail_fast and result:
            return result

