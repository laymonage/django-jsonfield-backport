from django.test import TestCase

from .models import JSONModel


class JSONFieldTest(TestCase):
    def test_json_field_create(self):
        obj = JSONModel.objects.create(data={'foo': 'bar'})
        saved_obj = JSONModel.objects.get(id=obj.id)
        self.assertEqual(saved_obj.data, {'foo': 'bar'})
