from rest_framework import serializers


class SplitCharField(serializers.ListField):
    def __init__(self, *args, delimiter, **kwargs):
        self.delimiter = delimiter
        self.child = serializers.CharField()
        super().__init__(*args, **kwargs)

    def to_internal_value(self, data):
        return self.delimiter.join(data)

    def to_representation(self, value):
        return value.split(self.delimiter)
