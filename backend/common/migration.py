from .base_model import TECHNICAL_SCHEMA


def include_name(name: str | None, type_: str, parent_names: dict[str, str | None]) -> bool:
    if type_ == "schema":
        return name in (None, TECHNICAL_SCHEMA)
    return True


def alembic_options() -> dict[str, object]:
    return {"include_schemas": True, "include_name": include_name}
