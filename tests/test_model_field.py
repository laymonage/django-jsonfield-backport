import operator
import uuid
from unittest import mock, skipIf, skipUnless

import django
from django.core import serializers
from django.core.checks import Error, Warning as DjangoWarning
from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import (
    DataError,
    IntegrityError,
    NotSupportedError,
    OperationalError,
    connection,
    models,
)
from django.db.models import Count, F, OuterRef, Q, Subquery, Transform, Value
from django.db.models.expressions import RawSQL
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext

from django_jsonfield_backport import forms
from django_jsonfield_backport.features import features
from django_jsonfield_backport.models import (
    JSONCast,
    JSONField,
    KeyTextTransform,
    KeyTransform,
    KeyTransformFactory,
    KeyTransformTextLookupMixin,
)

from .models import CustomJSONDecoder, JSONModel, NullableJSONModel


@skipUnless(features[connection.vendor].supports_json_field, "Only test on supported backends.")
class JSONFieldTests(TestCase):
    def test_invalid_value(self):
        msg = "is not JSON serializable"
        with self.assertRaisesMessage(TypeError, msg):
            NullableJSONModel.objects.create(
                value={"uuid": uuid.UUID("d85e2076-b67c-4ee7-8c3a-2bf5a2cc2475")}
            )

    def test_custom_encoder_decoder(self):
        value = {"uuid": uuid.UUID("{d85e2076-b67c-4ee7-8c3a-2bf5a2cc2475}")}
        obj = NullableJSONModel(value_custom=value)
        obj.clean_fields()
        obj.save()
        obj.refresh_from_db()
        self.assertEqual(obj.value_custom, value)

    def test_db_check_constraints(self):
        value = "{@!invalid json value 123 $!@#"
        with mock.patch.object(DjangoJSONEncoder, "encode", return_value=value):
            with self.assertRaises((IntegrityError, DataError, OperationalError)):
                NullableJSONModel.objects.create(value_custom=value)


class TestMethods(SimpleTestCase):
    def test_deconstruct(self):
        field = JSONField()
        name, path, args, kwargs = field.deconstruct()
        self.assertEqual(path, "django_jsonfield_backport.models.JSONField")
        self.assertEqual(args, [])
        self.assertEqual(kwargs, {})

    def test_deconstruct_custom_encoder_decoder(self):
        field = JSONField(encoder=DjangoJSONEncoder, decoder=CustomJSONDecoder)
        name, path, args, kwargs = field.deconstruct()
        self.assertEqual(kwargs["encoder"], DjangoJSONEncoder)
        self.assertEqual(kwargs["decoder"], CustomJSONDecoder)

    @skipIf(django.VERSION >= (3, 1), "Not applicable.")
    def test_get_transforms(self):
        @JSONField.register_lookup
        class MyTransform(Transform):
            lookup_name = "my_transform"

        field = JSONField()
        transform = field.get_transform("my_transform")
        self.assertIs(transform, MyTransform)
        JSONField._unregister_lookup(MyTransform)
        JSONField._clear_cached_lookups()
        transform = field.get_transform("my_transform")
        self.assertIsInstance(transform, KeyTransformFactory)

    def test_key_transform_text_lookup_mixin_non_key_transform(self):
        transform = Transform("test")
        msg = "Transform should be an instance of KeyTransform in order to use " "this lookup."
        with self.assertRaisesMessage(TypeError, msg):
            KeyTransformTextLookupMixin(transform)


