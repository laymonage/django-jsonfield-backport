from unittest import skipIf

import django
from django.core.checks import Error, Warning as DjangoWarning
from django.db import connection, models
from django.test import TestCase, skipUnlessDBFeature
from django.test.utils import isolate_apps

from django_jsonfield_backport.models import JSONField


@isolate_apps("tests")
@skipIf(django.VERSION >= (3, 1), "Not applicable.")
class CheckTests(TestCase):
    @skipUnlessDBFeature("supports_json_field")
    def test_ordering_pointing_to_json_field_value(self):
        class Model(models.Model):
            field = JSONField()

            class Meta:
                ordering = ["field__value"]

        self.assertEqual(Model.check(databases=self.databases), [])

    def test_check_jsonfield_router_migrate_not_allowed(self):
        class UnallowedModel(models.Model):
            field = JSONField()

        self.assertEqual(UnallowedModel.check(databases=self.databases), [])

    def test_check_jsonfield(self):
        class Model(models.Model):
            field = JSONField()

        error = Error(
            "%s does not support JSONFields." % connection.display_name,
            obj=Model,
            id="fields.E180",
        )

        expected = [] if connection.features.supports_json_field else [error]
        self.assertEqual(Model.check(databases=self.databases), expected)

    def test_check_jsonfield_required_db_features(self):
        class Model(models.Model):
            field = JSONField()

            class Meta:
                required_db_features = {"supports_json_field"}

        self.assertEqual(Model.check(databases=self.databases), [])


@isolate_apps("tests")
@skipUnlessDBFeature("supports_json_field")
@skipIf(django.VERSION >= (3, 1), "Not applicable.")
class DefaultTests(TestCase):
    def test_invalid_default(self):
        class Model(models.Model):
            field = JSONField(default={})

        self.assertEqual(
            Model._meta.get_field("field").check(),
            [
                DjangoWarning(
                    msg=(
                        "JSONField default should be a callable instead of an "
                        "instance so that it's not shared between all field "
                        "instances."
                    ),
                    hint=("Use a callable instead, e.g., use `dict` instead of `{}`."),
                    obj=Model._meta.get_field("field"),
                    id="fields.E010",
                )
            ],
        )

    def test_valid_default(self):
        class Model(models.Model):
            field = JSONField(default=dict)

        self.assertEqual(Model._meta.get_field("field").check(), [])

    def test_valid_default_none(self):
        class Model(models.Model):
            field = JSONField(default=None)

        self.assertEqual(Model._meta.get_field("field").check(), [])

    def test_valid_callable_default(self):
        def callable_default():
            return {"it": "works"}

        class Model(models.Model):
            field = JSONField(default=callable_default)

        self.assertEqual(Model._meta.get_field("field").check(), [])
