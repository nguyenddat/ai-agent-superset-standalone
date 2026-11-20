import argparse
import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

from local_env import add_local_arguments, host_mapper, override_app_db


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Chạy backend từ máy host cho bộ đánh giá text2sql.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18100)
    parser.add_argument("--trace-file", default="", help="Ghi message của từng lượt agent ra file JSONL")
    add_local_arguments(parser)
    return parser.parse_args()


def message_trace(messages: list[Any]) -> list[dict[str, Any]]:
    trace = []
    for message in messages[2:]:
        kind = type(message).__name__
        if kind == "AIMessage":
            usage = getattr(message, "usage_metadata", None) or {}
            trace.append({
                "kind": "ai", "text": message.text[:500],
                "tool_calls": [{"name": call["name"], "args": call["args"]} for call in message.tool_calls],
                "tokens": {key: usage.get(key) for key in ("input_tokens", "output_tokens")},
            })
        elif kind == "ToolMessage":
            trace.append({"kind": "tool", "name": message.name, "status": message.status,
                          "content": str(message.content)[:400]})
        else:
            trace.append({"kind": kind, "text": str(message.content)[:300]})
    return trace


def install_probes(remap: Any, trace_file: str) -> None:
    from backend.modules.text2sql.services import text2sql_agent_service as agent_module

    original_url = agent_module.source_url
    agent_module.source_url = lambda session, connection_id: remap(original_url(session, connection_id))
    if not trace_file:
        return
    path = Path(trace_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = threading.Lock()
    original_agent = agent_module.run_tool_agent

    def traced_run_tool_agent(system_prompt: str, context: dict[str, Any], *args: Any, **kwargs: Any) -> Any:
        started = time.perf_counter()
        result = original_agent(system_prompt, context, *args, **kwargs)
        record = {
            "question": context.get("question"), "seconds": round(time.perf_counter() - started, 2),
            "resumed": kwargs.get("resume") is not None, "exhausted": result.exhausted,
            "paused": result.pause is not None, "messages": message_trace(result.messages),
        }
        with lock, path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        return result

    agent_module.run_tool_agent = traced_run_tool_agent


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    override_app_db(args.app_db)
    install_probes(host_mapper(args.source_host_map), args.trace_file)

    import uvicorn

    from backend.main import app

    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
