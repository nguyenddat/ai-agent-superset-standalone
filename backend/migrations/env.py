"""Alembic migration environment for the application metadata database."""

from alembic import context
from sqlalchemy import create_engine, pool

from backend.common.base_model import Base
from backend.common.migration import alembic_options
from backend.core.setting import Config
from backend.modules.model_registry import register_all_models

register_all_models()
target_metadata = Base.metadata


def database_url() -> str:
    return Config().require_database_url()


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        **alembic_options(),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(database_url(), poolclass=pool.NullPool)
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection, target_metadata=target_metadata, compare_type=True,
                **alembic_options(),
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
