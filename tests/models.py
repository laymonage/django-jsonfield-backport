import json
import uuid

from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

from django_jsonfield_backport.models import JSONField


class CustomJSONDecoder(json.JSONDecoder):
    def __init__(self, object_hook=None, *args, **kwargs):
        return super().__init__(object_hook=self.as_uuid, *args, **kwargs)

    def as_uuid(self, dct):
        if 'uuid' in dct:
            dct['uuid'] = uuid.UUID(dct['uuid'])
        return dct


class JSONModel(models.Model):
    value = JSONField()


class NullableJSONModel(models.Model):
    value = JSONField(blank=True, null=True)
    value_custom = JSONField(
        encoder=DjangoJSONEncoder,
        decoder=CustomJSONDecoder,
        null=True,
    )
