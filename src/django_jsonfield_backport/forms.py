"""
Form field classes.
"""
import json
import warnings

import django
from django.core.exceptions import ValidationError
from django.forms import CharField, Textarea
from django.utils.translation import gettext_lazy as _

__all__ = ("JSONField",)


class InvalidJSONInput(str):
    pass


class JSONString(str):
    pass


if django.VERSION >= (3, 1):
    from django.forms import JSONField as BuiltinJSONField

    class JSONField(BuiltinJSONField):
        def __init__(self, *args, **kwargs):
            warnings.warn(
                "You are using Django 3.1 or newer, which already has a built-in JSONField. "
                "Use django.forms.JSONField instead.",
                ImportWarning,
                stacklevel=2,
            )
            super().__init__(*args, **kwargs)


else:

    class JSONField(CharField):
        default_error_messages = {
            "invalid": _("Enter a valid JSON."),
        }
        widget = Textarea

        def __init__(self, encoder=None, decoder=None, **kwargs):
            self.encoder = encoder
            self.decoder = decoder
            super().__init__(**kwargs)

        def to_python(self, value):
            if self.disabled:
                return value
            if value in self.empty_values:
                return None
            elif isinstance(value, (list, dict, int, float, JSONString)):
                return value
            try:
                converted = json.loads(value, cls=self.decoder)
            except json.JSONDecodeError:
                raise ValidationError(
                    self.error_messages["invalid"], code="invalid", params={"value": value}
                )
            if isinstance(converted, str):
                return JSONString(converted)
            else:
                return converted

        def bound_data(self, data, initial):
            if self.disabled:
                return initial
            try:
                return json.loads(data, cls=self.decoder)
            except json.JSONDecodeError:
                return InvalidJSONInput(data)

        def prepare_value(self, value):
            if isinstance(value, InvalidJSONInput):
                return value
            return json.dumps(value, cls=self.encoder)

        def has_changed(self, initial, data):
            if super().has_changed(initial, data):
                return True
            # For purposes of seeing whether something has changed, True isn't the
            # same as 1 and the order of keys doesn't matter.
            return json.dumps(initial, sort_keys=True, cls=self.encoder) != json.dumps(
                self.to_python(data), sort_keys=True, cls=self.encoder
            )
