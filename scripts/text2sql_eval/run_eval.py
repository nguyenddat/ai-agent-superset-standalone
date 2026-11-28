import argparse
import json
import re
import threading
import time
import unicodedata
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, nullcontext
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from statistics import median
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import httpx
from local_env import add_local_arguments, host_mapper, override_app_db

from backend.core.setting import config

HERE = Path(__file__).resolve().parent
NUMBER = re.compile(r"(?<![\w.,])(-?\d{1,3}(?:\.\d{3})+(?:,\d+)?|-?\d+(?:[.,]\d+)?)")
GROUPED = re.compile(r"-?\d{1,3}(?:\.\d{3})+(?:,\d+)?")
STYLE_CHECKS = {
    "underscore": lambda text, year: "_" in text,
    "backtick": lambda text, year: "`" in text,
    "same_year": lambda text, year: re.search(rf"\d{{1,2}}/\d{{1,2}}/{year}\b", text) is not None,
    "grouped_year": lambda text, year: f"{str(year)[0]}.{str(year)[1:]}" in text,
    "ban_ghi": lambda text, year: "bản ghi" in text.casefold(),
    "metric": lambda text, year: re.search(r"\bmetric\b", text.casefold()) is not None,
    "toi": lambda text, year: re.search(r"(?<!\w)tôi(?!\w)", text.casefold()) is not None,
}
BASELINE = HERE / "results" / "a2-final-x2.json"
ASSUMPTION_CUES = (
    "gia dinh", "hieu la", "mac dinh", "tam hieu", "tam lay", "chua ro", "khong noi ro", "chua noi ro", "chua neu",
    "khong neu", "so gop", "gop chung", "gop ca", "gop tat ca", "chung cho",
)
ALIASES = {"ho chi minh": ("tp.hcm", "tphcm", "tp hcm", "sai gon")}
CHAT_STREAM = "/api/v1/text2sql/chat/stream"
CHAT_JSON = "/api/v1/text2sql/chat"
CONVERSATIONS = "/api/v1/conversations"
PAUSED_URI = "postgresql+psycopg://eval@127.0.0.1:1/none"
TIMEOUT = httpx.Timeout(300.0, connect=10.0)


