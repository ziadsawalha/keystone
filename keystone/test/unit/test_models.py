import json
import unittest2 as unittest
from keystone.models import Resource


class TestModels(unittest.TestCase):
    '''Unit tests for keystone/models.py.'''

    def test_resource(self):
        resource = Resource()
        self.assertEquals(str(resource.__class__),
                          "<class 'keystone.models.Resource'>",
                          "Resource should be of instance "
                          "class keystone.models.Resource but instead "
                          "was '%s'" % str(resource.__class__))
        self.assertIsInstance(resource, dict, "")

    def test_resource_static_properties(self):
        resource = Resource(id=1, name="the resource", blank=None)
        self.assertEquals(resource.id, 1)
        self.assertEquals(resource.name, "the resource")
        try:
            x = resource.some_bad_property
        except AttributeError:
            pass
        except:
            self.assert_(False, "Invalid attribute on resource should fail")

    def test_resource_json_serialization(self):
        resource = Resource(id=1, name="the resource", blank=None)
        json_str = resource.to_json()
        d1 = json.loads(json_str)
        d2 = json.loads('{"name": "the resource", "id": 1}')
        self.assertEquals(d1, d2)

    def test_resource_xml_serialization(self):
        resource = Resource(id=1, name="the resource", blank=None)
        xml_str = resource.to_xml()

    def test_resource_xml_deserialization(self):
        resource = Resource(id=1, name="the resource", blank=None)
        self.assertIsInstance(resource, Resource)

    def test_resource_json_deserialization(self):
        resource = Resource.from_json('{"name": "the resource", "id": 1}',
                            hints=[{"contract_attributes": ['id', 'name']}])
        self.assertIsInstance(resource, Resource)
        self.assertEquals(resource.id, 1)
        self.assertEquals(resource.name, "the resource")

    def test_resource_inspection(self):
        resource = Resource(id=1, name="the resource", blank=None)
        self.assertIsNone(resource.inspect())

    def test_resource_validation(self):
        resource = Resource(id=1, name="the resource", blank=None)
        self.assertTrue(resource.validate())


if __name__ == '__main__':
    unittest.main()
