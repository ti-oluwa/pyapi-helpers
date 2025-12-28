import enum


class ExtendedEnum(enum.Enum):
    """Extended Enum class to add some useful methods to the Enum class."""

    @classmethod
    def list(cls):
        return list(map(lambda c: c.value, cls))

    @classmethod
    def get(cls, value):
        return cls(value)

    @classmethod
    def get_name(cls, value):
        return cls.get(value).name

    @classmethod
    def get_value(cls, name):
        return cls[name].value

    @classmethod
    def get_name_from_value(cls, value):
        return cls.get(value).name
