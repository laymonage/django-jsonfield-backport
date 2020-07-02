from django.db import models

from django_jsonfield_backport.models import JSONField


class JSONModel(models.Model):
    data = JSONField()
