from django.db import models


class PostgreSQLArrayAppend(models.Func):
    """
    Custom function to append an element to a PostgreSQL array.

    This function wraps the PostgreSQL `array_append` function to add an element to an array field.

    Example:
        ```python
        from django.db.models import F, Value
        from .models import MyModel

        # Append a new element 'new_value' to the array field 'tags'
        MyModel.objects.update(
            tags=PostgreSQLArrayAppend(F('tags'), Value('new_value'))
        )
        ```

    :param expressions: Two expressions are required.
                        The first is the array field, and the second is the element to append.
    :param extras: Extra options that can be passed to `models.Func` constructor.
    """

    function = "array_append"
    template = "%(function)s(%(expressions)s)"

    def __init__(self, *expressions, **extras):
        if len(expressions) != 2:
            raise ValueError(
                "Two expressions are required: an array field and an element to append."
            )
        super().__init__(*expressions, **extras)


class PostgreSQLArrayRemove(models.Func):
    """
    Custom function to remove an element from a PostgreSQL array.

    This function wraps the PostgreSQL `array_remove` function to remove an element from an array field.

    Example:
        ```python
        from django.db.models import F, Value
        from .models import MyModel

        # Remove the element 'old_value' from the array field 'tags'
        MyModel.objects.update(
            tags=PostgreSQLArrayRemove(F('tags'), Value('old_value'))
        )
        ```

    :param expressions: Two expressions are required.
                        The first is the array field, and the second is the element to remove.
    :param extras: Extra options that can be passed to `models.Func` constructor.
    """

    function = "array_remove"
    template = "%(function)s(%(expressions)s)"

    def __init__(self, *expressions, **extras):
        if len(expressions) != 2:
            raise ValueError(
                "Two expressions are required: an array field and an element to remove."
            )
        super().__init__(*expressions, **extras)


class PostgreSQLArrayAny(models.Func):
    """
    Custom function to check if any element in a PostgreSQL array satisfies a condition.

    This function wraps the PostgreSQL `ANY` function, which checks if any element in an array meets a condition.

    Example:
        ```python
        from django.db.models import Q, F
        from .models import MyModel

        # Check if any value in the array field 'tags' contains the substring 'value'
        MyModel.objects.filter(
            PostgreSQLArrayAny(Value('value'), F('tags'))
        )
        ```

    :param expressions: Two expressions are required.
                        The first is the condition, and the second is the array field to check.
    :param extras: Extra options that can be passed to `models.Func` constructor.
    """

    function = "ANY"
    template = "%(function)s(%(expressions)s)"

    def __init__(self, *expressions, **extras):
        if len(expressions) != 2:
            raise ValueError(
                "Two expressions are required: a condition and an array field."
            )
        super().__init__(*expressions, **extras)


class PostgreSQLArrayAll(models.Func):
    """
    Custom function to check if all elements in a PostgreSQL array satisfy a condition.

    This function wraps the PostgreSQL `ALL` function, which checks if all elements in an array meet a condition.

    Example:
        ```python
        from django.db.models import Q, F
        from .models import MyModel

        # Check if all values in the array field 'tags' contain the substring 'value'
        MyModel.objects.filter(
            PostgreSQLArrayAll(Q(field__icontains='value'), F('tags'))
        )
        ```

    :param expressions: Two expressions are required.
                        The first is the condition, and the second is the array field to check.
    :param extras: Extra options that can be passed to `models.Func` constructor.
    """

    function = "ALL"
    template = "%(function)s(%(expressions)s)"

    def __init__(self, *expressions, **extras):
        if len(expressions) != 2:
            raise ValueError(
                "Two expressions are required: a condition and an array field."
            )
        super().__init__(*expressions, **extras)


class PostgreSQLArrayOverlap(models.Func):
    """
    Custom function to check if two PostgreSQL arrays overlap (i.e., have common elements).

    This function wraps the PostgreSQL `&&` (overlap) operator.

    Example:
        ```python
        from django.db.models import F
        from .models import MyModel

        # Check if the array field 'tags1' overlaps with 'tags2'
        MyModel.objects.filter(
            PostgreSQLArrayOverlap(F('tags1'), F('tags2'))
        )
        ```

    :param expressions: Two expressions are required.
                        The two arrays to check for overlap.
    :param extras: Extra options that can be passed to `models.Func` constructor.
    """

    function = "&&"
    template = "%(expressions)s"

    def __init__(self, *expressions, **extras):
        if len(expressions) != 2:
            raise ValueError("Two array fields are required to check for overlap.")
        super().__init__(*expressions, **extras)


