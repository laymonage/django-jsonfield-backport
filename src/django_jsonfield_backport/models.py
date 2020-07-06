import json
import warnings

import django
from django.core import checks, exceptions
from django.db import NotSupportedError, connections, router
from django.db.models import lookups
from django.db.models.fields import Field
from django.db.models.functions import Cast
from django.db.models.lookups import FieldGetDbPrepValueMixin, Lookup, Transform
from django.utils.translation import gettext_lazy as _

from . import forms
from .features import features

__all__ = ["JSONField"]


class CheckFieldDefaultMixin:
    _default_hint = ("<valid default>", "<invalid default>")

    def _check_default(self):
        if self.has_default() and self.default is not None and not callable(self.default):
            return [
                checks.Warning(
                    "%s default should be a callable instead of an instance "
                    "so that it's not shared between all field instances."
                    % (self.__class__.__name__,),
                    hint=(
                        "Use a callable instead, e.g., use `%s` instead of "
                        "`%s`." % self._default_hint
                    ),
                    obj=self,
                    id="fields.E010",
                )
            ]
        else:
            return []

    def check(self, **kwargs):
        errors = super().check(**kwargs)
        errors.extend(self._check_default())
        return errors


if django.VERSION >= (3, 1):
    from django.db.models import JSONField as BuiltinJSONField

    class JSONField(BuiltinJSONField):
        system_check_deprecated_details = {
            "msg": "You are using Django 3.1 or newer, which already has a built-in JSONField.",
            "hint": "Use django.db.models.JSONField instead.",
            "id": "django_jsonfield_backport.W001",
        }


else:

    class JSONField(CheckFieldDefaultMixin, Field):
        empty_strings_allowed = False
        description = _("A JSON object")
        default_error_messages = {
            "invalid": _("Value must be valid JSON."),
        }
        _default_hint = ("dict", "{}")

        def __init__(self, verbose_name=None, name=None, encoder=None, decoder=None, **kwargs):
            if encoder and not callable(encoder):
                raise ValueError("The encoder parameter must be a callable object.")
            if decoder and not callable(decoder):
                raise ValueError("The decoder parameter must be a callable object.")
            self.encoder = encoder
            self.decoder = decoder
            super().__init__(verbose_name, name, **kwargs)

        def check(self, **kwargs):
            errors = super().check(**kwargs)
            databases = kwargs.get("databases") or []
            errors.extend(self._check_supported(databases))
            return errors

        def _check_supported(self, databases):
            errors = []
            for db in databases:
                if not router.allow_migrate_model(db, self.model):
                    continue
                connection = connections[db]
                if not (
                    "supports_json_field" in self.model._meta.required_db_features
                    or features[connection.vendor].supports_json_field
                ):
                    errors.append(
                        checks.Error(
                            "%s does not support JSONFields." % connection.display_name,
                            obj=self.model,
                            id="fields.E180",
                        )
                    )
            return errors

        def deconstruct(self):
            name, path, args, kwargs = super().deconstruct()
            if self.encoder is not None:
                kwargs["encoder"] = self.encoder
            if self.decoder is not None:
                kwargs["decoder"] = self.decoder
            return name, path, args, kwargs

        def from_db_value(self, value, expression, connection):
            if value is None:
                return value
            if features[connection.vendor].has_native_json_field and self.decoder is None:
                return value
            try:
                return json.loads(value, cls=self.decoder)
            except json.JSONDecodeError:
                return value

        def db_check(self, connection):
            data = self.db_type_parameters(connection)
            if connection.vendor == "mysql":
                if connection.mysql_is_mariadb and connection.mysql_version < (10, 4, 3):
                    return "JSON_VALID(`%(column)s`)" % data
            if connection.vendor == "oracle":
                return "%(qn_column)s IS JSON" % data
            if connection.vendor == "sqlite":
                return '(JSON_VALID("%(column)s") OR "%(column)s" IS NULL)' % data
            return None

        def db_type(self, connection):
            db_types = {
                "mysql": "json",
                "oracle": "nclob",
                "postgresql": "jsonb",
                "sqlite": "text",
            }
            return db_types[connection.vendor]

        def get_db_converters(self, connection):
            if connection.vendor == "oracle":
                return [
                    connection.ops.convert_textfield_value,
                    *super().get_db_converters(connection),
                ]
            return super().get_db_converters(connection)

        def get_prep_value(self, value):
            if value is None:
                return value
            return json.dumps(value, cls=self.encoder)

        def get_transform(self, name):
            transform = super().get_transform(name)
            if transform:
                return transform
            return KeyTransformFactory(name)

        def select_format(self, compiler, sql, params):
            if self.decoder is not None:
                if compiler.connection.vendor == "postgresql":
                    return "(%s)::text" % sql, params
            return super().select_format(compiler, sql, params)

        def validate(self, value, model_instance):
            super().validate(value, model_instance)
            try:
                json.dumps(value, cls=self.encoder)
            except TypeError:
                raise exceptions.ValidationError(
                    self.error_messages["invalid"], code="invalid", params={"value": value},
                )

        def value_to_string(self, obj):
            return self.value_from_object(obj)

        def formfield(self, **kwargs):
            return super().formfield(
                **{
                    "form_class": forms.JSONField,
                    "encoder": self.encoder,
                    "decoder": self.decoder,
                    **kwargs,
                }
            )