class TestValidation(SimpleTestCase):
    databases = {"default"}

    @skipIf(django.VERSION >= (3, 1), "Not applicable.")
    def test_invalid_default(self):
        class InvalidDefaultModel(models.Model):
            field = JSONField(default={})

        self.assertEqual(
            InvalidDefaultModel._meta.get_field("field").check(),
            [
                DjangoWarning(
                    msg=(
                        "JSONField default should be a callable instead of an instance "
                        "so that it's not shared between all field instances."
                    ),
                    hint="Use a callable instead, e.g., use `dict` instead of `{}`.",
                    obj=InvalidDefaultModel._meta.get_field("field"),
                    id="fields.E010",
                )
            ],
        )

    @skipIf(django.VERSION >= (3, 1), "Not applicable.")
    def test_check_jsonfield(self):
        error = Error(
            "%s does not support JSONFields." % connection.display_name,
            obj=JSONModel,
            id="fields.E180",
        )
        self.assertEqual(JSONModel.check(databases=self.databases), [])
        original_feature = features[connection.vendor].supports_json_field
        features[connection.vendor].supports_json_field = False

        class UnallowedModel(models.Model):
            field = JSONField()

        self.assertEqual(UnallowedModel.check(databases=self.databases), [])
        self.assertEqual(JSONModel.check(databases=self.databases), [error])
        features[connection.vendor].supports_json_field = original_feature

    def test_invalid_encoder(self):
        msg = "The encoder parameter must be a callable object."
        with self.assertRaisesMessage(ValueError, msg):
            JSONField(encoder=DjangoJSONEncoder())

    def test_invalid_decoder(self):
        msg = "The decoder parameter must be a callable object."
        with self.assertRaisesMessage(ValueError, msg):
            JSONField(decoder=CustomJSONDecoder())

    def test_validation_error(self):
        field = JSONField()
        msg = "Value must be valid JSON."
        value = uuid.UUID("{d85e2076-b67c-4ee7-8c3a-2bf5a2cc2475}")
        with self.assertRaisesMessage(ValidationError, msg):
            field.clean({"uuid": value}, None)

    def test_custom_encoder(self):
        field = JSONField(encoder=DjangoJSONEncoder)
        value = uuid.UUID("{d85e2076-b67c-4ee7-8c3a-2bf5a2cc2475}")
        field.clean({"uuid": value}, None)


class TestFormField(SimpleTestCase):
    @skipIf(django.VERSION >= (3, 1), "Not applicable.")
    def test_formfield(self):
        model_field = JSONField()
        form_field = model_field.formfield()
        self.assertIsInstance(form_field, forms.JSONField)

    def test_formfield_custom_encoder_decoder(self):
        model_field = JSONField(encoder=DjangoJSONEncoder, decoder=CustomJSONDecoder)
        form_field = model_field.formfield()
        self.assertIs(form_field.encoder, DjangoJSONEncoder)
        self.assertIs(form_field.decoder, CustomJSONDecoder)


class TestSerialization(SimpleTestCase):
    test_data = '[{"fields": {"value": %s}, ' '"model": "tests.jsonmodel", "pk": null}]'
    test_values = (
        # (Python value, serialized value),
        ({"a": "b", "c": None}, '{"a": "b", "c": null}'),
        ("abc", '"abc"'),
        ('{"a": "a"}', '"{\\"a\\": \\"a\\"}"'),
    )

    def test_dumping(self):
        for value, serialized in self.test_values:
            with self.subTest(value=value):
                instance = JSONModel(value=value)
                data = serializers.serialize("json", [instance])
                self.assertJSONEqual(data, self.test_data % serialized)

    def test_loading(self):
        for value, serialized in self.test_values:
            with self.subTest(value=value):
                instance = list(serializers.deserialize("json", self.test_data % serialized))[
                    0
                ].object
                self.assertEqual(instance.value, value)


