import json
from lxml import etree
import unittest2 as unittest

from keystone.models import Endpoint
from keystone.test import utils as testutils


class TestModelsEndpoint(unittest.TestCase):
    '''Unit tests for keystone/models.py:Endpoint class.'''

    def test_endpoint(self):
        endpoint = Endpoint()
        self.assertEquals(str(endpoint.__class__),
                          "<class 'keystone.models.Endpoint'>",
                          "endpoint should be of instance "
                          "class keystone.models.Endpoint but instead "
                          "was '%s'" % str(endpoint.__class__))
        self.assertIsInstance(endpoint, dict, "")

    def test_endpoint_static_properties(self):
        endpoint = Endpoint(id=1, name="the endpoint", enabled=True,
                            blank=None)
        self.assertEquals(endpoint.id, 1)
        self.assertEquals(endpoint.name, "the endpoint")
        self.assertTrue(endpoint.enabled)
        self.assertEquals(endpoint.admin_url, None)
        try:
            x = endpoint.some_bad_property
        except AttributeError:
            pass
        except:
            self.assert_(False, "Invalid attribute on endpoint should fail")

    def test_endpoint_properties(self):
        endpoint = Endpoint(id=1, name="the endpoint", blank=None)
        endpoint["dynamic"] = "test"
        self.assertEquals(endpoint["dynamic"], "test")

    def test_endpoint_json_serialization(self):
        endpoint = Endpoint(id=1, name="the endpoint", blank=None)
        endpoint["dynamic"] = "test"
        json_str = endpoint.to_json()
        d1 = json.loads(json_str)
        d2 = json.loads('{"name": "the endpoint", \
                          "id": 1, "dynamic": "test"}')
        self.assertEquals(d1, d2)

    def test_endpoint_xml_serialization(self):
        endpoint = Endpoint(id=1, name="the endpoint", blank=None)
        xml_str = endpoint.to_xml()
        self.assertTrue(testutils.XMLTools.xmlEqual(xml_str,
                        '<Endpoint name="the endpoint" version_info="" \
                        tenant_id="" admin_url="" public_url="" \
                        internal_url="" version_id="" blank="" region="" \
                        version_list="" type="" id="1"/>'))

    def test_endpoint_json_deserialization(self):
        endpoint = Endpoint.from_json('{"name": "the endpoint", "id": 1}',
                            hints=[{"contract_attributes": ['id', 'name']}])
        self.assertIsInstance(endpoint, Endpoint)
        self.assertEquals(endpoint.id, 1)
        self.assertEquals(endpoint.name, "the endpoint")

    def test_endpoint_xml_deserialization(self):
        endpoint = Endpoint(id=1, name="the endpoint", blank=None)
        self.assertIsInstance(endpoint, Endpoint)

    def test_endpoint_inspection(self):
        endpoint = Endpoint(id=1, name="the endpoint", blank=None)
        self.assertIsNone(endpoint.inspect())

    def test_endpoint_validation(self):
        endpoint = Endpoint(id=1, name="the endpoint", blank=None)
        self.assertTrue(endpoint.validate())


if __name__ == '__main__':
    unittest.main()
