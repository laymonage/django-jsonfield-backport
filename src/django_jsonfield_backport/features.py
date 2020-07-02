import operator

from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.db.backends.base.features import BaseDatabaseFeatures
from django.db.backends.sqlite3.base import DatabaseFeatures as BaseSQLiteFeatures
from django.db.utils import OperationalError
from django.utils.functional import cached_property

try:
    from django.db.backends.mysql.base import DatabaseFeatures as BaseMySQLFeatures
except ImproperlyConfigured:
    BaseMySQLFeatures = BaseDatabaseFeatures

try:
    from django.db.backends.oracle.base import DatabaseFeatures as BaseOracleFeatures
except ImproperlyConfigured:
    BaseOracleFeatures = BaseDatabaseFeatures

try:
    from django.db.backends.postgresql.base import DatabaseFeatures as BasePostgresFeatures
except ImproperlyConfigured:
    BasePostgresFeatures = BaseDatabaseFeatures


class MySQLFeatures(BaseMySQLFeatures):

    @cached_property
    def supports_column_check_constraints(self):
        if self.connection.mysql_is_mariadb:
            return self.connection.mysql_version >= (10, 2, 1)
        return self.connection.mysql_version >= (8, 0, 16)

    supports_table_check_constraints = property(operator.attrgetter('supports_column_check_constraints'))

    @cached_property
    def can_introspect_check_constraints(self):
        if self.connection.mysql_is_mariadb:
            version = self.connection.mysql_version
            return (version >= (10, 2, 22) and version < (10, 3)) or version >= (10, 3, 10)
        return self.connection.mysql_version >= (8, 0, 16)

    @cached_property
    def supports_json_field(self):
        if self.connection.mysql_is_mariadb:
            return self.connection.mysql_version >= (10, 2, 7)
        return self.connection.mysql_version >= (5, 7, 8)

    @cached_property
    def can_introspect_json_field(self):
        if self.connection.mysql_is_mariadb:
            return self.supports_json_field and self.can_introspect_check_constraints
        return self.supports_json_field

    supports_primitives_in_json_field = True
    has_native_json_field = False
    has_json_operators = False


class OracleFeatures(BaseOracleFeatures):
    supports_json_field = True
    supports_primitives_in_json_field = False
    can_introspect_json_field = True
    has_native_json_field = False
    has_json_operators = False


class PostgresFeatures(BasePostgresFeatures):
    supports_json_field = True
    supports_primitives_in_json_field = True
    can_introspect_json_field = True
    has_native_json_field = True
    has_json_operators = True


class SQLiteFeatures(BaseSQLiteFeatures):

    @cached_property
    def supports_json_field(self):
        try:
            with self.connection.cursor() as cursor, transaction.atomic():
                cursor.execute('SELECT JSON(\'{"a": "b"}\')')
        except OperationalError:
            return False
        return True

    supports_primitives_in_json_field = True
    can_introspect_json_field = property(operator.attrgetter('supports_json_field'))
    has_native_json_field = False
    has_json_operators = False


features = {
    'mysql': MySQLFeatures,
    'oracle': OracleFeatures,
    'postgresql': PostgresFeatures,
    'sqlite': SQLiteFeatures,
}