@skipUnless(features[connection.vendor].supports_json_field, "Only test on supported backends.")
class TestSaveLoad(TestCase):
    def test_null(self):
        obj = NullableJSONModel(value=None)
        obj.save()
        obj.refresh_from_db()
        self.assertIsNone(obj.value)

    @skipUnless(
        features[connection.vendor].supports_primitives_in_json_field,
        "Only test on supported backends.",
    )
    def test_json_null_different_from_sql_null(self):
        json_null = NullableJSONModel.objects.create(value=Value("null"))
        json_null.refresh_from_db()
        sql_null = NullableJSONModel.objects.create(value=None)
        sql_null.refresh_from_db()
        # 'null' is not equal to NULL in the database.
        self.assertSequenceEqual(
            NullableJSONModel.objects.filter(value=Value("null")), [json_null],
        )
        self.assertSequenceEqual(
            NullableJSONModel.objects.filter(value=None), [json_null],
        )
        self.assertSequenceEqual(
            NullableJSONModel.objects.filter(value__isnull=True), [sql_null],
        )
        # 'null' is equal to NULL in Python (None).
        self.assertEqual(json_null.value, sql_null.value)

    @skipUnless(
        features[connection.vendor].supports_primitives_in_json_field,
        "Only test on supported backends.",
    )
    def test_primitives(self):
        values = [
            True,
            1,
            1.45,
            "String",
            "",
        ]
        for value in values:
            with self.subTest(value=value):
                obj = JSONModel(value=value)
                obj.save()
                obj.refresh_from_db()
                self.assertEqual(obj.value, value)

    def test_dict(self):
        values = [
            {},
            {"name": "John", "age": 20, "height": 180.3},
            {"a": True, "b": {"b1": False, "b2": None}},
        ]
        for value in values:
            with self.subTest(value=value):
                obj = JSONModel.objects.create(value=value)
                obj.refresh_from_db()
                self.assertEqual(obj.value, value)

    def test_list(self):
        values = [
            [],
            ["John", 20, 180.3],
            [True, [False, None]],
        ]
        for value in values:
            with self.subTest(value=value):
                obj = JSONModel.objects.create(value=value)
                obj.refresh_from_db()
                self.assertEqual(obj.value, value)

    def test_realistic_object(self):
        value = {
            "name": "John",
            "age": 20,
            "pets": [
                {"name": "Kit", "type": "cat", "age": 2},
                {"name": "Max", "type": "dog", "age": 1},
            ],
            "courses": [["A1", "A2", "A3"], ["B1", "B2"], ["C1"]],
        }
        obj = JSONModel.objects.create(value=value)
        obj.refresh_from_db()
        self.assertEqual(obj.value, value)


