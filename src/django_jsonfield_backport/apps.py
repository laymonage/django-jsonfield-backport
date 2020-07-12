from django.apps import AppConfig
from django.db.backends.signals import connection_created
from django.utils.translation import ugettext_lazy as _

from django_jsonfield_backport import features


class JSONFieldConfig(AppConfig):
    name = "django_jsonfield_backport"
    verbose_name = _("JSONField backport from Django 3.1")

    def ready(self):
        connection_created.connect(features.extend_features)
        connection_created.connect(features.extend_sqlite)