def normalized(value: str) -> str:
    folded = unicodedata.normalize("NFD", value.casefold().replace("đ", "d").replace("*", ""))
    return " ".join("".join(char for char in folded if unicodedata.category(char) != "Mn").split())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Chạy bộ câu hỏi text2sql qua HTTP trên database nguồn và LLM thật.")
    parser.add_argument("--connection-id", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:18100", help="Backend đang chạy (xem serve.py)")
    parser.add_argument("--endpoint", choices=("stream", "json"), default="stream")
    parser.add_argument("--questions", default=str(HERE / "questions.json"))
    parser.add_argument("--only", default="", help="Danh sách id hoặc loại, cách nhau bằng dấu phẩy")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--repeat", type=int, default=1, help="Chạy mỗi câu N lần để đo độ ổn định")
    parser.add_argument("--user-id", default="text2sql-eval", help="user_id gửi kèm; rỗng thì không ghi hội thoại")
    parser.add_argument("--keep-conversations", action="store_true", help="Không xóa hội thoại sau khi chấm")
    parser.add_argument("--trace-file", default="", help="File JSONL mà serve.py --trace-file đang ghi")
    parser.add_argument("--out", default="", help="File JSON kết quả; mặc định results/<thời điểm>.json")
    parser.add_argument("--baseline", default=str(BASELINE), help="File kết quả cũ để so độ trễ; rỗng thì bỏ qua")
    add_local_arguments(parser)
    return parser.parse_args()


def cell(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def local_today() -> date:
    return datetime.now(ZoneInfo(config.text2sql_timezone)).date()


def gold_rows(remap: Any, connection_id: UUID, sqls: list[str], today: date) -> list[dict[str, Any]]:
    from backend.core.database import get_session_factory
    from backend.modules.text2sql.repositories.source_query_repository import (
        run_read_only,
        source_url,
    )

    if not sqls:
        return []
    session = get_session_factory()()
    try:
        url = remap(source_url(session, connection_id))
    finally:
        session.close()
    results = []
    for sql in sqls:
        rendered = sql.replace("{today}", f"DATE '{today.isoformat()}'")
        rows = run_read_only(url, rendered, 500, 60)
        rendered_rows = [[cell(v) for v in row] for row in rows.rows]
        results.append({"sql": rendered, "columns": rows.columns, "rows": rendered_rows})
    return results


@contextmanager
def paused_connection() -> Any:
    from cryptography.fernet import Fernet

    from backend.core.database import get_session_factory
    from backend.modules.database_connection.models import DatabaseConnection

    key = config.require_connection_encryption_key()
    session = get_session_factory()()
    connection = DatabaseConnection(
        name=f"text2sql-eval paused {uuid4().hex[:8]}", dialect="postgresql", driver="psycopg",
        uri_ciphertext=Fernet(key.encode()).encrypt(PAUSED_URI.encode()).decode("ascii"), is_active=False,
    )
    session.add(connection)
    session.commit()
    try:
        yield connection.id
    finally:
        session.delete(connection)
        session.commit()
        session.close()


def answer_numbers(text: str) -> list[float]:
    values = []
    for match in NUMBER.findall(text):
        plain = match.replace(".", "") if GROUPED.fullmatch(match) else match
        try:
            values.append(float(plain.replace(",", ".")))
        except ValueError:
            continue
    return values


def has_number(numbers: list[float], wanted: float, tolerance: float | None) -> bool:
    limit = tolerance if tolerance is not None else max(0.051, abs(wanted) * 0.005)
    return any(abs(number - wanted) <= limit for number in numbers)


def check_gold(item: dict[str, Any], answer: str, gold: dict[str, Any]) -> list[str]:
    problems = []
    rows = gold["rows"]
    text = normalized(answer)
    numbers = answer_numbers(answer)
    kind = item["check"]
    if kind == "bool":
        expected = bool(rows and rows[0][0])
        first = normalized(re.split(r"[.!\n]", answer.strip(), maxsplit=1)[0])
        said = False if re.search(r"\bkhong\b", first) else True if re.search(r"\bco\b", first) else None
        if said is not expected:
            problems.append(f"có/không: mong đợi {expected}, câu đầu là '{first[:80]}'")
        return problems
    if kind in ("entities", "first_entity"):
        names = [str(row[0]) for row in rows if row and row[0] is not None]
        if kind == "first_entity":
            names = names[:1]
        if not names and not re.search(r"khong co|khong thanh pho nao|khong noi nao|khong ghi nhan", text):
            problems.append("gold rỗng nhưng câu trả lời không nói là không có")
        for name in names:
            key = normalized(name)
            if key not in text and not any(alias in text for alias in ALIASES.get(key, ())):
                problems.append(f"thiếu thực thể '{name}'")
        return problems
    for row in rows:
        for value in row:
            if isinstance(value, bool) or value is None:
                continue
            if isinstance(value, (int, float)):
                zero_in_words = value == 0 and re.search(r"\bkhong co\b|\bkhong\b.*\bnao\b", text)
                if not zero_in_words and not has_number(numbers, float(value), item.get("tolerance")):
                    problems.append(f"thiếu số {round(float(value), 3)}")
            elif (
                isinstance(value, str) and not re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", value)
                and normalized(value) not in text
            ):
                problems.append(f"thiếu '{value}'")
    if not rows:
        problems.append("gold không có dòng nào")
    return problems


def evaluate(item: dict[str, Any], output: dict[str, Any], golds: list[dict[str, Any]]) -> dict[str, Any]:
    answer = output.get("answer") or ""
    sql_steps = [step for answer_item in output.get("answers", []) for step in answer_item.get("steps", [])
                 if step.get("sql") and not step.get("error")]
    notes = []
    kind = item["check"]
    if kind == "keywords":
        text = normalized(answer)
        problems = [f"thiếu ý {group}" for group in item["keywords"] if not any(word in text for word in group)]
    elif kind in ("clarify", "clarify_or_assume"):
        text = normalized(answer)
        asked = output.get("status") == "needs_clarification" or "?" in answer
        assumed = any(cue in text for cue in ASSUMPTION_CUES) or any(
            explanation.get("kind") == "assumption"
            for answer_item in output.get("answers", []) for step in answer_item.get("steps", [])
            for explanation in step.get("explanations") or []
        )
        broken_down = bool(item.get("breakdown")) and len(answer_numbers(answer)) >= item["breakdown"]
        ok = asked or (kind == "clarify_or_assume" and (assumed or broken_down))
        problems = [] if ok else ["không hỏi lại và không nêu giả định"]
        notes.append(
            "hỏi lại (ask_user)" if output.get("status") == "needs_clarification"
            else "hỏi lại bằng văn bản" if asked else "nêu giả định" if assumed
            else "trả theo từng đối tượng" if broken_down else "trả lời thẳng"
        )
    else:
        attempts = [check_gold(item, answer, gold) for gold in golds]
        problems = min(attempts, key=len) if attempts else ["không có gold"]
    if item.get("no_query") and sql_steps:
        notes.append(f"thừa {len(sql_steps)} truy vấn")
    preprocess = output.get("preprocess") or {}
    if item.get("expect_split") and not preprocess.get("is_split"):
        notes.append("không tách câu")
    if item.get("expect_dependent") and not any(q.get("depends_on") for q in preprocess.get("questions", [])):
        notes.append("không có depends_on")
    return {"passed": not problems, "problems": problems, "notes": notes}


def sse_events(response: httpx.Response) -> Any:
    name, data = None, []
    for line in response.iter_lines():
        if not line:
            if name is not None:
                yield name, json.loads("\n".join(data)) if data else {}
            name, data = None, []
        elif line.startswith(":"):
            continue
        elif line.startswith("event:"):
            name = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].strip())


