from unittest import skipUnless

import django
from django.core.checks import Warning as DjangoWarning
from django.test import SimpleTestCase

from django_jsonfield_backport import forms, models

from .models import JSONModel


@skipUnless(django.VERSION >= (3, 1), "Only show deprecation message for Django >= 3.1.")
class DeprecationTests(SimpleTestCase):
    def test_model_field_deprecation_message(self):
        self.assertEqual(
            JSONModel().check(),
            [
                DjangoWarning(
                    "You are using Django 3.1 or newer, which already has a built-in JSONField.",
                    hint="Use django.db.models.JSONField instead.",
                    obj=JSONModel._meta.get_field("value"),
                    id="django_jsonfield_backport.W001",
                ),
            ],
        )

    def test_form_field_deprecation_message(self):
        msg = (
            "You are using Django 3.1 or newer, which already has a built-in JSONField. "
            "Use django.forms.JSONField instead."
        )
        with self.assertWarnsMessage(ImportWarning, msg):
            forms.JSONField()

    def test_key_transform_deprecation_message(self):
        msg = (
            "You are using Django 3.1 or newer, which already has a built-in KeyTransform. "
            "Use django.db.models.fields.json.KeyTransform instead."
        )
        with self.assertWarnsMessage(ImportWarning, msg):
            models.KeyTransform("foo", "bar")

    def test_key_text_transform_deprecation_message(self):
        msg = (
            "You are using Django 3.1 or newer, which already has a built-in "
            "KeyTextTransform. Use django.db.models.fields.json.KeyTextTransform instead."
        )
        with self.assertWarnsMessage(ImportWarning, msg):
            models.KeyTextTransform("foo", "bar")
