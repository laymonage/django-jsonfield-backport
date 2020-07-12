import django
from django.apps import AppConfig
from django.utils.translation import ugettext_lazy as _

from django_jsonfield_backport import features, models


class JSONFieldConfig(AppConfig):
    name = "django_jsonfield_backport"
    verbose_name = _("JSONField backport from Django 3.1")

    def ready(self):
        if django.VERSION >= (3, 1):
            return
        features.connect_signal_receivers()
        models.register_lookups()
