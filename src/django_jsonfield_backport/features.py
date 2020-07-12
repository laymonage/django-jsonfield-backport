import functools
import json

import django
from django.db import transaction
from django.db.backends.base.features import BaseDatabaseFeatures
from django.db.backends.sqlite3.base import none_guard
from django.db.utils import OperationalError
from django.utils.version import PY38


class DatabaseFeatures(BaseDatabaseFeatures):
    # Does the backend support JSONField?
    supports_json_field = True
    # Does the backend support primitives in JSONField?
    supports_primitives_in_json_field = True
    # Is there a true datatype for JSON?
    has_native_json_field = False
    # Does the backend use PostgreSQL-style JSON operators like '->'?
    has_json_operators = False


class MySQLFeatures(DatabaseFeatures):
    def supports_json_field(self):
        if self.connection.mysql_is_mariadb:
            return self.connection.mysql_version >= (10, 2, 7)
        return self.connection.mysql_version >= (5, 7, 8)


class OracleFeatures(DatabaseFeatures):
    supports_primitives_in_json_field = False


class PostgresFeatures(DatabaseFeatures):
    has_native_json_field = True
    has_json_operators = True


class SQLiteFeatures(DatabaseFeatures):
    def supports_json_field(self):
        try:
            with self.connection.cursor() as cursor, transaction.atomic():
                cursor.execute('SELECT JSON(\'{"a": "b"}\')')
        except OperationalError:
            return False
        return True


feature_classes = {
    "mysql": MySQLFeatures,
    "oracle": OracleFeatures,
    "postgresql": PostgresFeatures,
    "sqlite": SQLiteFeatures,
}


feature_names = [
    "supports_json_field",
    "supports_primitives_in_json_field",
    "has_native_json_field",
    "has_json_operators",
]


def extend_features(connection=None, **kwargs):
    if django.VERSION >= (3, 1):
        return
    for name in feature_names:
        value = feature = getattr(feature_classes[connection.vendor], name)
        if callable(feature):
            value = feature(connection.features)
        setattr(connection.features, name, value)


@none_guard
def _sqlite_json_contains(haystack, needle):
    target, candidate = json.loads(haystack), json.loads(needle)
    if isinstance(target, dict) and isinstance(candidate, dict):
        return target.items() >= candidate.items()
    return target == candidate


def extend_sqlite(connection=None, **kwargs):
    if connection.vendor == "sqlite":
        if PY38:
            create_deterministic_function = functools.partial(
                connection.connection.create_function, deterministic=True,
            )
        else:
            create_deterministic_function = connection.connection.create_function
        create_deterministic_function("JSON_CONTAINS", 2, _sqlite_json_contains)
