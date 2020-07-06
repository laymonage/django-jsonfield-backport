import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECRET_KEY = "0xdeadbeefdeadbeef"
DEBUG = True

INSTALLED_APPS = [
    "tests",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.%s" % os.getenv("DB_BACKEND"),
        "NAME": os.getenv("DB_NAME"),
        "USER": os.getenv("DB_USER"),
        "PASSWORD": os.getenv("DB_PASSWORD"),
        "HOST": os.getenv("DB_HOST", ""),
        "PORT": os.getenv("DB_PORT", ""),
        "TEST": {
            "USER": "default_test",
            "TBLSPACE": "default_test_tbls",
            "TBLSPACE_TMP": "default_test_tbls_tmp",
        },
    },
}
DATABASE_ROUTERS = ["tests.models.MyRouter"]

SILENCED_SYSTEM_CHECKS = ["django_jsonfield_backport.W001"]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_L10N = True
USE_TZ = True
