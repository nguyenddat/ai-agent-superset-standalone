import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from langchain_core.language_models import BaseChatModel
from openai import OpenAIError
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

from backend.agent_package.prompts.prompt_text2sql_agent import text2sql_agent_prompt
from backend.agent_package.tool_agent import (
    ToolAgentResume,
    ToolCallback,
    ToolError,
    ToolStartCallback,
    run_tool_agent,
)
from backend.core.setting import config

from ..repositories.source_query_repository import QueryRows, run_read_only, source_url
from ..schemas import (
    AgentStepOut,
    FieldOut,
    PreprocessedQuestionOut,
    PreprocessOut,
    QuestionAnswerOut,
    QuestionKnowledgeOut,
)
from ..utils.exceptions import Text2SqlAgentUnavailable
from .agent_catalog import AgentCatalog, load_catalog
from .agent_tools import QueryCache, Text2SqlToolkit
from .answer_stream import DeltaBuffer
from .chat_events import (
    TOOL_STARTED,
    Emit,
    lookup_event,
    step_event,
    tool_started_event,
)
from .chat_graph import PendingQuestion
from .display_format import (
    date_ranges,
    dates_context,
    llm_fields,
    llm_rows,
    today_label,
)
from .pii_masker import PiiMasker

logger = logging.getLogger("text2sql.agent")

TOPIC_FIELDS = ("tables", "columns", "glossary", "expert_rules", "own_knowledge")
EMPTY_ANSWER = "Chưa trả lời được câu hỏi này."
SUBJECT_LENGTH = 80
SUBJECT_KEYS = {
    "get_metric": "metric", "query_metric": "metric", "get_table": "table", "get_expert_rule": "rule",
    "get_column_values": "column",
}

SourceRunner = Callable[[URL, str, int, int], QueryRows]


__all__ = [
    "AgentRun",
    "Text2SqlAgentService",
    "date_ranges",
    "prior_context",
    "replied_steps",
    "tool_reporter",
    "tool_starter",
    "tool_subject",
]


def knowledge_context(knowledge: QuestionKnowledgeOut) -> dict[str, Any]:
    return {
        "metrics": [
            {"id": str(item.metric_id), "name": item.name, "label": item.label, "description": item.description}
            for item in knowledge.metrics
        ],
        **{
            field: [{"name": hit.display_name, "text": hit.text} for hit in getattr(knowledge, field)]
            for field in TOPIC_FIELDS
        },
    }


def prior_context(answer: QuestionAnswerOut, max_rows: int, today: date | None = None) -> dict[str, Any]:
    data = next((step for step in reversed(answer.steps) if step.error is None and step.sql), None)
    payload = None
    if data is not None:
        rows = data.rows[:max_rows]
        payload = {"columns": data.columns, "rows": rows}
        if data.fields and today is not None:
            fields = [FieldOut.model_validate(item) if isinstance(item, dict) else item for item in data.fields]
            payload = {"fields": llm_fields(fields), "columns": data.columns, "rows": llm_rows(rows, fields, today)}
    return {"position": answer.position, "question": answer.question, "answer": answer.answer, "data": payload}


def replied_steps(pending: PendingQuestion | None, reply: str | None) -> list[AgentStepOut]:
    if pending is None:
        return []
    steps = list(pending.steps)
    for index in range(len(steps) - 1, -1, -1):
        if steps[index].tool == "ask_user":
            steps[index] = steps[index].model_copy(update={"notes": [f"Người dùng trả lời: {reply}"]})
            break
    return steps


def tool_reporter(position: int, toolkit: Text2SqlToolkit, emit: Emit) -> ToolCallback:
    seen = len(toolkit.steps)

    def report(tool: str, arguments: dict[str, Any], output: Any) -> None:
        nonlocal seen
        recorded = toolkit.steps[seen:]
        seen = len(toolkit.steps)
        if not recorded:
            emit("tool", lookup_event(position, tool, arguments, output))
        for step in recorded:
            emit("tool", step_event(position, step))

    return report


