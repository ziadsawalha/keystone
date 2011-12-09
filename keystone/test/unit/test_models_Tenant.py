import json
from lxml import etree
import unittest2 as unittest

from keystone.models import Tenant
from keystone.test import utils as testutils


class TestModelsTenant(unittest.TestCase):
    '''Unit tests for keystone/models.py:Tenant class.'''

    def test_tenant(self):
        tenant = Tenant()
        self.assertEquals(str(tenant.__class__),
                          "<class 'keystone.models.Tenant'>",
                          "tenant should be of instance "
                          "class keystone.models.Tenant but instead "
                          "was '%s'" % str(tenant.__class__))
        self.assertIsInstance(tenant, dict, "")

    def test_tenant_static_properties(self):
        tenant = Tenant(id=1, name="the tenant", enabled=True, blank=None)
        self.assertEquals(tenant.id, 1)
        self.assertEquals(tenant.name, "the tenant")
        self.assertTrue(tenant.enabled)
        self.assertEquals(tenant.description, None)
        try:
            x = tenant.some_bad_property
        except AttributeError:
            pass
        except:
            self.assert_(False, "Invalid attribute on tenant should fail")

    def test_tenant_properties(self):
        tenant = Tenant(id=1, name="the tenant", blank=None)
        tenant["dynamic"] = "test"
        self.assertEquals(tenant["dynamic"], "test")

    def test_tenant_json_serialization(self):
        tenant = Tenant(id=1, name="the tenant", blank=None)
        tenant["dynamic"] = "test"
        json_str = tenant.to_json()
        d1 = json.loads(json_str)
        d2 = json.loads('{"name": "the tenant", \
                          "id": 1, "dynamic": "test"}')
        self.assertEquals(d1, d2)

    def test_tenant_xml_serialization(self):
        tenant = Tenant(id=1, name="the tenant", blank=None)
        xml_str = tenant.to_xml()
        self.assertTrue(testutils.XMLTools.xmlEqual(xml_str,
                        '<Tenant blank="" enabled="" id="1" \
                        name="the tenant" description=""/>'))

    def test_tenant_json_deserialization(self):
        tenant = Tenant.from_json('{"name": "the tenant", "id": 1}',
                            hints=[{"contract_attributes": ['id', 'name']}])
        self.assertIsInstance(tenant, Tenant)
        self.assertEquals(tenant.id, 1)
        self.assertEquals(tenant.name, "the tenant")

    def test_tenant_xml_deserialization(self):
        tenant = Tenant(id=1, name="the tenant", blank=None)
        self.assertIsInstance(tenant, Tenant)

    def test_tenant_inspection(self):
        tenant = Tenant(id=1, name="the tenant", blank=None)
        self.assertIsNone(tenant.inspect())

    def test_tenant_validation(self):
        tenant = Tenant(id=1, name="the tenant", blank=None)
        self.assertTrue(tenant.validate())


if __name__ == '__main__':
    unittest.main()
