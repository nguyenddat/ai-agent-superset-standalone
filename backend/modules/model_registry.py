from importlib import import_module

MODEL_PACKAGES = (
    "backend.modules.database_connection.models",
    "backend.modules.data_dictionary.models",
    "backend.modules.business_model.models",
    "backend.modules.data_lineage.models",
    "backend.modules.metric_management.models",
    "backend.modules.glossary_management.models",
    "backend.modules.expert_rule_management.models",
    "backend.modules.own_knowledge.models",
    "backend.modules.text2sql.models",
    "backend.modules.conversation.models",
)


def register_all_models() -> None:
    for package in MODEL_PACKAGES:
        import_module(package)
