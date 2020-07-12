=========================
django-jsonfield-backport
=========================

.. image:: https://img.shields.io/pypi/v/django-jsonfield-backport.svg
   :target: https://pypi.org/project/django-jsonfield-backport/

.. image:: https://img.shields.io/pypi/l/django-jsonfield-backport
   :target: https://github.com/laymonage/django-jsonfield-backport/blob/master/LICENSE

.. image:: https://github.com/laymonage/django-jsonfield-backport/workflows/Test/badge.svg
   :target: https://github.com/laymonage/django-jsonfield-backport/actions?workflow=Test

.. image:: https://coveralls.io/repos/laymonage/django-jsonfield-backport/badge.svg
   :target: https://coveralls.io/r/laymonage/django-jsonfield-backport

.. image:: https://img.shields.io/badge/code%20style-black-000000.svg
   :target: https://github.com/python/black

|

Backport of the cross-DB `JSONField`__ model and form fields from Django 3.1.

.. __: https://docs.djangoproject.com/en/dev/releases/3.1/#jsonfield-for-all-supported-database-backends

.. code-block:: python

    from django.db import models
    from django_jsonfield_backport.models import JSONField

    class ContactInfo(models.Model):
        data = JSONField()

    ContactInfo.objects.create(data={
        'name': 'John',
        'cities': ['London', 'Cambridge'],
        'pets': {'dogs': ['Rufus', 'Meg']},
    })
    ContactInfo.objects.filter(
        data__name='John',
        data__pets__has_key='dogs',
        data__cities__contains='London',
    ).delete()

Features
========

Most features of the JSONField model and form fields from Django 3.1 are
supported.

* MariaDB, MySQL, Oracle, PostgreSQL, and SQLite support.
* JSONField lookups and transforms support.
* Custom encoder and decoder support.

Due to limited access to Django's APIs, some features are not supported.

* Introspection is not supported.
* On MariaDB and Oracle, ``Cast``\ing to JSONField must be done using the
  included ``JSONCast`` class.

This package is fully compatible with the JSONField from Django 3.1. That
means you just need to change your imports and edit your migrations when you
finally upgrade to Django 3.1. If you leave them as they are, this package
will use the built-in JSONField and system warnings will be raised.

Requirements
============

This package supports and is tested against the latest patch versions of:

* **Python:** 3.5 (Django 2.2 only), 3.6, 3.7, 3.8, 3.9
* **Django:** 2.2, 3.0, 3.1
* **MariaDB:** 10.2, 10.3, 10.4, 10.5
* **MySQL:** 5.7, 8.0
* **Oracle:** 12.2+ (only tested against 12.2.0.1 SE)
* **PostgreSQL:** 9.5, 10, 11, 12
* **SQLite:** 3.9.0+ with the `JSON1`_ extension

All database backends are tested with the latest versions of their drivers.
SQLite is also tested on GitHub Actions' latest macOS and Windows virtual
environments.

.. _JSON1: https://docs.djangoproject.com/en/3.1/ref/databases/#sqlite-json1

Installation
============

1. Use **pip** or your preferred dependency management tool to install the package.

   .. code-block:: shell

       $ pip install django-jsonfield-backport

2. Add ``"django_jsonfield_backport"`` to ``INSTALLED_APPS`` in your settings.

   .. code-block:: python

       INSTALLED_APPS = [
           ...
           "django_jsonfield_backport",
       ]

Usage
=====

To use the model and form fields, import ``JSONField`` from
``django_jsonfield_backport.models`` and ``django_jsonfield_backport.forms``,
respectively.

Model field example:

.. code-block:: python

    from django.db import models
    from django_jsonfield_backport.models import JSONField

    class ContactInfo(models.Model):
        data = JSONField()

Form field example:

.. code-block:: python

    from django import forms
    from django_jsonfield_backport.forms import JSONField

    class ContactForm(forms.Form):
        data = JSONField()

``JSONCast``, ``KeyTransform``, and ``KeyTextTransform`` classes are also
available from ``django_jsonfield_backport.models``.

Documentation
=============

Since this package is a backport, the official Django 3.1 docs for
|models.JSONField|_ and |forms.JSONField|_ are mostly compatible with this
package.

.. |models.JSONField| replace:: ``models.JSONField``
.. |forms.JSONField| replace:: ``forms.JSONField``