def _raw_subject(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text[:SUBJECT_LENGTH] or None


def _catalog_subject(catalog: AgentCatalog, tool: str, arguments: dict[str, Any]) -> str | None:
    if tool in ("get_metric", "query_metric"):
        metric = catalog.metric(str(arguments.get("metric", "")))
        return metric.label or metric.name
    if tool == "get_table":
        table = catalog.table(str(arguments.get("table", "")))
        return table.label or table.qualified_name
    if tool == "get_expert_rule":
        return catalog.rule(str(arguments.get("rule", ""))).name
    column = catalog.table(str(arguments.get("table", ""))).column(str(arguments.get("column", "")))
    return column.label or column.name


def tool_subject(catalog: AgentCatalog, tool: str, arguments: dict[str, Any]) -> str | None:
    if tool == "run_sql":
        return _raw_subject(arguments.get("purpose"))
    if tool not in SUBJECT_KEYS:
        return None
    try:
        return _catalog_subject(catalog, tool, arguments)
    except ToolError:
        return _raw_subject(arguments.get(SUBJECT_KEYS[tool]))


def tool_starter(position: int, catalog: AgentCatalog, emit: Emit) -> ToolStartCallback:
    def start(tool: str, arguments: dict[str, Any]) -> None:
        emit(TOOL_STARTED, tool_started_event(position, tool, tool_subject(catalog, tool, arguments)))

    return start


@dataclass
class AgentRun:
    catalog: AgentCatalog
    cache: QueryCache
    today: date
    model: BaseChatModel | None = None
    # Dùng chung cho mọi câu của lượt để một giá trị luôn có cùng nhãn thay thế.
    masker: PiiMasker = field(default_factory=PiiMasker)

    def answer(
        self, preprocess: PreprocessOut, item: PreprocessedQuestionOut, prior: Sequence[QuestionAnswerOut],
        pending: PendingQuestion | None = None, reply: str | None = None, emit: Emit | None = None,
    ) -> QuestionAnswerOut | PendingQuestion:
        max_rows = config.text2sql_agent_max_rows_to_llm
        toolkit = Text2SqlToolkit(
            self.catalog, self.cache, max_rows, replied_steps(pending, reply), position=item.position,
            today=self.today, question_type=item.question_type, masker=self.masker,
        )
        context = {
            "today": today_label(self.today),
            "dates": dates_context(self.today),
            "question": item.question, "question_type": item.question_type,
            "business_concepts": item.business_concepts,
            "knowledge": knowledge_context(item.knowledge),
            "prior_results": [prior_context(answer, max_rows, self.today) for answer in prior],
        }
        streams = {}
        if emit is not None:
            final = not preprocess.is_split and len(preprocess.questions) == 1
            streams = {
                "on_tool": tool_reporter(item.position, toolkit, emit),
                "on_text": DeltaBuffer(emit, item.position, final).text_stream(),
                "on_tool_start": tool_starter(item.position, self.catalog, emit),
            }
        try:
            result = run_tool_agent(
                text2sql_agent_prompt, context, toolkit.tools(), config.text2sql_agent_max_steps, self.model,
                resume=ToolAgentResume(pending.pause, reply) if pending is not None else None, **streams,
            )
        except OpenAIError as error:
            logger.warning("Agent lỗi ở câu %s: %s", item.position, type(error).__name__)
            raise Text2SqlAgentUnavailable() from error
        if result.pause is not None:
            payload = result.pause.payload
            return PendingQuestion(
                position=item.position, question=payload["question"], options=list(payload.get("options") or []),
                pause=result.pause, steps=[*toolkit.steps, AgentStepOut(tool="ask_user", arguments=payload)],
            )
        return QuestionAnswerOut(
            position=item.position, question=item.question, answer=result.answer or EMPTY_ANSWER,
            exhausted=result.exhausted, steps=toolkit.steps,
        )


class Text2SqlAgentService:
    def __init__(
        self, session: Session, model: BaseChatModel | None = None, runner: SourceRunner = run_read_only,
    ) -> None:
        self.session = session
        self.model = model
        self.runner = runner

    def start(self, connection_id: UUID) -> AgentRun:
        url = source_url(self.session, connection_id)
        timeout = config.text2sql_query_timeout_seconds
        cache = QueryCache(
            runner=lambda sql, max_rows: self.runner(url, sql, max_rows, timeout),
            max_rows=config.text2sql_query_max_rows,
        )
        today = datetime.now(ZoneInfo(config.text2sql_timezone)).date()
        return AgentRun(load_catalog(self.session, connection_id), cache, today, self.model)
