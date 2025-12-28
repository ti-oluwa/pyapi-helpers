from src.dependencies import deps_required, depends_on


deps_required(
    {
        "click": "click",
    }
)

import typing
import click  # type: ignore[import]


def make_commands_registry(
    name: str,
    description: typing.Optional[str] = None,
    **kwargs,
) -> click.Group:
    """
    Uses `click` to create a command registry/group.

    A command registry is a group of commands that can be executed via CLI.
    Basically, it's a `click.Group` object.

    :param name: name of the command group
    :param description: description of the command registry/group
    :param kwargs: additional arguments to pass to `click.group`
    """

    def registry():
        """
        Group of application commands accessible via CLI
        """
        pass

    if description:
        registry.__doc__ = description
        kwargs.setdefault("help", description)

    kwargs.setdefault("invoke_without_command", True)
    cls = kwargs.pop("cls", click.Group)
    return click.group(name, cls=cls, **kwargs)(registry)


management = make_commands_registry("manage", "Application management commands")
"""
Default management commands registry for the FastAPI application.

Register commands using the `register` decorator or using `management.command`.

Create a new command registry using `make_commands_registry` function if
the default commands registered are not needed/suitable for your use case.

Example:
```python
import click

from src.fastapi.commands import main, register

myapp_commands = make_commands_registry("myapp_commands", "My application commands")
# Create a registrar for the new command registry
register = myapp_commands.command

@register("do_something")
@click.option("--option", help="Some option")
def do_something(option: str):
    \"\"\"Do something with the provided option.\"\"\"
    pass
    
# In main.py

if __name__ == "__main__":
    myapp_commands() # This will run the command group/registry
```
"""

register = management.command
"""
Register a command with the default management command registry.

Example:
```python
import click
from src.fastapi.commands import register


@register("do_something")
@click.option("--option", help="Some option")
def do_something(option: str):
    \"\"\"Do something with the provided option.\"\"\"
    pass
```
"""

LOG_LEVELS = {
    "debug",
    "info",
    "warning",
    "error",
    "critical",
}


@register("startserver", help="Start the FastAPI application server using uvicorn")
@click.argument(
    "app",
    default="main:app",
    required=False,
    metavar="APP",
    envvar="FASTAPI_APP_MODULE",
)
@click.option("--host", "-h", default="127.0.0.1", help="Bind socket to this host.")
@click.option("--port", "-p", default=8000, help="Bind socket to this port.")
@click.option("--workers", "-w", default=1, help="Number of worker processes.")
@click.option(
    "--reload/--no-reload",
    default=None,
    help="Enable/disable automatic reloading.",
    is_flag=True,
)
@click.option(
    "--log-level",
    default="info",
    type=click.Choice(LOG_LEVELS),
    help="Log level [debug, info, warning, error, critical]",
)
@click.option("--ssl-keyfile", help="SSL key file", type=click.Path(exists=True))
@click.option(
    "--ssl-certfile", help="SSL certificate file", type=click.Path(exists=True)
)
@click.pass_context
@depends_on({"uvicorn": "uvicorn"})
def startserver(
    ctx: typing.Optional[click.Context],
    app: str,
    host: str,
    port: int,
    workers: int,
    reload: bool,
    log_level: str,
    ssl_keyfile: typing.Optional[str],
    ssl_certfile: typing.Optional[str],
):
    """
    Start the FastAPI application server using uvicorn.

    The APP argument should be in format "module:app_var", e.g. "main:app"

    Examples:\n
        manage.py startserver\n
        manage.py startserver custom_app:app\n
        manage.py startserver --host 0.0.0.0 --port 80\n
        manage.py startserver --workers 4 --reload\n
        manage.py startserver --log-level debug\n
        manage.py startserver --ssl-keyfile ./key.pem --ssl-certfile ./cert.pem
    """
    import uvicorn  # type: ignore[import]

    config = {
        "app": app,
        "host": host,
        "port": port,
        "workers": workers,
        "log_level": log_level,
        **({"reload": reload} if reload is not None else {}),
        **({"ssl_keyfile": ssl_keyfile} if ssl_keyfile else {}),
        **({"ssl_certfile": ssl_certfile} if ssl_certfile else {}),
    }

    if ctx and ctx.obj:
        # Get any additional options passed via command line
        config.update(
            {k.replace("-", "_"): v for k, v in ctx.obj.items() if v is not None}
        )

    try:
        uvicorn.run(**config)
    except Exception as exc:
        click.echo(
            click.style(f"Error starting server: {str(exc)}", fg="red"),
            err=True,
        )
        raise click.Abort() from exc


__all__ = ["management", "register", "startserver"]
