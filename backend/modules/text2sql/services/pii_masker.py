import logging
import re
import threading
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from presidio_analyzer import AnalyzerEngine
    from presidio_anonymizer import AnonymizerEngine

logger = logging.getLogger(__name__)

LANGUAGE = "en"
PLACEHOLDER_FLAGGED = "PII"

VN_PHONE = "VN_PHONE_NUMBER"
VN_CITIZEN_ID = "VN_CITIZEN_ID"
VN_IDENTITY_CARD = "VN_IDENTITY_CARD"
VN_TAX_CODE = "VN_TAX_CODE"
VN_BANK_ACCOUNT = "VN_BANK_ACCOUNT"

# Phát hiện theo giá trị, không cần gợi ý từ tên cột.
VALUE_ENTITIES = ["EMAIL_ADDRESS", "PHONE_NUMBER", VN_PHONE, "CREDIT_CARD", "IBAN_CODE", "IP_ADDRESS"]
# Chuỗi số trần nên chỉ nhận khi tên cột gợi ý đúng loại giấy tờ.
HINTED_ENTITIES = [VN_CITIZEN_ID, VN_IDENTITY_CARD, VN_TAX_CODE, VN_BANK_ACCOUNT]

# Nhãn <LOẠI_n>; chấp nhận cả dạng LLM thoát Markdown (\<PII\_1\>) và bọc trong cặp dấu `.
PLACEHOLDER = re.compile(r"(`?)\\?<([A-Z][A-Z0-9]*(?:\\?_[A-Z][A-Z0-9]*)*)\\?_(\d+)\\?>\1")
# Đuôi có thể là phần đầu của một nhãn bị cắt giữa hai đoạn stream.
PLACEHOLDER_TAIL = re.compile(r"`?\\?(?:<[A-Z0-9_\\]{0,48})?$")

COLUMN_HINTS: tuple[tuple[re.Pattern[str], tuple[str, ...]], ...] = (
    (re.compile(r"\b(cccd|can cuoc|cmt|chung minh)\b"), (VN_CITIZEN_ID, VN_IDENTITY_CARD)),
    (re.compile(r"\bcmnd\b"), (VN_IDENTITY_CARD,)),
    (re.compile(r"\b(mst|ma so thue|tax)\b"), (VN_TAX_CODE,)),
    (re.compile(r"\b(stk|tai khoan|account|bank)\b"), (VN_BANK_ACCOUNT,)),
    (re.compile(r"\b(sdt|dien thoai|phone|mobile|tel)\b"), (VN_PHONE, "PHONE_NUMBER")),
    (re.compile(r"\b(email|mail)\b"), ("EMAIL_ADDRESS",)),
)


def build_analyzer() -> "AnalyzerEngine":
    # Nạp lười: spaCy và Presidio mất vài giây và nhiều bộ nhớ, chỉ cần khi thật sự che dữ liệu.
    import spacy
    from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer, RecognizerRegistry
    from presidio_analyzer.nlp_engine import SpacyNlpEngine
    from presidio_analyzer.predefined_recognizers import (
        CreditCardRecognizer,
        EmailRecognizer,
        IbanRecognizer,
        IpRecognizer,
        PhoneRecognizer,
    )
    from spacy.language import Language

    for name in ("presidio-analyzer", "presidio-anonymizer"):
        logging.getLogger(name).setLevel(logging.WARNING)

    if "lowercase_lemma" not in Language.factories:
        @Language.component("lowercase_lemma")
        def lowercase_lemma(doc: Any) -> Any:
            for token in doc:
                token.lemma_ = token.lower_
            return doc

    # Mô hình spaCy rỗng: chỉ dùng recognizer theo mẫu, không cần tải mô hình ngôn ngữ.
    class BlankNlpEngine(SpacyNlpEngine):
        def load(self) -> None:
            nlp = spacy.blank(LANGUAGE)
            nlp.add_pipe("lowercase_lemma")
            self.nlp = {LANGUAGE: nlp}

    def pattern(entity: str, regex: str, score: float) -> PatternRecognizer:
        return PatternRecognizer(
            supported_entity=entity, patterns=[Pattern(entity.lower(), regex, score)], supported_language=LANGUAGE,
        )

    registry = RecognizerRegistry(supported_languages=[LANGUAGE])
    for recognizer in (
        EmailRecognizer(supported_language=LANGUAGE),
        CreditCardRecognizer(supported_language=LANGUAGE),
        IbanRecognizer(supported_language=LANGUAGE),
        IpRecognizer(supported_language=LANGUAGE),
        PhoneRecognizer(supported_language=LANGUAGE, supported_regions=("VN", "US", "GB", "SG", "JP", "KR", "CN")),
        pattern(
            VN_PHONE, r"(?<!\d)(?:\+84|84|0)[\s.\-]?(?:3[2-9]|5[25689]|7[06-9]|8[1-9]|9\d)(?:[\s.\-]?\d){7}(?!\d)",
            0.75,
        ),
        pattern(VN_CITIZEN_ID, r"(?<!\d)\d{12}(?!\d)", 0.3),
        pattern(VN_IDENTITY_CARD, r"(?<!\d)\d{9}(?!\d)", 0.3),
        pattern(VN_TAX_CODE, r"(?<!\d)\d{10}(?:-\d{3})?(?!\d)", 0.3),
        pattern(VN_BANK_ACCOUNT, r"(?<!\d)\d{8,16}(?!\d)", 0.3),
    ):
        registry.add_recognizer(recognizer)
    engine = BlankNlpEngine(models=[{"lang_code": LANGUAGE, "model_name": "blank"}])
    engine.load()
    return AnalyzerEngine(registry=registry, nlp_engine=engine, supported_languages=[LANGUAGE])