class JSONCast(Cast):
    def as_mysql(self, compiler, connection, **extra_context):
        template = None
        if connection.mysql_is_mariadb:
            template = "JSON_EXTRACT(%(expressions)s, '$')"
        return super().as_sql(compiler, connection, template=template, **extra_context)

    def as_oracle(self, compiler, connection, **extra_context):
        template = "JSON_QUERY(%(expressions)s, '$')"
        return super().as_sql(compiler, connection, template=template, **extra_context)


def compile_json_path(key_transforms, include_root=True):
    path = ["$"] if include_root else []
    for key_transform in key_transforms:
        try:
            num = int(key_transform)
        except ValueError:  # non-integer
            path.append(".")
            path.append(json.dumps(key_transform))
        else:
            path.append("[%s]" % num)
    return "".join(path)


class PostgresOperatorLookup(FieldGetDbPrepValueMixin, Lookup):
    """Lookup defined by operators on PostgreSQL."""

    postgres_operator = None

    def as_postgresql(self, compiler, connection):
        lhs, lhs_params = self.process_lhs(compiler, connection)
        rhs, rhs_params = self.process_rhs(compiler, connection)
        params = tuple(lhs_params) + tuple(rhs_params)
        return "%s %s %s" % (lhs, self.postgres_operator, rhs), params


class DataContains(PostgresOperatorLookup):
    lookup_name = "contains"
    postgres_operator = "@>"

    def as_sql(self, compiler, connection):
        lhs, lhs_params = self.process_lhs(compiler, connection)
        rhs, rhs_params = self.process_rhs(compiler, connection)
        params = tuple(lhs_params) + tuple(rhs_params)
        return "JSON_CONTAINS(%s, %s)" % (lhs, rhs), params

    def as_oracle(self, compiler, connection):
        if isinstance(self.rhs, KeyTransform):
            return HasKey(self.lhs, self.rhs).as_oracle(compiler, connection)
        lhs, lhs_params = self.process_lhs(compiler, connection)
        params = tuple(lhs_params)
        sql = "JSON_QUERY(%s, '$%s' WITH WRAPPER) = " "JSON_QUERY('%s', '$.value' WITH WRAPPER)"
        rhs = json.loads(self.rhs)
        if isinstance(rhs, dict):
            if not rhs:
                return "DBMS_LOB.SUBSTR(%s) LIKE '{%%%%}'" % lhs, params
            return (
                " AND ".join(
                    [
                        sql % (lhs, ".%s" % json.dumps(key), json.dumps({"value": value}))
                        for key, value in rhs.items()
                    ]
                ),
                params,
            )
        return sql % (lhs, "", json.dumps({"value": rhs})), params


