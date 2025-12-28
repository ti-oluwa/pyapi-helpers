import typing
from django.contrib.auth.models import AbstractBaseUser


class UserNotFoundInContext(Exception):
    pass


def get_user_from_context(
    context: typing.Optional[typing.Dict[str, typing.Any]],,
    *,
    user_key: str = "user",
    raise_notfound: bool = False,
) -> typing.Optional[AbstractBaseUser]:
    user: typing.Optional[AbstractBaseUser] = context.get(user_key, None)
    if not isinstance(user, AbstractBaseUser): 
        try:
            user = context["request"].user
        except KeyError:
            user = None
    
    if not isinstance(user, AbstractBaseUser) and raise_notfound:
        raise UserNotFoundInContext
    return user
