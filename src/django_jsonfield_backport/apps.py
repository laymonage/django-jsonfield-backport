from django import VERSION as django_version
from django.apps import AppConfig

if django_version >= (3, 0):
    from django.utils.translation import gettext_lazy as _
else:
    from django.utils.translation import ugettext_lazy as _

from django_jsonfield_backport import features, forms, models


class JSONFieldConfig(AppConfig):
    name = "django_jsonfield_backport"
    verbose_name = _("JSONField backport from Django 3.1")

    def ready(self):
        if django_version >= (3, 1):
            return
        features.extend_default_connection()
        features.connect_signal_receivers()
        forms.patch_admin()
        models.register_lookups()
