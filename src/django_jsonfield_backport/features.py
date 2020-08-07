import functools
import json

from django.db import transaction
from django.db.backends.base.features import BaseDatabaseFeatures
from django.db.backends.signals import connection_created
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
    # Does the backend support __contains and __contained_by lookups for a JSONField?
    supports_json_field_contains = True
    # Does value__d__contains={'f': 'g'} (without a list around the dict) match
    # {'d': [{'f': 'g'}]}?
    json_key_contains_list_matching_requires_list = False


class MySQLFeatures(DatabaseFeatures):
    def supports_json_field(self):
        if self.connection.mysql_is_mariadb:
            return self.connection.mysql_version >= (10, 2, 7)
        return self.connection.mysql_version >= (5, 7, 8)


class OracleFeatures(DatabaseFeatures):
    supports_primitives_in_json_field = False
    supports_json_field_contains = False


class PostgresFeatures(DatabaseFeatures):
    has_native_json_field = True
    has_json_operators = True
    json_key_contains_list_matching_requires_list = True


class SQLiteFeatures(DatabaseFeatures):
    def supports_json_field(self):
        try:
            with self.connection.cursor() as cursor, transaction.atomic():
                cursor.execute('SELECT JSON(\'{"a": "b"}\')')
        except OperationalError:
            return False
        return True

    supports_json_field_contains = False


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
    "supports_json_field_contains",
    "json_key_contains_list_matching_requires_list",
]


def extend_features(connection, **kwargs):
    for name in feature_names:
        value = feature = getattr(feature_classes[connection.vendor], name)
        if callable(feature):
            value = feature(connection.features)
        setattr(connection.features, name, value)


@none_guard
def _sqlite_json_contains(haystack, needle):
    if isinstance(haystack, str):
        try:
            target = json.loads(haystack)
        except json.JSONDecodeError:
            target = haystack
    else:
        target = haystack
    if isinstance(needle, str):
        try:
            candidate = json.loads(needle)
        except json.JSONDecodeError:
            candidate = needle
    else:
        candidate = needle
    if isinstance(target, dict) and isinstance(candidate, dict):
        if target.items() >= candidate.items():
            return True
        for key, value in candidate.items():
            if key in target:
                if not _sqlite_json_contains(target[key], value):
                    return False
            else:
                return False
        return True
    if isinstance(target, list):
        if isinstance(candidate, list):
            try:
                # When possible, use superset checking for better performance.
                return set(target).issuperset(candidate)
            except TypeError:
                # Superset checking may not be possible, e.g. with nested lists.
                return all(c in target for c in candidate)
        return candidate in target
    return target == candidate


def extend_sqlite(connection, **kwargs):
    if connection.vendor != "sqlite":
        return
    if PY38:
        create_deterministic_function = functools.partial(
            connection.connection.create_function, deterministic=True,
        )
    else:
        create_deterministic_function = connection.connection.create_function
    create_deterministic_function("JSON_CONTAINS", 2, _sqlite_json_contains)


def connect_signal_receivers():
    connection_created.connect(extend_features)
    connection_created.connect(extend_sqlite)
