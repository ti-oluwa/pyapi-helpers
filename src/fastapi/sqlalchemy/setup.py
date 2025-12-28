import typing
from contextlib import asynccontextmanager, contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session, configure_mappers, DeclarativeMeta
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

from src.fastapi.config import settings

########
# SYNC #
########

sa_configs = settings.SQLALCHEMY
engine = create_engine(**sa_configs.engine["sync"])
SessionLocal = sessionmaker(bind=engine, class_=Session, **sa_configs.sessionmaker.sync)


@contextmanager
def get_session(session_type: typing.Optional[typing.Type[Session]] = None, **kwargs):
    """
    Returns a new DB session.

    :param session_type: Type of session to return
    :param kwargs: Additional keyword arguments to pass to the session on creation
    """
    session_type_ = session_type or SessionLocal
    with session_type_(**kwargs) as session:
        yield session


#########
# ASYNC #
#########

async_engine = create_async_engine(**sa_configs.engine["async"])
AsyncSessionLocal = sessionmaker(
    bind=async_engine,  # type: ignore[arg-type]
    class_=AsyncSession,
    **sa_configs.sessionmaker["async"],  # type: ignore
)


@asynccontextmanager
async def get_async_session(
    session_type: typing.Optional[typing.Type[AsyncSession]] = None, **kwargs
):
    """
    Returns a new async DB session.

    :param session_type: Type of session to return
    :param kwargs: Additional keyword arguments to pass to the session on creation
    """
    session_type_ = session_type or AsyncSessionLocal
    async with session_type_(**kwargs) as session:  # type: ignore
        yield session


def bind_db_to_model_base(db_engine, model_base: DeclarativeMeta) -> None:
    """
    Bind the database engine to the model base, creating all tables in the database.
    """
    model_base.metadata.create_all(bind=db_engine)
    # Ensures that mappings/relationships between
    # models are properly defined on setup
    configure_mappers()


__all__ = [
    "get_session",
    "engine",
    "SessionLocal",
    "get_async_session",
    "async_engine",
    "AsyncSessionLocal",
]