class ContainedBy(PostgresOperatorLookup):
    lookup_name = "contained_by"
    postgres_operator = "<@"

    def as_sql(self, compiler, connection):
        lhs, lhs_params = self.process_lhs(compiler, connection)
        rhs, rhs_params = self.process_rhs(compiler, connection)
        params = tuple(rhs_params) + tuple(lhs_params)
        return "JSON_CONTAINS(%s, %s)" % (rhs, lhs), params

    def as_oracle(self, compiler, connection):
        raise NotSupportedError("contained_by lookup is not supported on Oracle.")


class HasKeyLookup(PostgresOperatorLookup):
    logical_operator = None

    def as_sql(self, compiler, connection, template=None):
        # Process JSON path from the left-hand side.
        if isinstance(self.lhs, KeyTransform):
            lhs, lhs_params, lhs_key_transforms = self.lhs.preprocess_lhs(compiler, connection)
            lhs_json_path = compile_json_path(lhs_key_transforms)
        else:
            lhs, lhs_params = self.process_lhs(compiler, connection)
            lhs_json_path = "$"
        sql = template % lhs
        # Process JSON path from the right-hand side.
        rhs = self.rhs
        rhs_params = []
        if not isinstance(rhs, (list, tuple)):
            rhs = [rhs]
        for key in rhs:
            if isinstance(key, KeyTransform):
                *_, rhs_key_transforms = key.preprocess_lhs(compiler, connection)
            else:
                rhs_key_transforms = [key]
            rhs_params.append(
                "%s%s" % (lhs_json_path, compile_json_path(rhs_key_transforms, include_root=False))
            )
        # Add condition for each key.
        if self.logical_operator:
            sql = "(%s)" % self.logical_operator.join([sql] * len(rhs_params))
        return sql, tuple(lhs_params) + tuple(rhs_params)

    def as_mysql(self, compiler, connection):
        return self.as_sql(compiler, connection, template="JSON_CONTAINS_PATH(%s, 'one', %%s)")

    def as_oracle(self, compiler, connection):
        sql, params = self.as_sql(compiler, connection, template="JSON_EXISTS(%s, '%%s')")
        # Add paths directly into SQL because path expressions cannot be passed
        # as bind variables on Oracle.
        return sql % tuple(params), []

    def as_postgresql(self, compiler, connection):
        if isinstance(self.rhs, KeyTransform):
            *_, rhs_key_transforms = self.rhs.preprocess_lhs(compiler, connection)
            for key in rhs_key_transforms[:-1]:
                self.lhs = KeyTransform(key, self.lhs)
            self.rhs = rhs_key_transforms[-1]
        return super().as_postgresql(compiler, connection)

    def as_sqlite(self, compiler, connection):
        return self.as_sql(compiler, connection, template="JSON_TYPE(%s, %%s) IS NOT NULL")


class HasKey(HasKeyLookup):
    lookup_name = "has_key"
    postgres_operator = "?"
    prepare_rhs = False


class HasKeys(HasKeyLookup):
    lookup_name = "has_keys"
    postgres_operator = "?&"
    logical_operator = " AND "

    def get_prep_lookup(self):
        return [str(item) for item in self.rhs]


class HasAnyKeys(HasKeys):
    lookup_name = "has_any_keys"
    postgres_operator = "?|"
    logical_operator = " OR "


