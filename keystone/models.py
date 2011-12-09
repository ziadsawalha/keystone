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
        [{"attribute": value}]
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
        # initialize dynamically (to prevent recursion on __setattr__)
        super(Resource, self).__setattr__("contract_attributes", [])
        # set statically for references
        self.contract_attributes = []
        if kw:
            self.contract_attributes.extend(kw.keys())
            for name, value in kw.iteritems():
                if value:
                    self.__setattr__(name, value)
                else:
                    if name in self:
                        del self[name]

    #
    # model properties
    #
    # Override built-in classes to allow for user.id (as well as user["id"])
    # for attributes defined in the Keystone contract
    #
    def __getattr__(self, name):
        """ Supports reading contract attributes (ex. tenant.id)

        This should only be called if the original call did not match
        an attribute (Python's rules)"""
        if name in self.contract_attributes:
            if name in self:
                return self[name]
            return None
        else:
            raise AttributeError("'%s' not found on object of class '%s'" % \
                                 (name, self.__class__.__name__))

    def __setattr__(self, name, value):
        """ Supports setting contract attributes (ex. tenant.name = 'A1')

        This should only be called if the original call did not match
        an attribute (Python's rules)."""
        if name in self.contract_attributes:
            # Go all the way back to the dict and set the value
            super(Resource, self).__setattr__(name, value)
        elif name == 'contract_attributes':
            # Allow someone to set that
            super(Resource, self).__setattr__(name, value)
        else:
            raise AttributeError("'%s' not found on object of class '%s'" % \
                                 (name, self.__class__.__name__))

    #
    # Validation calls
    #
    def validate(self):
        """ Validates object attributes. Raises error if object not valid

        This calls inspect() in fail_fast mode, so it gets back the first
        validation error and raises it. It is up to the code in inspect()
        to determine what validations take precedence and are returned
        first

        :returns: True if no validation errors raise"""
        errors = self.inspect(fail_fast=True)
        if errors:
            raise errors[0][0](errors[0][1])
        return errors is None

    def inspect(self, fail_fast=None):
        """ Validates and retuns validation results without raising any errors
        :param fail_fast" return after first validation failure

        :returns: [(faultClass, message), ...], ordered by relevance
            - if None, then no errors found
        """
        return None

    #
    # Serialization Functions - may be moved to a different class
    #
    @staticmethod
    def dict_to_xml(d, xml):
        """ Attempts to convert a dict into XML as best as possible.
        Converts named keys and attributes and recursively calls for
        any values are are embedded dicts"""
        for key, value in d.iteritems():
            if isinstance(value, dict):
                element = xml.Element(key)
                dict_to_xml(value, element)
            else:
                xml.set(key, str(value))

    def to_json(self, hints=None):
        """ Serializes object to json - implies latest Keystone contract """
        return json.dumps(self)

    def to_xml(self, hints=None):
        """ Serializes object to XML - implies latest Keystone contract """
        dom = etree.Element(self.__class__.__name__)
        for attribute in self.contract_attributes:
            dom.set(attribute, str(self.__getattr__(attribute) or ''))
        self.dict_to_xml(self, dom)
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

    #
    # Backend management
    #
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

    @classmethod
    def get(cls, id=None, *args, **kw):
        # backends[find the class].get(id, *args, **kw)
        return cls(*args, **kw)


class Service(Resource):
    """ Service model """
    def __init__(self, id=None, type=None, name=None, description=None,
                 *args, **kw):
        super(Service, self).__init__(id=id, type=type, name=name,
                                      description=description, *args, **kw)

    def to_json_20(self):
        return super(Service, self).to_json_20()

    def inspect(self, fail_fast=None):
        result = super(Service, self).inspect(fail_fast)
        if fail_fast and result:
            return result


class Tenant(Resource):
    """ Tenant model """
    def __init__(self, id=None, name=None, description=None, enabled=None,
                 *args, **kw):
        super(Tenant, self).__init__(id=id, name=name,
                                      description=description, enabled=enabled,
                                      *args, **kw)


class User(Resource):
    """ User model

    Attribute Notes:
    default_tenant_id (formerly tenant_id): this attribute can be enabled or
        disabled by configuration. When enabled, any authentication call
        without a tenant gets authenticated to this tenant.
    """
    def __init__(self, id=None, password=None, name=None,
                 default_tenant_id=None,
                 email=None, enabled=None,
                 *args, **kw):
        super(User, self).__init__(id=id, password=password, name=name,
                        default_tenant_id=default_tenant_id, email=email,
                        enabled=enabled, *args, **kw)


class EndpointTemplate(Resource):
    """ EndpointTemplate model """
    def __init__(self, id=None, region=None, name=None, type=None,
                 public_url=None, admin_url=None,
                 internal_url=None, enabled=None, is_global=None,
                 version_id=None, version_list=None, version_info=None,
                 *args, **kw):
        super(EndpointTemplate, self).__init__(id=id, region=region, name=name,
                 type=type, public_url=public_url, admin_url=admin_url,
                 internal_url=internal_url, enabled=enabled,
                 is_global=is_global, version_id=version_id,
                 version_list=version_list, version_info=version_info,
                                      *args, **kw)


class Endpoint(Resource):
    """ Endpoint model """
    def __init__(self, id=None, tenant_id=None, region=None, name=None,
                 type=None, public_url=None, admin_url=None,
                 internal_url=None,  version_id=None, version_list=None,
                 version_info=None,
                 *args, **kw):
        super(Endpoint, self).__init__(id=id, tenant_id=tenant_id,
                 region=region, name=name, type=type, public_url=public_url,
                 admin_url=admin_url, internal_url=internal_url,
                 version_id=version_id, version_list=version_list,
                 version_info=version_info,
                                      *args, **kw)


class Role(Resource):
    """ Role model """
    def __init__(self, id=None, name=None, description=None, service_id=None,
                 tenant_id=None, *args, **kw):
        super(Role, self).__init__(id=id, name=name, description=description,
                                   service_id=service_id, tenant_id=tenant_id,
                                    *args, **kw)


class Token(Resource):
    """ Token model """
    def __init__(self, id=None, expires=None, tenant_id=None, *args, **kw):
        super(Token, self).__init__(id=id, expires=expires,
                                    tenant_id=tenant_id, *args, **kw)