@skipUnless(features[connection.vendor].supports_json_field, "Only test on supported backends.")
class TestQuerying(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.primitives = [True, False, "yes", 7, 9.6]
        values = [
            None,
            [],
            {},
            {"a": "b", "c": 14},
            {
                "a": "b",
                "c": 14,
                "d": ["e", {"f": "g"}],
                "h": True,
                "i": False,
                "j": None,
                "k": {"l": "m"},
                "n": [None],
            },
            [1, [2]],
            {"k": True, "l": False},
            {
                "foo": "bar",
                "baz": {"a": "b", "c": "d"},
                "bar": ["foo", "bar"],
                "bax": {"foo": "bar"},
            },
        ]
        cls.objs = [NullableJSONModel.objects.create(value=value) for value in values]
        if features[connection.vendor].supports_primitives_in_json_field:
            cls.objs.extend(
                [NullableJSONModel.objects.create(value=value) for value in cls.primitives]
            )
        cls.raw_sql = "%s::jsonb" if connection.vendor == "postgresql" else "%s"

    def test_exact(self):
        self.assertSequenceEqual(
            NullableJSONModel.objects.filter(value__exact={}), [self.objs[2]],
        )

    def test_exact_complex(self):
        self.assertSequenceEqual(
            NullableJSONModel.objects.filter(value__exact={"a": "b", "c": 14}), [self.objs[3]],
        )

    def test_isnull(self):
        self.assertSequenceEqual(
            NullableJSONModel.objects.filter(value__isnull=True), [self.objs[0]],
        )

    def test_ordering_by_transform(self):
        objs = [
            NullableJSONModel.objects.create(value={"ord": 93, "name": "bar"}),
            NullableJSONModel.objects.create(value={"ord": 22.1, "name": "foo"}),
            NullableJSONModel.objects.create(value={"ord": -1, "name": "baz"}),
            NullableJSONModel.objects.create(value={"ord": 21.931902, "name": "spam"}),
            NullableJSONModel.objects.create(value={"ord": -100291029, "name": "eggs"}),
        ]
        query = NullableJSONModel.objects.filter(value__name__isnull=False).order_by("value__ord")
        expected = [objs[4], objs[2], objs[3], objs[1], objs[0]]
        mariadb = connection.vendor == "mysql" and connection.mysql_is_mariadb
        if mariadb or connection.vendor == "oracle":
            # MariaDB and Oracle return JSON values as strings.
            expected = [objs[2], objs[4], objs[3], objs[1], objs[0]]
        self.assertSequenceEqual(query, expected)

    def test_ordering_grouping_by_key_transform(self):
        base_qs = NullableJSONModel.objects.filter(value__d__0__isnull=False)
        for qs in (
            base_qs.order_by("value__d__0"),
            base_qs.annotate(key=KeyTransform("0", KeyTransform("d", "value"))).order_by("key"),
        ):
            self.assertSequenceEqual(qs, [self.objs[4]])
        qs = NullableJSONModel.objects.filter(value__isnull=False)
        self.assertQuerysetEqual(
            qs.filter(value__isnull=False)
            .annotate(key=KeyTextTransform("f", KeyTransform("1", KeyTransform("d", "value"))))
            .values("key")
            .annotate(count=Count("key"))
            .order_by("count"),
            [(None, 0), ("g", 1)],
            operator.itemgetter("key", "count"),
        )

    @skipIf(
        connection.vendor == "oracle", "Oracle doesn't support grouping by LOBs, see #24096.",
    )
    def test_ordering_grouping_by_count(self):
        qs = (
            NullableJSONModel.objects.filter(value__isnull=False,)
            .values("value__d__0")
            .annotate(count=Count("value__d__0"))
            .order_by("count")
        )
        self.assertQuerysetEqual(qs, [1, 11], operator.itemgetter("count"))

    def test_key_transform_raw_expression(self):
        expr = RawSQL(self.raw_sql, ['{"x": "bar"}'])
        self.assertSequenceEqual(
            NullableJSONModel.objects.filter(value__foo=KeyTransform("x", expr)), [self.objs[7]],
        )

    def test_nested_key_transform_raw_expression(self):
        expr = RawSQL(self.raw_sql, ['{"x": {"y": "bar"}}'])
        self.assertSequenceEqual(
            NullableJSONModel.objects.filter(
                value__foo=KeyTransform("y", KeyTransform("x", expr))
            ),
            [self.objs[7]],
        )

    def test_key_transform_expression(self):
        self.assertSequenceEqual(
            NullableJSONModel.objects.filter(value__d__0__isnull=False)
            .annotate(key=KeyTransform("d", "value"))
            .annotate(
                chain=KeyTransform("0", "key"),
                expr=KeyTransform("0", JSONCast("key", JSONField())),
            )
            .filter(chain=F("expr")),
            [self.objs[4]],
        )

    def test_nested_key_transform_expression(self):
        self.assertSequenceEqual(
            NullableJSONModel.objects.filter(value__d__0__isnull=False)
            .annotate(key=KeyTransform("d", "value"))
            .annotate(
                chain=KeyTransform("f", KeyTransform("1", "key")),
                expr=KeyTransform("f", KeyTransform("1", JSONCast("key", JSONField()))),
            )
            .filter(chain=F("expr")),
            [self.objs[4]],
        )

    def test_has_key(self):
        self.assertSequenceEqual(
            NullableJSONModel.objects.filter(value__has_key="a"), [self.objs[3], self.objs[4]],
        )

    def test_has_key_null_value(self):
        self.assertSequenceEqual(
            NullableJSONModel.objects.filter(value__has_key="j"), [self.objs[4]],
        )

    def test_has_key_deep(self):
        tests = [
            (Q(value__baz__has_key="a"), self.objs[7]),
            (Q(value__has_key=KeyTransform("a", KeyTransform("baz", "value"))), self.objs[7]),
            (Q(value__has_key=KeyTransform("c", KeyTransform("baz", "value"))), self.objs[7]),
            (Q(value__d__1__has_key="f"), self.objs[4]),
            (
                Q(value__has_key=KeyTransform("f", KeyTransform("1", KeyTransform("d", "value")))),
                self.objs[4],
            ),
        ]
        for condition, expected in tests:
            with self.subTest(condition=condition):
                self.assertSequenceEqual(
                    NullableJSONModel.objects.filter(condition), [expected],
                )

    def test_has_key_list(self):
        obj = NullableJSONModel.objects.create(value=[{"a": 1}, {"b": "x"}])
        tests = [
            Q(value__1__has_key="b"),
            Q(value__has_key=KeyTransform("b", KeyTransform(1, "value"))),
            Q(value__has_key=KeyTransform("b", KeyTransform("1", "value"))),
        ]
        for condition in tests:
            with self.subTest(condition=condition):
                self.assertSequenceEqual(
                    NullableJSONModel.objects.filter(condition), [obj],
                )

    def test_has_keys(self):
        self.assertSequenceEqual(
            NullableJSONModel.objects.filter(value__has_keys=["a", "c", "h"]), [self.objs[4]],
        )

    def test_has_any_keys(self):
        self.assertSequenceEqual(
            NullableJSONModel.objects.filter(value__has_any_keys=["c", "l"]),
            [self.objs[3], self.objs[4], self.objs[6]],
        )

    def test_contains(self):
        tests = [
            ({}, self.objs[2:5] + self.objs[6:8]),
            ({"baz": {"a": "b", "c": "d"}}, [self.objs[7]]),
            ({"k": True, "l": False}, [self.objs[6]]),
            ({"d": ["e", {"f": "g"}]}, [self.objs[4]]),
            ([1, [2]], [self.objs[5]]),
            ({"n": [None]}, [self.objs[4]]),
            ({"j": None}, [self.objs[4]]),
        ]
        for value, expected in tests:
            with self.subTest(value=value):
                qs = NullableJSONModel.objects.filter(value__contains=value)
                self.assertSequenceEqual(qs, expected)

    @skipUnless(
        features[connection.vendor].supports_primitives_in_json_field,
        "Only test on supported backends.",
    )
    def test_contains_primitives(self):
        for value in self.primitives:
            with self.subTest(value=value):
                qs = NullableJSONModel.objects.filter(value__contains=value)
                self.assertIs(qs.exists(), True)

    @skipIf(
        connection.vendor == "oracle", "Oracle doesn't support contained_by lookup.",
    )
    def test_contained_by(self):
        qs = NullableJSONModel.objects.filter(value__contained_by={"a": "b", "c": 14, "h": True})
        self.assertSequenceEqual(qs, self.objs[2:4])

    @skipUnless(
        connection.vendor == "oracle", "Oracle doesn't support contained_by lookup.",
    )
    def test_contained_by_unsupported(self):
        msg = "contained_by lookup is not supported on Oracle."
        with self.assertRaisesMessage(NotSupportedError, msg):
            NullableJSONModel.objects.filter(value__contained_by={"a": "b"}).get()

    def test_deep_values(self):
        qs = NullableJSONModel.objects.values_list("value__k__l")
        expected_objs = [(None,)] * len(self.objs)
        expected_objs[4] = ("m",)
        self.assertSequenceEqual(qs, expected_objs)

    @skipUnless(
        features[connection.vendor].can_distinct_on_fields, "Only test on supported backends.",
    )
    def test_deep_distinct(self):
        query = NullableJSONModel.objects.distinct("value__k__l").values_list("value__k__l")
        self.assertSequenceEqual(query, [("m",), (None,)])

    def test_isnull_key(self):
        # key__isnull=False works the same as has_key='key'.
        self.assertSequenceEqual(
            NullableJSONModel.objects.filter(value__a__isnull=True), self.objs[:3] + self.objs[5:],
        )
        self.assertSequenceEqual(
            NullableJSONModel.objects.filter(value__a__isnull=False), [self.objs[3], self.objs[4]],
        )
        self.assertSequenceEqual(
            NullableJSONModel.objects.filter(value__j__isnull=False), [self.objs[4]],
        )

    def test_isnull_key_or_none(self):
        obj = NullableJSONModel.objects.create(value={"a": None})
        self.assertSequenceEqual(
            NullableJSONModel.objects.filter(Q(value__a__isnull=True) | Q(value__a=None)),
            self.objs[:3] + self.objs[5:] + [obj],
        )

    def test_none_key(self):
        self.assertSequenceEqual(
            NullableJSONModel.objects.filter(value__j=None), [self.objs[4]],
        )

    def test_none_deep(self):
        obj = NullableJSONModel.objects.create(value={"foo": {"bar": None}})
        self.assertSequenceEqual(
            NullableJSONModel.objects.filter(value__foo__bar=None), [obj],
        )

    def test_none_key_exclude(self):
        obj = NullableJSONModel.objects.create(value={"j": 1})
        if connection.vendor == "oracle":
            # Oracle supports filtering JSON objects with NULL keys, but the
            # current implementation doesn't support it.
            self.assertSequenceEqual(
                NullableJSONModel.objects.exclude(value__j=None),
                self.objs[1:4] + self.objs[5:] + [obj],
            )
        else:
            self.assertSequenceEqual(NullableJSONModel.objects.exclude(value__j=None), [obj])

    def test_shallow_list_lookup(self):
        self.assertSequenceEqual(
            NullableJSONModel.objects.filter(value__0=1), [self.objs[5]],
        )

    def test_shallow_obj_lookup(self):
        self.assertSequenceEqual(
            NullableJSONModel.objects.filter(value__a="b"), [self.objs[3], self.objs[4]],
        )

    def test_obj_subquery_lookup(self):
        qs = NullableJSONModel.objects.annotate(
            field=Subquery(NullableJSONModel.objects.filter(pk=OuterRef("pk")).values("value")),
        ).filter(field__a="b")
        self.assertSequenceEqual(qs, [self.objs[3], self.objs[4]])

    def test_deep_lookup_objs(self):
        self.assertSequenceEqual(
            NullableJSONModel.objects.filter(value__k__l="m"), [self.objs[4]],
        )

    def test_shallow_lookup_obj_target(self):
        self.assertSequenceEqual(
            NullableJSONModel.objects.filter(value__k={"l": "m"}), [self.objs[4]],
        )

    def test_deep_lookup_array(self):
        self.assertSequenceEqual(
            NullableJSONModel.objects.filter(value__1__0=2), [self.objs[5]],
        )

    def test_deep_lookup_mixed(self):
        self.assertSequenceEqual(
            NullableJSONModel.objects.filter(value__d__1__f="g"), [self.objs[4]],
        )

    def test_deep_lookup_transform(self):
        self.assertSequenceEqual(
            NullableJSONModel.objects.filter(value__c__gt=2), [self.objs[3], self.objs[4]],
        )
        self.assertSequenceEqual(
            NullableJSONModel.objects.filter(value__c__gt=2.33), [self.objs[3], self.objs[4]],
        )
        self.assertIs(NullableJSONModel.objects.filter(value__c__lt=5).exists(), False)

    @skipIf(
        connection.vendor == "oracle", "Raises ORA-00600: internal error code on Oracle 18.",
    )
    def test_usage_in_subquery(self):
        self.assertSequenceEqual(
            NullableJSONModel.objects.filter(
                id__in=NullableJSONModel.objects.filter(value__c=14),
            ),
            self.objs[3:5],
        )

    def test_key_iexact(self):
        self.assertIs(NullableJSONModel.objects.filter(value__foo__iexact="BaR").exists(), True)
        self.assertIs(NullableJSONModel.objects.filter(value__foo__iexact='"BaR"').exists(), False)

    def test_key_contains(self):
        self.assertIs(NullableJSONModel.objects.filter(value__foo__contains="ar").exists(), True)

    def test_key_icontains(self):
        self.assertIs(NullableJSONModel.objects.filter(value__foo__icontains="Ar").exists(), True)

    def test_key_startswith(self):
        self.assertIs(NullableJSONModel.objects.filter(value__foo__startswith="b").exists(), True)

    def test_key_istartswith(self):
        self.assertIs(NullableJSONModel.objects.filter(value__foo__istartswith="B").exists(), True)

    def test_key_endswith(self):
        self.assertIs(NullableJSONModel.objects.filter(value__foo__endswith="r").exists(), True)

    def test_key_iendswith(self):
        self.assertIs(NullableJSONModel.objects.filter(value__foo__iendswith="R").exists(), True)

    def test_key_regex(self):
        self.assertIs(NullableJSONModel.objects.filter(value__foo__regex=r"^bar$").exists(), True)

    def test_key_iregex(self):
        self.assertIs(NullableJSONModel.objects.filter(value__foo__iregex=r"^bAr$").exists(), True)

    @skipUnless(
        features[connection.vendor].has_json_operators,
        "A separate test exists for backends with no json operators.",
    )
    def test_key_sql_injection(self):
        with CaptureQueriesContext(connection) as queries:
            self.assertIs(
                NullableJSONModel.objects.filter(
                    **{"""value__test' = '"a"') OR 1 = 1 OR ('d""": "x"}
                ).exists(),
                False,
            )
        self.assertIn(
            """."value" -> 'test'' = ''"a"'') OR 1 = 1 OR (''d') = '"x"' """, queries[0]["sql"],
        )

    @skipIf(
        features[connection.vendor].has_json_operators,
        "A separate test exists for backends with json operators.",
    )
    def test_key_sql_injection_escape(self):
        query = str(
            JSONModel.objects.filter(**{"""value__test") = '"a"' OR 1 = 1 OR ("d""": "x"}).query
        )
        self.assertIn('"test\\"', query)
        self.assertIn('\\"d', query)

    def test_key_escape(self):
        obj = NullableJSONModel.objects.create(value={"%total": 10})
        self.assertEqual(NullableJSONModel.objects.filter(**{"value__%total": 10}).get(), obj)

    def test_none_key_and_exact_lookup(self):
        self.assertSequenceEqual(
            NullableJSONModel.objects.filter(value__a="b", value__j=None), [self.objs[4]],
        )

    def test_lookups_with_key_transform(self):
        tests = (
            ("value__d__contains", "e"),
            ("value__baz__has_key", "c"),
            ("value__baz__has_keys", ["a", "c"]),
            ("value__baz__has_any_keys", ["a", "x"]),
            ("value__contains", KeyTransform("bax", "value")),
            ("value__has_key", KeyTextTransform("foo", "value")),
        )
        # contained_by lookup is not supported on Oracle.
        if connection.vendor != "oracle":
            tests += (
                ("value__baz__contained_by", {"a": "b", "c": "d", "e": "f"}),
                (
                    "value__contained_by",
                    KeyTransform(
                        "x", RawSQL(self.raw_sql, ['{"x": {"a": "b", "c": 1, "d": "e"}}']),
                    ),
                ),
            )
        for lookup, value in tests:
            with self.subTest(lookup=lookup):
                self.assertIs(NullableJSONModel.objects.filter(**{lookup: value}).exists(), True)