class JSONExact(lookups.Exact):
    can_use_none_as_rhs = True

    def process_lhs(self, compiler, connection):
        lhs, lhs_params = super().process_lhs(compiler, connection)
        if connection.vendor == "sqlite":
            rhs, rhs_params = super().process_rhs(compiler, connection)
            if rhs == "%s" and rhs_params == [None]:
                # Use JSON_TYPE instead of JSON_EXTRACT for NULLs.
                lhs = "JSON_TYPE(%s, '$')" % lhs
        elif connection.vendor == "oracle":
            lhs = "DBMS_LOB.SUBSTR(%s)" % lhs
        return lhs, lhs_params

    def process_rhs(self, compiler, connection):
        rhs, rhs_params = super().process_rhs(compiler, connection)
        # Treat None lookup values as null.
        if rhs == "%s" and rhs_params == [None]:
            rhs_params = ["null"]
        if connection.vendor == "mysql":
            func = ["JSON_EXTRACT(%s, '$')"] * len(rhs_params)
            rhs = rhs % tuple(func)
        return rhs, rhs_params


if django.VERSION < (3, 1):
    JSONField.register_lookup(DataContains)
    JSONField.register_lookup(ContainedBy)
    JSONField.register_lookup(HasKey)
    JSONField.register_lookup(HasKeys)
    JSONField.register_lookup(HasAnyKeys)
    JSONField.register_lookup(JSONExact)

if django.VERSION >= (3, 1):
    from django.db.models.fields.json import (
        KeyTextTransform as BuiltinKeyTextTransform,
        KeyTransform as BuiltinKeyTransform,
    )

    class KeyTransform(BuiltinKeyTransform):
        def __init__(self, *args, **kwargs):
            warnings.warn(
                "You are using Django 3.1 or newer, which already has a built-in KeyTransform. "
                "Use django.db.models.fields.json.KeyTransform instead.",
                ImportWarning,
                stacklevel=2,
            )
            super().__init__(*args, **kwargs)

    class KeyTextTransform(BuiltinKeyTextTransform):
        def __init__(self, *args, **kwargs):
            warnings.warn(
                "You are using Django 3.1 or newer, which already has a built-in "
                "KeyTextTransform. Use django.db.models.fields.json.KeyTextTransform instead.",
                ImportWarning,
                stacklevel=2,
            )
            super().__init__(*args, **kwargs)


