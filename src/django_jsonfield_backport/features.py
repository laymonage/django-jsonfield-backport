from django.db import connection, transaction
from django.db.backends.base.features import BaseDatabaseFeatures
from django.db.backends.signals import connection_created
from django.db.utils import OperationalError


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

feature_names = set(dir(DatabaseFeatures)) - set(dir(BaseDatabaseFeatures))


def extend_features(connection, **kwargs):
    # Database is from an unknown vendor, we don't know about the features.
    if connection.vendor not in feature_classes:
        return

    for name in feature_names:
        value = feature = getattr(feature_classes[connection.vendor], name)
        if callable(feature):
            value = feature(connection.features)
        setattr(connection.features, name, value)


def extend_default_connection():
    # For management commands and shell, another app may have already created
    # a default database connection before the signal receiver is connected,
    # so we extend_features immediately if the connection exists and is usable.
    if connection.connection and connection.is_usable():
        extend_features(connection)


def connect_signal_receivers():
    connection_created.connect(extend_features)