def stream_output(response: httpx.Response, started: float) -> dict[str, Any]:
    questions: dict[int, dict[str, Any]] = {}
    events: list[dict[str, Any]] = []
    output: dict[str, Any] = {"http_status": response.status_code}

    def question(position: int) -> dict[str, Any]:
        return questions.setdefault(position, {"position": position, "steps": []})

    deltas = 0
    for name, data in sse_events(response):
        offset = round(time.perf_counter() - started, 2)
        if name == "answer_delta":
            deltas += 1
            if data.get("final") and "first_delta_t" not in output:
                output["first_delta_t"] = offset
            continue
        events.append({"event": name, "t": offset, "position": data.get("position")})
        if name == "preprocess":
            output["preprocess"] = data
        elif name == "question_started":
            question(data["position"]).update(question=data["question"], started_t=offset, resumed=data["resumed"])
        elif name == "tool":
            question(data["position"])["steps"].append(data)
        elif name == "question_waiting":
            question(data["position"]).update(waiting=data, ended_t=offset)
        elif name == "question_answered":
            question(data["position"]).update(answer=data["answer"], exhausted=data["exhausted"], ended_t=offset)
        elif name in ("turn", "answer", "clarification", "done", "error"):
            output[name] = data
    done = output.get("done") or {}
    output.update(
        status=done.get("status"), answer=done.get("answer"), resume_id=done.get("resume_id"),
        conversation_id=done.get("conversation_id"), turn_id=done.get("turn_id"),
        answers=[questions[position] for position in sorted(questions)], events=events, delta_count=deltas,
    )
    return output


def json_output(response: httpx.Response) -> dict[str, Any]:
    body = response.json()
    if response.status_code != 200:
        return {"http_status": response.status_code, "detail": body.get("detail")}
    return {**body, "http_status": 200, "events": []}