else:

    class KeyTransform(Transform):
        postgres_operator = "->"
        postgres_nested_operator = "#>"

        def __init__(self, key_name, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.key_name = str(key_name)

        def preprocess_lhs(self, compiler, connection, lhs_only=False):
            if not lhs_only:
                key_transforms = [self.key_name]
            previous = self.lhs
            while isinstance(previous, KeyTransform):
                if not lhs_only:
                    key_transforms.insert(0, previous.key_name)
                previous = previous.lhs
            lhs, params = compiler.compile(previous)
            if connection.vendor == "oracle":
                # Escape string-formatting.
                key_transforms = [key.replace("%", "%%") for key in key_transforms]
            return (lhs, params, key_transforms) if not lhs_only else (lhs, params)

        def as_mysql(self, compiler, connection):
            lhs, params, key_transforms = self.preprocess_lhs(compiler, connection)
            json_path = compile_json_path(key_transforms)
            return "JSON_EXTRACT(%s, %%s)" % lhs, tuple(params) + (json_path,)

        def as_oracle(self, compiler, connection):
            lhs, params, key_transforms = self.preprocess_lhs(compiler, connection)
            json_path = compile_json_path(key_transforms)
            return (
                ("COALESCE(JSON_QUERY(%s, '%s'), JSON_VALUE(%s, '%s'))" % ((lhs, json_path) * 2)),
                tuple(params) * 2,
            )

        def as_postgresql(self, compiler, connection):
            lhs, params, key_transforms = self.preprocess_lhs(compiler, connection)
            if len(key_transforms) > 1:
                return (
                    "(%s %s %%s)" % (lhs, self.postgres_nested_operator),
                    params + [key_transforms],
                )
            try:
                lookup = int(self.key_name)
            except ValueError:
                lookup = self.key_name
            return "(%s %s %%s)" % (lhs, self.postgres_operator), tuple(params) + (lookup,)

        def as_sqlite(self, compiler, connection):
            lhs, params, key_transforms = self.preprocess_lhs(compiler, connection)
            json_path = compile_json_path(key_transforms)
            return "JSON_EXTRACT(%s, %%s)" % lhs, tuple(params) + (json_path,)

    class KeyTextTransform(KeyTransform):
        postgres_operator = "->>"
        postgres_nested_operator = "#>>"


class KeyTransformTextLookupMixin:
    """
    Mixin for combining with a lookup expecting a text lhs from a JSONField
    key lookup. On PostgreSQL, make use of the ->> operator instead of casting
    key values to text and performing the lookup on the resulting
    representation.
    """

    def process_lhs(self, compiler, connection):
        lhs, lhs_params = super().process_lhs(compiler, connection)
        if connection.vendor == "mysql":
            return "JSON_UNQUOTE(%s)" % lhs, lhs_params
        return lhs, lhs_params

    def __init__(self, key_transform, *args, **kwargs):
        if not isinstance(key_transform, KeyTransform):
            raise TypeError(
                "Transform should be an instance of KeyTransform in order to " "use this lookup."
            )
        key_text_transform = KeyTextTransform(
            key_transform.key_name, *key_transform.source_expressions, **key_transform.extra
        )
        super().__init__(key_text_transform, *args, **kwargs)


class CaseInsensitiveMixin:
    """
    Mixin to allow case-insensitive comparison of JSON values on MySQL.
    MySQL handles strings used in JSON context using the utf8mb4_bin collation.
    Because utf8mb4_bin is a binary collation, comparison of JSON values is
    case-sensitive.
    """

    def process_lhs(self, compiler, connection):
        lhs, lhs_params = super().process_lhs(compiler, connection)
        if connection.vendor == "mysql":
            return "LOWER(%s)" % lhs, lhs_params
        return lhs, lhs_params

    def process_rhs(self, compiler, connection):
        rhs, rhs_params = super().process_rhs(compiler, connection)
        if connection.vendor == "mysql":
            return "LOWER(%s)" % rhs, rhs_params
        return rhs, rhs_params


class KeyTransformIsNull(lookups.IsNull):
    # key__isnull=False is the same as has_key='key'
    def as_oracle(self, compiler, connection):
        if not self.rhs:
            return HasKey(self.lhs.lhs, self.lhs.key_name).as_oracle(compiler, connection)
        return super().as_sql(compiler, connection)

    def as_sqlite(self, compiler, connection):
        if not self.rhs:
            return HasKey(self.lhs.lhs, self.lhs.key_name).as_sqlite(compiler, connection)
        return super().as_sql(compiler, connection)


class KeyTransformExact(JSONExact):
    def process_lhs(self, compiler, connection):
        lhs, lhs_params = super().process_lhs(compiler, connection)
        if connection.vendor == "sqlite":
            rhs, rhs_params = super().process_rhs(compiler, connection)
            if rhs == "%s" and rhs_params == ["null"]:
                lhs, _ = self.lhs.preprocess_lhs(compiler, connection, lhs_only=True)
                lhs = "JSON_TYPE(%s, %%s)" % lhs
        elif connection.vendor == "mysql" and connection.mysql_is_mariadb:
            lhs = "JSON_UNQUOTE(%s)" % lhs
        return lhs, lhs_params

    def process_rhs(self, compiler, connection):
        if isinstance(self.rhs, KeyTransform):
            return super(lookups.Exact, self).process_rhs(compiler, connection)
        rhs, rhs_params = super().process_rhs(compiler, connection)
        if connection.vendor == "oracle":
            func = []
            for value in rhs_params:
                value = json.loads(value)
                function = "JSON_QUERY" if isinstance(value, (list, dict)) else "JSON_VALUE"
                func.append("%s('%s', '$.value')" % (function, json.dumps({"value": value})))
            rhs = rhs % tuple(func)
            rhs_params = []
        elif connection.vendor == "sqlite":
            func = ["JSON_EXTRACT(%s, '$')" if value != "null" else "%s" for value in rhs_params]
            rhs = rhs % tuple(func)
        return rhs, rhs_params

    def as_oracle(self, compiler, connection):
        rhs, rhs_params = super().process_rhs(compiler, connection)
        if rhs_params == ["null"]:
            # Field has key and it's NULL.
            has_key_expr = HasKey(self.lhs.lhs, self.lhs.key_name)
            has_key_sql, has_key_params = has_key_expr.as_oracle(compiler, connection)
            is_null_expr = self.lhs.get_lookup("isnull")(self.lhs, True)
            is_null_sql, is_null_params = is_null_expr.as_sql(compiler, connection)
            return (
                "%s AND %s" % (has_key_sql, is_null_sql),
                tuple(has_key_params) + tuple(is_null_params),
            )
        return super().as_sql(compiler, connection)


class KeyTransformIExact(CaseInsensitiveMixin, KeyTransformTextLookupMixin, lookups.IExact):
    pass


class KeyTransformIContains(CaseInsensitiveMixin, KeyTransformTextLookupMixin, lookups.IContains):
    pass


class KeyTransformContains(KeyTransformTextLookupMixin, lookups.Contains):
    pass


class KeyTransformStartsWith(KeyTransformTextLookupMixin, lookups.StartsWith):
    pass


class KeyTransformIStartsWith(
    CaseInsensitiveMixin, KeyTransformTextLookupMixin, lookups.IStartsWith
):
    pass


class KeyTransformEndsWith(KeyTransformTextLookupMixin, lookups.EndsWith):
    pass


class KeyTransformIEndsWith(CaseInsensitiveMixin, KeyTransformTextLookupMixin, lookups.IEndsWith):
    pass


class KeyTransformRegex(KeyTransformTextLookupMixin, lookups.Regex):
    pass


class KeyTransformIRegex(CaseInsensitiveMixin, KeyTransformTextLookupMixin, lookups.IRegex):
    pass


class KeyTransformNumericLookupMixin:
    def process_rhs(self, compiler, connection):
        rhs, rhs_params = super().process_rhs(compiler, connection)
        if not features[connection.vendor].has_native_json_field:
            rhs_params = [json.loads(value) for value in rhs_params]
        return rhs, rhs_params


class KeyTransformLt(KeyTransformNumericLookupMixin, lookups.LessThan):
    pass


class KeyTransformLte(KeyTransformNumericLookupMixin, lookups.LessThanOrEqual):
    pass


class KeyTransformGt(KeyTransformNumericLookupMixin, lookups.GreaterThan):
    pass


class KeyTransformGte(KeyTransformNumericLookupMixin, lookups.GreaterThanOrEqual):
    pass


if django.VERSION < (3, 1):
    KeyTransform.register_lookup(KeyTransformExact)
    KeyTransform.register_lookup(KeyTransformIExact)
    KeyTransform.register_lookup(KeyTransformIsNull)
    KeyTransform.register_lookup(KeyTransformContains)
    KeyTransform.register_lookup(KeyTransformIContains)
    KeyTransform.register_lookup(KeyTransformStartsWith)
    KeyTransform.register_lookup(KeyTransformIStartsWith)
    KeyTransform.register_lookup(KeyTransformEndsWith)
    KeyTransform.register_lookup(KeyTransformIEndsWith)
    KeyTransform.register_lookup(KeyTransformRegex)
    KeyTransform.register_lookup(KeyTransformIRegex)

    KeyTransform.register_lookup(KeyTransformLt)
    KeyTransform.register_lookup(KeyTransformLte)
    KeyTransform.register_lookup(KeyTransformGt)
    KeyTransform.register_lookup(KeyTransformGte)


class KeyTransformFactory:
    def __init__(self, key_name):
        self.key_name = key_name

    def __call__(self, *args, **kwargs):
        return KeyTransform(self.key_name, *args, **kwargs)
