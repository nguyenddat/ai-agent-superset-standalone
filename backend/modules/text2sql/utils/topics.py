TABLE = "table"
COLUMN = "column"
METRIC = "metric"
GLOSSARY = "glossary"
EXPERT_RULE = "expert_rule"
OWN_KNOWLEDGE = "own_knowledge"

TOPICS: tuple[str, ...] = (TABLE, COLUMN, METRIC, GLOSSARY, EXPERT_RULE, OWN_KNOWLEDGE)

DEFAULT_INTERVAL_SECONDS: dict[str, int] = {
    TABLE: 900,
    COLUMN: 900,
    METRIC: 300,
    GLOSSARY: 300,
    EXPERT_RULE: 300,
    OWN_KNOWLEDGE: 120,
}


def validate_topics(topics: list[str] | None) -> tuple[str, ...]:
    if topics is None:
        return TOPICS
    unknown = sorted(set(topics) - set(TOPICS))
    if unknown:
        raise ValueError(f"Topic không hợp lệ: {', '.join(unknown)}.")
    return tuple(topic for topic in TOPICS if topic in set(topics))