@lru_cache(maxsize=1)
def get_analyzer() -> "AnalyzerEngine":
    return build_analyzer()


@lru_cache(maxsize=1)
def get_anonymizer() -> "AnonymizerEngine":
    from presidio_anonymizer import AnonymizerEngine

    return AnonymizerEngine()


def warm_up_masker() -> None:
    # Nạp sẵn khi khởi động để câu hỏi đầu tiên không phải chờ vài giây; lỗi thì để lần che đầu tiên nạp lại.
    try:
        get_analyzer()
        get_anonymizer()
    except Exception:
        logger.exception("Không nạp sẵn được Presidio")


def _plain(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.casefold().replace("đ", "d"))
    return " ".join("".join(char for char in decomposed if unicodedata.category(char) != "Mn").split())


def hinted_entities(column_label: str, column_name: str) -> list[str]:
    text = _plain(f"{column_label} {column_name.replace('_', ' ')}")
    found: list[str] = []
    for pattern, entities in COLUMN_HINTS:
        if pattern.search(text):
            found.extend(entity for entity in entities if entity not in found)
    return found


@dataclass(frozen=True)
class MaskColumn:
    label: str
    name: str
    flagged: bool = False


@dataclass
class PiiReport:
    masked_columns: list[str] = field(default_factory=list)
    detected: dict[str, int] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.masked_columns or self.detected)


def split_placeholder_tail(text: str) -> tuple[str, str]:
    tail = PLACEHOLDER_TAIL.search(text)
    start = tail.start() if tail is not None else len(text)
    return text[:start], text[start:]


def anonymous_placeholders(text: str) -> str:
    # Bỏ số thứ tự: lượt sau đánh số lại từ đầu nên <PII_1> của lượt trước có thể là người khác.
    return PLACEHOLDER.sub(lambda match: f"<{match.group(2).replace("\\", "")}>", text)


class _Placeholders:
    def __init__(self) -> None:
        self.ids: dict[tuple[str, str], str] = {}
        self.counts: dict[str, int] = defaultdict(int)
        self.values: dict[str, str] = {}

    def get(self, entity: str, raw: str, seen: set[tuple[str, str]]) -> str:
        key = (entity, raw)
        seen.add(key)
        if key not in self.ids:
            self.counts[entity] += 1
            self.ids[key] = f"<{entity}_{self.counts[entity]}>"
            self.values[self.ids[key]] = raw
        return self.ids[key]

    def restore(self, values: dict[str, str]) -> None:
        for placeholder, raw in values.items():
            match = PLACEHOLDER.fullmatch(placeholder)
            if match is None:
                continue
            entity, number = match.group(2), int(match.group(3))
            self.ids[(entity, raw)] = placeholder
            self.values[placeholder] = raw
            self.counts[entity] = max(self.counts[entity], number)


