"""Alembic migration environment for the application metadata database."""

from alembic import context
from sqlalchemy import create_engine, pool

from backend.common.base_model import Base
from backend.core.setting import Config
from backend.modules.business_model import models as business_model_models  # noqa: F401 - register models with Base
from backend.modules.data_lineage import models as data_lineage_models  # noqa: F401 - register models with Base
from backend.modules.metric_management import models as metric_management_models  # noqa: F401 - register models with Base
from backend.modules.glossary_management import models as glossary_management_models  # noqa: F401
from backend.modules.expert_rule_management import models as expert_rule_management_models  # noqa: F401
from backend.modules.data_dictionary import models as data_dictionary_models  # noqa: F401 - register models with Base
from backend.modules.database_connection import models  # noqa: F401 - register models with Base

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
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(database_url(), poolclass=pool.NullPool)
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
