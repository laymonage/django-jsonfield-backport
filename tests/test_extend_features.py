from unittest import mock

from django.db.backends.base.features import BaseDatabaseFeatures
from django.test import SimpleTestCase

from django_jsonfield_backport.features import extend_features

FIELD_NAME = "this_field_should_never_exist"


@mock.patch("django_jsonfield_backport.features.feature_names", [FIELD_NAME])
class ExtendFeaturesTest(SimpleTestCase):
    def test_static(self):
        """
        Test static field value to be added for known database vendor.
        """

        class DatabaseConnection:
            vendor = "postgresql"
            features = BaseDatabaseFeatures(connection=None)

        connection = DatabaseConnection()

        # Make sure the connection does not have the fake feature yet
        self.assertIs(hasattr(connection.features, FIELD_NAME), False)

        # Extend the feature set based on the connection vendor
        with mock.patch(
            "django_jsonfield_backport.features.PostgresFeatures.%s" % FIELD_NAME,
            return_value=True,
            new_callable=mock.PropertyMock,  # Mock a property instead of a method
            create=True,
        ):
            extend_features(connection=connection)

        # Make sure the fake feature has been set now
        self.assertIs(hasattr(connection.features, FIELD_NAME), True)
        self.assertIs(getattr(connection.features, FIELD_NAME), True)

    def test_callable(self):
        """
        Test callable field value to be added for known database vendor.
        """

        class DatabaseConnection:
            vendor = "postgresql"
            features = BaseDatabaseFeatures(connection=None)

        connection = DatabaseConnection()

        # Make sure the connection does not have the fake feature yet
        self.assertIs(hasattr(connection.features, FIELD_NAME), False)

        # Extend the feature set based on the connection vendor
        with mock.patch(
            "django_jsonfield_backport.features.PostgresFeatures.%s" % FIELD_NAME,
            return_value=True,  # MagicMock (default) is already a callable object
            create=True,
        ):
            extend_features(connection=connection)

        # Make sure the fake feature has been set now
        self.assertIs(hasattr(connection.features, FIELD_NAME), True)
        self.assertIs(getattr(connection.features, FIELD_NAME), True)

    def test_unknown_vendor(self):
        """
        Test that nothing gets added for an unknown database vendor.
        """

        class DatabaseConnection:
            vendor = "this_vendor_will_never_exist"
            features = BaseDatabaseFeatures(connection=None)

        connection = DatabaseConnection()

        # Make sure the connection does not have the fake feature yet
        self.assertIs(hasattr(connection.features, FIELD_NAME), False)

        # Extend the feature set based on the connection vendor
        extend_features(connection=connection)

        # Make sure the fake feature is still not there
        self.assertIs(hasattr(connection.features, FIELD_NAME), False)