class Client:
    def __init__(self, base_url: str, endpoint: str) -> None:
        key = config.text2sql_service_key
        headers = {"X-Service-Key": key.get_secret_value()} if key else {}  # unset: the API answers 503
        self.http = httpx.Client(base_url=base_url, timeout=TIMEOUT, headers=headers)
        self.endpoint = endpoint

    def chat(self, body: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        if self.endpoint == "json":
            output = json_output(self.http.post(CHAT_JSON, json=body))
        else:
            with self.http.stream("POST", CHAT_STREAM, json=body) as response:
                if response.status_code != 200:
                    response.read()
                    output = {"http_status": response.status_code, "detail": response.json().get("detail")}
                else:
                    output = stream_output(response, started)
        output["seconds"] = round(time.perf_counter() - started, 2)
        return output

    def turns(self, conversation_id: str, user_id: str) -> list[dict[str, Any]]:
        response = self.http.get(f"{CONVERSATIONS}/{conversation_id}/turns", params={"user_id": user_id})
        response.raise_for_status()
        return response.json()

    def delete_conversation(self, conversation_id: str, user_id: str) -> None:
        self.http.delete(f"{CONVERSATIONS}/{conversation_id}", params={"user_id": user_id})


def timings(output: dict[str, Any]) -> dict[str, Any]:
    events = output.get("events") or []
    first = {event["event"]: event["t"] for event in reversed(events)}
    return {
        "total": output.get("seconds"),
        "first_event": events[0]["t"] if events else None,
        "preprocess": first.get("preprocess"),
        "questions": [
            {"position": item["position"], "seconds": round(item["ended_t"] - item["started_t"], 2)}
            for item in output.get("answers", []) if "started_t" in item and "ended_t" in item
        ],
        "tool_steps": sum(len(item.get("steps", [])) for item in output.get("answers", [])),
        "make_chart": sum(
            1 for item in output.get("answers", []) for step in item.get("steps", [])
            if step.get("tool") == "make_chart"
        ),
        "first_text": output.get("first_delta_t", first.get("answer")),
        "answer_deltas": output.get("delta_count", 0),
    }


def style_flags(answer: str, today: date) -> list[str]:
    return [name for name, check in STYLE_CHECKS.items() if check(answer or "", today.year)]


def middle(values: list[float | None]) -> float | None:
    found = [value for value in values if value is not None]
    return round(median(found), 2) if found else None


def acceptance(records: list[dict[str, Any]]) -> dict[str, Any]:
    single = [
        record for record in records if not record["item"].get("expect_split") and not record["item"].get("turns")
    ]
    charted = [
        record for record in single
        if any(timing.get("make_chart") for turn in record["turns"] for timing in turn["timings"])
    ]
    texts = [timing.get("first_text") for record in records for turn in record["turns"] for timing in turn["timings"]]
    passed = sum(record["verdict"]["passed"] for record in records)
    return {
        "make_chart_share": round(len(charted) / len(single), 3) if single else None,
        "median_seconds": middle([record["seconds"] for record in records]),
        "median_first_text": middle(texts),
        "passed_share": round(passed / len(records), 3) if records else None,
    }


def baseline_acceptance(path: str) -> dict[str, Any] | None:
    if not path or not Path(path).exists():
        return None
    records = json.loads(Path(path).read_text(encoding="utf-8")).get("records", [])
    for record in records:
        for turn in record["turns"]:
            for timing, exchange in zip(turn["timings"], turn["exchanges"], strict=False):
                answered = [event["t"] for event in exchange["output"].get("events", []) if event["event"] == "answer"]
                timing.setdefault("first_text", answered[0] if answered else None)
    return acceptance(records)


def run_turn(
    client: Client, connection_id: UUID, user_id: str, conversation_id: str | None, turn: dict[str, Any],
) -> dict[str, Any]:
    body: dict[str, Any] = {"connection_id": str(connection_id), "question": turn["question"]}
    if user_id:
        body["user_id"] = user_id
    if conversation_id:
        body["conversation_id"] = conversation_id
    if turn.get("bogus_resume"):
        body["resume_id"] = str(uuid4())
    today = local_today()
    exchanges = [{"question": turn["question"], "output": client.chat(body)}]
    replies = list(turn.get("replies", []))
    while replies and exchanges[-1]["output"].get("status") == "needs_clarification":
        previous = exchanges[-1]["output"]
        reply = replies.pop(0)
        resume = {**body, "question": reply, "resume_id": previous["resume_id"]}
        if previous.get("conversation_id"):
            resume["conversation_id"] = previous["conversation_id"]
        exchanges.append({"question": reply, "output": client.chat(resume)})
    return {"today": today.isoformat(), "exchanges": exchanges}


def check_turn(turn: dict[str, Any], record: dict[str, Any], golds: list[dict[str, Any]]) -> dict[str, Any]:
    exchanges = record["exchanges"]
    final = exchanges[-1]["output"]
    expected_error = turn.get("expect_http_status")
    if expected_error is not None:
        status = final.get("http_status")
        problems = [] if status == expected_error else [f"HTTP {status}, mong đợi {expected_error}"]
        return {"passed": not problems, "problems": problems, "notes": [str(final.get("detail"))[:120]]}
    if final.get("http_status") != 200:
        return {"passed": False, "problems": [f"HTTP {final.get('http_status')}: {final.get('detail')}"], "notes": []}
    if final.get("error"):
        return {"passed": False, "problems": [f"event error: {final['error']}"], "notes": []}
    if not final.get("done") and final.get("events"):
        return {"passed": False, "problems": ["stream kết thúc không có done"], "notes": []}
    verdict = evaluate(turn, final, golds)
    paused = sum(1 for exchange in exchanges if exchange["output"].get("status") == "needs_clarification")
    if turn.get("expect_pause") and not paused:
        verdict["problems"].append("không hỏi lại bằng ask_user")
    if paused:
        verdict["notes"].append(f"tạm dừng {paused} lần")
    verdict["passed"] = not verdict["problems"]
    return verdict


def check_persistence(client: Client, user_id: str, records: list[dict[str, Any]]) -> list[str]:
    exchanges = [exchange for record in records for exchange in record["exchanges"]]
    outputs = [exchange["output"] for exchange in exchanges if exchange["output"].get("http_status") == 200]
    conversation_id = next((output.get("conversation_id") for output in outputs if output.get("conversation_id")), None)
    if not outputs:
        return []
    if conversation_id is None:
        return ["không có conversation_id"]
    problems = []
    if any(output.get("conversation_id") != conversation_id for output in outputs):
        problems.append("các lượt không cùng conversation_id")
    stored = client.turns(conversation_id, user_id)
    if len(stored) != len(outputs):
        problems.append(f"lưu {len(stored)} lượt, mong đợi {len(outputs)}")
    for index, (output, turn) in enumerate(zip(outputs, stored, strict=False)):
        if str(turn["id"]) != output.get("turn_id"):
            problems.append(f"lượt {index + 1}: turn_id khác")
        if turn["status"] != output.get("status"):
            problems.append(f"lượt {index + 1}: status lưu {turn['status']}, stream {output.get('status')}")
        if (turn.get("answer") or "") != (output.get("answer") or ""):
            problems.append(f"lượt {index + 1}: answer lưu khác answer stream")
        if output.get("status") == "needs_clarification" and turn.get("resume_id") != output.get("resume_id"):
            problems.append(f"lượt {index + 1}: resume_id lưu khác resume_id stream")
        previous = outputs[index - 1] if index else None
        waited = previous is not None and previous.get("status") == "needs_clarification"
        if waited and str(turn.get("continued_from")) != previous.get("turn_id"):
            problems.append(f"lượt {index + 1}: continued_from không trỏ về lượt hỏi lại")
    return problems


def agent_traces(trace_file: str, questions: set[str]) -> list[dict[str, Any]]:
    path = Path(trace_file) if trace_file else None
    if path is None or not path.exists():
        return []
    runs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record.get("question") in questions:
            runs.append(record)
    return runs


def resolve_connection(item: dict[str, Any], connection_id: UUID, paused_id: UUID | None) -> UUID:
    kind = item.get("connection")
    if kind == "unknown":
        return UUID(int=0)
    if kind == "paused":
        return paused_id or UUID(int=0)
    return connection_id


def main() -> None:
    args = parse_args()
    override_app_db(args.app_db)
    remap = host_mapper(args.source_host_map)
    connection_id = UUID(args.connection_id)
    items = json.loads(Path(args.questions).read_text(encoding="utf-8"))
    if args.only:
        wanted = {value.strip() for value in args.only.split(",") if value.strip()}
        items = [item for item in items if item["id"] in wanted or item["type"] in wanted]
    if args.repeat > 1:
        items = [{**item, "id": f"{item['id']}#{run}"} for item in items for run in range(1, args.repeat + 1)]
    local = threading.local()
    print_lock = threading.Lock()

    def client() -> Client:
        if not hasattr(local, "client"):
            local.client = Client(args.base_url, args.endpoint)
        return local.client

    def task(item: dict[str, Any], paused_id: UUID | None) -> dict[str, Any]:
        target = resolve_connection(item, connection_id, paused_id)
        user_id = "" if item.get("stateless") else args.user_id
        conversation_id = None
        turn_records = []
        for turn in item.get("turns") or [item]:
            record = run_turn(client(), target, user_id, conversation_id, turn)
            final = record["exchanges"][-1]["output"]
            conversation_id = final.get("conversation_id") or conversation_id
            day = date.fromisoformat(record["today"])
            golds = gold_rows(remap, connection_id, turn.get("gold", []), day) if turn.get("gold") else []
            record.update(
                question=turn["question"], gold=golds, verdict=check_turn(turn, record, golds),
                timings=[timings(exchange["output"]) for exchange in record["exchanges"]],
                style=style_flags(final.get("answer") or "", day),
            )
            turn_records.append(record)
        problems = [f"lượt {index + 1}: {problem}" if len(turn_records) > 1 else problem
                    for index, record in enumerate(turn_records) for problem in record["verdict"]["problems"]]
        notes = [note for record in turn_records for note in record["verdict"]["notes"]]
        if user_id and target == connection_id:
            persistence = check_persistence(client(), user_id, turn_records)
            problems.extend(f"lưu hội thoại: {problem}" for problem in persistence)
            if conversation_id and not args.keep_conversations:
                client().delete_conversation(conversation_id, user_id)
        questions = {
            answer.get("question") for record in turn_records for exchange in record["exchanges"]
            for answer in exchange["output"].get("answers", [])
        }
        result = {
            "item": item, "turns": turn_records, "verdict": {"passed": not problems, "problems": problems,
                                                             "notes": notes},
            "seconds": round(sum(t["total"] or 0 for record in turn_records for t in record["timings"]), 2),
            "agent_runs": agent_traces(args.trace_file, questions),
        }
        mark = "PASS" if not problems else "FAIL"
        with print_lock:
            print(f"[{mark}] {item['id']:7} {result['seconds']:6.1f}s {'; '.join(problems)} "
                  f"{'| ' + ', '.join(notes) if notes else ''}", flush=True)
        return result

    started = time.perf_counter()
    needs_paused = any(item.get("connection") == "paused" for item in items)
    with (
        paused_connection() if needs_paused else nullcontext() as paused_id,
        ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool,
    ):
        records = list(pool.map(lambda item: task(item, paused_id), items))
    summary: dict[str, dict[str, int]] = {}
    for record in records:
        bucket = summary.setdefault(record["item"]["type"], {"total": 0, "passed": 0})
        bucket["total"] += 1
        bucket["passed"] += int(record["verdict"]["passed"])
    passed = sum(bucket["passed"] for bucket in summary.values())
    print(f"Tổng: {passed}/{len(records)} đạt trong {time.perf_counter() - started:.0f}s")
    for kind, bucket in summary.items():
        print(f"  {kind:13} {bucket['passed']}/{bucket['total']}")
    events = Counter(
        event["event"] for record in records for turn in record["turns"] for exchange in turn["exchanges"]
        for event in exchange["output"].get("events", [])
    )
    styles = Counter(flag for record in records for turn in record["turns"] for flag in turn.get("style", []))
    print("Văn phong (số câu trả lời có):", ", ".join(f"{name} {styles[name]}" for name in STYLE_CHECKS))
    current = acceptance(records)
    before = baseline_acceptance(args.baseline)
    print("Nghiệm thu:      hiện tại | bản cũ")
    for key in ("make_chart_share", "median_seconds", "median_first_text", "passed_share"):
        print(f"  {key:18} {current[key]!s:>8} | {(before or {}).get(key)!s:>8}")
    out = Path(args.out) if args.out else HERE / "results" / f"{datetime.now():%Y%m%d-%H%M%S}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "today": local_today().isoformat(), "model": config.openrouter_model, "endpoint": args.endpoint,
        "summary": summary, "passed": passed, "total": len(records), "events": dict(events),
        "style": dict(styles), "acceptance": {"current": current, "baseline": before}, "records": records,
    }, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"Kết quả: {out}")


if __name__ == "__main__":
    main()
