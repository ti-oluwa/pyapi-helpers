import typing
import click
import sqlalchemy as sa
from sqlalchemy.orm import Session
import fastapi.exceptions

from src.fastapi.commands import register
from .users import get_user_model
from src.fastapi.sqlalchemy.models import Model
from src.fastapi.sqlalchemy.setup import get_session


def validate_value(value: str, validators: typing.List[typing.Callable]) -> str:
    """Validate a value against provided validators."""
    try:
        for validator in validators:
            validator(value)
        return value
    except ValueError as exc:
        raise click.BadParameter(str(exc))
    except fastapi.exceptions.ValidationException as exc:
        raise click.BadParameter("\n".join(exc.errors()))


def is_unique(
    session: Session, model: typing.Type[Model], field_name: str, value: str
) -> bool:
    """Check if the field value is unique."""
    result = session.execute(
        sa.select(sa.func.count()).where(getattr(model, field_name) == value)
    )
    return not result.scalar()


def is_unique_field(field_name: str, model: typing.Type[Model]) -> bool:
    """Check if the field is unique."""
    column = model.__table__.columns[field_name]  # type: ignore
    return getattr(column, "unique", False)


@register("create_admin_user")
@click.option(
    "--username",
    "-u",
    prompt="Username",
    help="Admin username",
    required=True,
    type=str,
)
def create_admin_user(username: str):
    """Create an admin instance of `settings.AUTH_USER_MODEL`."""
    user_model = get_user_model()
    with get_session() as session:
        if not is_unique(
            session,
            model=user_model,
            field_name=user_model.USERNAME_FIELD,
            value=username,
        ):
            raise click.BadParameter(
                click.style(f"Username '{username}' already exists", fg="yellow")
            )

        user_data = {
            user_model.USERNAME_FIELD: username,
            "is_active": True,
            "is_staff": True,
            "is_admin": True,
        }

        for field, validators in user_model._get_required_fields().items():
            if field not in user_data:
                check_unique = is_unique_field(field, user_model)
                while True:
                    try:
                        value = click.prompt(field)
                        validate_value(value, validators)
                        if check_unique:
                            if not is_unique(session, user_model, field, value):
                                click.echo(
                                    click.style(
                                        f"{field} '{value}' already exists", fg="yellow"
                                    ),
                                    err=True,
                                )
                                continue
                        user_data[field] = value
                        break
                    except click.BadParameter as exc:
                        click.echo(
                            click.style(f"Invalid {field}: {str(exc)}", fg="red"),
                            err=True,
                        )

        while True:
            password = click.prompt(
                "Password", hide_input=True, confirmation_prompt=True
            )
            user = user_model(**user_data)
            try:
                user.set_password(password)
                break
            except ValueError as exc:
                click.echo(click.style(f"Password is invalid: {str(exc)}", fg="yellow"))
            except fastapi.exceptions.ValidationException as exc:
                click.echo(
                    click.style("\n".join(exc.errors()), fg="yellow"),
                    err=True,
                )

        session.add(user)
        session.commit()
        click.echo(
            click.style(
                f"Admin user '{user.get_username()}' created successfully.",
                bold=True,
                fg="green",
            )
        )


__all__ = ["create_admin_user"]
