import time
from collections.abc import Callable

from backend.agent_package.tool_agent import TextStream

from .chat_events import ANSWER_DELTA, ANSWER_RESET, Emit, delta_event, reset_event

MIN_CHARS = 32
MAX_DELAY = 0.05

Clock = Callable[[], float]


class DeltaBuffer:
    def __init__(
        self, emit: Emit, position: int | None, final: bool, min_chars: int = MIN_CHARS,
        max_delay: float = MAX_DELAY, clock: Clock = time.monotonic,
    ) -> None:
        self.emit = emit
        self.position = position
        self.final = final
        self.min_chars = min_chars
        self.max_delay = max_delay
        self.clock = clock
        self.round: int | None = None
        self.pending = ""
        self.last_flush: float | None = None

    def delta(self, round_: int, text: str) -> None:
        if self.round is not None and round_ != self.round:
            self.flush()
        self.round = round_
        self.pending += text
        due = self.last_flush is None or self.clock() - self.last_flush >= self.max_delay
        if len(self.pending) >= self.min_chars or due:
            self.flush()

    def end(self, round_: int, discard: bool) -> None:
        self.flush()
        if discard:
            self.emit(ANSWER_RESET, reset_event(self.position, round_))

    def flush(self) -> None:
        if not self.pending or self.round is None:
            return
        text, self.pending = self.pending, ""
        self.last_flush = self.clock()
        self.emit(ANSWER_DELTA, delta_event(self.position, self.round, self.final, text))

    def text_stream(self) -> TextStream:
        return TextStream(delta=self.delta, end=self.end)


class SynthesizeStream:
    def __init__(self, emit: Emit, clock: Clock = time.monotonic) -> None:
        self.buffer = DeltaBuffer(emit, None, True, clock=clock)

    def delta(self, text: str) -> None:
        self.buffer.delta(0, text)

    def close(self) -> None:
        self.buffer.flush()