.. _models.JSONField: https://docs.djangoproject.com/en/3.1/ref/models/fields/#django.db.models.JSONField
.. _forms.JSONField: https://docs.djangoproject.com/en/3.1/ref/forms/fields/#django.forms.JSONField

Rationale
=========

As of the creation of this package, JSONField implementations exist in multiple
packages on PyPI:

* `Django <https://github.com/django/django>`_:
  Before Django 3.1, PostgreSQL-only JSONField exists in the ``contrib.postgres``
  module.

* `jsonfield <https://github.com/rpkilby/jsonfield>`_:
  1.1k stars, cross-DB support with no extended querying capabilities.

* `django-annoying <https://github.com/skorokithakis/django-annoying#jsonfield>`_:
  787 stars, has a ``TextField``-based JSONField with no extended querying
  capabilities.

* `Django-MySQL <https://github.com/adamchainz/django-mysql>`_:
  364 stars, has a MariaDB/MySQL-only JSONField with extended querying
  capabilities (not entirely the same as in ``contrib.postgres``).

* `django-jsonfallback <https://github.com/raphaelm/django-jsonfallback>`_:
  26 stars, uses JSONField from ``contrib.postgres`` and Django-MySQL before
  falling back to ``TextField``\-based JSONField.

* `django-json-field <https://github.com/derek-schaefer/django-json-field>`_:
  116 stars, ``TextField``-based JSONField with custom encoder and decoder
  support with no extended querying capabilities (unmaintained).

* `django-jsonfield <https://github.com/adamchainz/django-jsonfield>`_:
  21 stars, cross-DB support with no extended querying capabilities.

* `django-jsonfield-compat <https://github.com/kbussell/django-jsonfield-compat>`_:
  8 stars, compatibility layer for ``contrib.postgres`` JSONField and
  django-jsonfield.

* `oracle-json-field <https://github.com/Exscientia/oracle-json-field>`_:
  2 stars, Oracle-only JSONField with extended querying capabilities
  (not entirely the same as in ``contrib.postgres``).

Along with other unmaintained packages such as `dj-jsonfield`_,
`vlk-django-jsonfield`_, `linaro-django-jsonfield`_, `jsonfield2`_,
`django-jsonfield2`_, `django-softmachine`_, `django-simple-jsonfield`_,
`easy_jsonfield`_, and `django-jsonbfield`_.

.. _dj-jsonfield: https://github.com/ratson/dj-jsonfield
.. _vlk-django-jsonfield: https://github.com/vialink/vlk-django-jsonfield
.. _linaro-django-jsonfield: https://pypi.org/project/linaro-django-jsonfield
.. _jsonfield2: https://github.com/rpkilby/jsonfield2
.. _django-jsonfield2: https://github.com/DarioGT/django-jsonfield2
.. _django-softmachine: https://github.com/certae/django-softmachine
.. _django-simple-jsonfield: https://github.com/devkral/django-simple-jsonfield
.. _easy_jsonfield: https://github.com/claydodo/easy_jsonfield
.. _django-jsonbfield: https://pypi.org/project/django-jsonbfield

Why create another one?
-----------------------

Up until the new JSONField in Django 3.1, there had been no implementation of
JSONField that supports all the database backends supported by Django with more
or less **the same functionalities** as the ``contrib.postgres`` JSONField
provides.

`Django's release process`_ does not backport new features to previous feature
releases. However, the current LTS release is 2.2 which is still supported until
April 2022. The next LTS release is Django 3.2 in April 2021 that happens to be
the end of extended support for Django 3.1.

Some projects only use LTS releases of Django. There are also incompatibilities
between Django 3.0 and 3.1. Therefore, using Django 3.1 may not be an option for
some people at the moment.

Since JSONField seems to be in popular demand and that it works well as a
standalone package, I decided to create a backport.

Besides, I'm the `co-author of the new JSONField`_. ¯\\_(ツ)_/¯

.. _Django's release process: https://docs.djangoproject.com/en/dev/internals/release-process/#supported-versions
.. _co-author of the new JSONField: https://github.com/django/django/pull/12392

License
=======

This package is licensed under the `BSD 3-Clause License`_.

.. _BSD 3-Clause License: https://github.com/laymonage/django-jsonfield-backport/blob/master/LICENSE