# Một masker dùng cho một lượt hỏi: cùng một giá trị luôn nhận cùng một nhãn ở mọi kết quả của lượt, và câu trả lời
# cuối được thay nhãn về giá trị thật trước khi tới người dùng.
class PiiMasker:
    def __init__(self, threshold: float = 0.5, values: dict[str, str] | None = None) -> None:
        self.threshold = threshold
        self.placeholders = _Placeholders()
        self.lock = threading.Lock()
        if values:
            self.placeholders.restore(values)

    @property
    def values(self) -> dict[str, str]:
        with self.lock:
            return dict(self.placeholders.values)

    def unmask(self, text: str) -> str:
        values = self.values
        if not values or "<" not in text:
            return text

        def replace(match: re.Match[str]) -> str:
            placeholder = f"<{match.group(2).replace("\\", "")}_{match.group(3)}>"
            return values.get(placeholder, match.group(0))

        return PLACEHOLDER.sub(replace, text)

    def unmask_value(self, value: Any) -> Any:
        # Dữ liệu JSON (dòng, spec biểu đồ): thay trong mọi chuỗi, kể cả khóa (ví dụ colors.assign theo giá trị).
        if isinstance(value, str):
            return self.unmask(value)
        if isinstance(value, list):
            return [self.unmask_value(item) for item in value]
        if isinstance(value, dict):
            return {self.unmask_value(key): self.unmask_value(item) for key, item in value.items()}
        return value

    def mask(self, columns: list[MaskColumn], rows: list[list[Any]]) -> tuple[list[list[Any]], PiiReport]:
        with self.lock:
            return self._mask(columns, rows)

    def _mask(self, columns: list[MaskColumn], rows: list[list[Any]]) -> tuple[list[list[Any]], PiiReport]:
        seen: set[tuple[str, str]] = set()
        hints = [hinted_entities(column.label, column.name) for column in columns]
        analyzed: dict[tuple[str, tuple[str, ...]], list[Any]] = {}
        masked_rows: list[list[Any]] = []
        touched: set[int] = set()
        for row in rows:
            masked: list[Any] = []
            for index, value in enumerate(row):
                column = columns[index]
                # Cột đánh dấu PII phải che mọi giá trị khác None, kể cả số và bool.
                if column.flagged and value is not None and not isinstance(value, str):
                    value = str(value)
                if not isinstance(value, str) or not value.strip():
                    masked.append(value)
                    continue
                masked.append(self._mask_value(value, column, hints[index], analyzed, seen))
                if column.flagged:
                    touched.add(index)
            masked_rows.append(masked)
        detected: dict[str, int] = defaultdict(int)
        for entity, _ in seen:
            detected[entity] += 1
        report = PiiReport(
            masked_columns=[column.label for index, column in enumerate(columns) if index in touched],
            detected=dict(sorted(detected.items())),
        )
        return masked_rows, report

    def _mask_value(
        self, value: str, column: MaskColumn, hints: list[str],
        analyzed: dict[tuple[str, tuple[str, ...]], list[Any]], seen: set[tuple[str, str]],
    ) -> str:
        key = (value, tuple(hints))
        if key not in analyzed:
            analyzed[key] = self._analyze(value, hints)
        results = analyzed[key]
        if results:
            return self._anonymize(value, results, seen)
        if column.flagged:
            return self.placeholders.get(PLACEHOLDER_FLAGGED, value, seen)
        return value

    def _analyze(self, value: str, hints: list[str]) -> list[Any]:
        analyzer = get_analyzer()
        results = analyzer.analyze(
            text=value, language=LANGUAGE, entities=VALUE_ENTITIES, score_threshold=self.threshold,
        )
        wanted = [entity for entity in hints if entity in HINTED_ENTITIES]
        if wanted:
            results += analyzer.analyze(text=value, language=LANGUAGE, entities=wanted, score_threshold=0.0)
        return self._without_overlaps(results)

    @staticmethod
    def _without_overlaps(results: list[Any]) -> list[Any]:
        kept: list[Any] = []
        for result in sorted(results, key=lambda item: (-item.score, item.start - item.end)):
            if all(result.end <= other.start or result.start >= other.end for other in kept):
                kept.append(result)
        return sorted(kept, key=lambda item: item.start)

    def _anonymize(self, value: str, results: list[Any], seen: set[tuple[str, str]]) -> str:
        from presidio_anonymizer.entities import OperatorConfig

        entities = {result.entity_type for result in results}
        operators = {
            entity: OperatorConfig(
                "custom", {"lambda": lambda raw, entity=entity: self.placeholders.get(entity, raw, seen)},
            )
            for entity in entities
        }
        return get_anonymizer().anonymize(text=value, analyzer_results=results, operators=operators).text