class PostgreSQLArrayContains(models.Func):
    """
    Custom function to check if a PostgreSQL array contains an element.

    This function wraps the PostgreSQL `@>` (contains) operator.

    Example:
        ```python
        from django.db.models import F, Value
        from .models import MyModel

        # Check if the array field 'tags' contains the element 'value'
        MyModel.objects.filter(
            PostgreSQLArrayContains(F('tags'), Value('value'))
        )
        ```

    :param expressions: Two expressions are required.
                        The first is the array field, and the second is the element to check.
    :param extras: Extra options that can be passed to `models.Func` constructor.
    """

    function = "@>"
    template = "%(expressions)s"

    def __init__(self, *expressions, **extras):
        if len(expressions) != 2:
            raise ValueError(
                "Two expressions are required: an array field and an element to check."
            )
        super().__init__(*expressions, **extras)


class PostgreSQLArrayLength(models.Func):
    """
    Custom function to get the length of a PostgreSQL array.

    Uses the PostgreSQL `array_length` function.

    Example:
        ```python
        from django.db.models import F
        from .models import MyModel

        # Get the length of the array field 'tags'
        MyModel.objects.annotate(
            array_length=PostgreSQLArrayLength(F('tags'))
        )
        ```

    :param expressions: The array field whose length is being measured.
    :param extras: Extra options that can be passed to `models.Func` constructor.
    """

    function = "array_length"
    template = (
        "%(function)s(%(expressions)s, 1)"  # 1 refers to the dimension of the array
    )

    def __init__(self, *expressions, **extras):
        if len(expressions) != 1:
            raise ValueError("One expression is required: the array field.")
        super().__init__(*expressions, **extras)


class PostgreSQLUnnest(models.Func):
    """
    Custom function to unnest (expand) a PostgreSQL array into a set of rows.

    This function wraps the PostgreSQL `unnest` function, which takes an array and returns each element in a separate row.

    Example:
        ```python
        from django.db.models import F
        from .models import MyModel

        # Unnest the array field 'tags' and annotate each row with an element from the array
        MyModel.objects.annotate(
            unnested_tag=PostgreSQLUnnest(F('tags'))
        )
        ```

    :param expressions: One expression is required: the array field to unnest.
    :param extras: Extra options that can be passed to `models.Func` constructor.
    """

    function = "unnest"
    template = "%(function)s(%(expressions)s)"

    def __init__(self, *expressions, **extras):
        if len(expressions) != 1:
            raise ValueError("One expression is required: the array field to unnest.")
        super().__init__(*expressions, **extras)


class PostgreSQLConcat(models.Func):
    """
    Custom function to concatenate values in PostgreSQL.

    This function wraps the PostgreSQL `concat` function, which concatenates multiple expressions into a single string.
    It works on any data types that can be implicitly cast to text, such as integers, strings, or dates.

    Example:
        ```python
        from django.db.models import F, Value
        from .models import MyModel

        # Concatenate first name and last name fields
        MyModel.objects.annotate(
            full_name=PostgreSQLConcat(
                F('first_name'), Value(' '), F('last_name')
            )
        )
        ```

    :param expressions: A variable number of expressions to concatenate.
    :param extras: Extra options to pass to `models.Func`.
    """

    function = "concat"
    template = "%(function)s(%(expressions)s)"

    def __init__(self, *expressions, **extras):
        if len(expressions) < 2:
            raise ValueError("At least two expressions are required for concatenation.")
        super().__init__(*expressions, **extras)


class PostgreSQLArrayConcat(models.Func):
    """
    Custom function to concatenate two arrays in PostgreSQL.

    This function wraps the PostgreSQL `array_cat` function, which concatenates two arrays into a single array.
    Both arrays must be of the same data type.

    Example:
        ```python
        from django.db.models import F, Value
        from .models import MyModel

        # Concatenate two array fields
        MyModel.objects.update(
            array_field=PostgreSQLArrayConcat(
                F('array_field_1'), F('array_field_2'), Value([1, 2, 3])
            )
        )
        ```

    :param expressions: Two expressions representing arrays to concatenate.
    :param extras: Extra options to pass to `models.Func`.
    """

    function = "array_cat"
    template = "%(function)s(%(expressions)s)"

    def __init__(self, *expressions, **extras):
        if len(expressions) != 2:
            raise ValueError("Two expressions are required for array concatenation.")
        super().__init__(*expressions, **extras)
