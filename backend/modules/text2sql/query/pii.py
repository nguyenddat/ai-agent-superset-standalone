import logging
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from presidio_analyzer import AnalyzerEngine
    from presidio_anonymizer import AnonymizerEngine

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
    scan: bool
    flagged: bool


@dataclass
class PiiReport:
    masked_columns: list[str] = field(default_factory=list)
    detected: dict[str, int] = field(default_factory=dict)


class _Placeholders:
    def __init__(self) -> None:
        self.ids: dict[tuple[str, str], str] = {}
        self.counts: dict[str, int] = defaultdict(int)

    def get(self, entity: str, raw: str) -> str:
        key = (entity, raw)
        if key not in self.ids:
            self.counts[entity] += 1
            self.ids[key] = f"<{entity}_{self.counts[entity]}>"
        return self.ids[key]


class PiiMasker:
    def __init__(self, threshold: float = 0.5) -> None:
        self.threshold = threshold

    def mask(self, columns: list[MaskColumn], rows: list[list[Any]]) -> tuple[list[list[Any]], PiiReport]:
        placeholders = _Placeholders()
        report = PiiReport()
        hints = [hinted_entities(column.label, column.name) if column.scan else [] for column in columns]
        analyzed: dict[tuple[str, tuple[str, ...]], list[Any]] = {}
        masked_rows: list[list[Any]] = []
        for row in rows:
            masked: list[Any] = []
            for index, value in enumerate(row):
                column = columns[index]
                # Cột đánh dấu PII phải che mọi giá trị khác None, kể cả số, bool (format_cell giữ nguyên kiểu).
                if column.flagged and value is not None and not isinstance(value, str):
                    value = str(value)
                if not (column.scan or column.flagged) or not isinstance(value, str) or not value.strip():
                    masked.append(value)
                    continue
                masked.append(self._mask_value(value, column, hints[index], placeholders, analyzed))
            masked_rows.append(masked)
        report.masked_columns = [column.label for column in columns if column.flagged]
        report.detected = {entity: count for entity, count in sorted(placeholders.counts.items())}
        return masked_rows, report

    def _mask_value(
        self, value: str, column: MaskColumn, hints: list[str], placeholders: _Placeholders,
        analyzed: dict[tuple[str, tuple[str, ...]], list[Any]],
    ) -> str:
        key = (value, tuple(hints))
        if key not in analyzed:
            analyzed[key] = self._analyze(value, hints)
        results = analyzed[key]
        if results:
            return self._anonymize(value, results, placeholders)
        if column.flagged:
            return placeholders.get(PLACEHOLDER_FLAGGED, value)
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

    @staticmethod
    def _anonymize(value: str, results: list[Any], placeholders: _Placeholders) -> str:
        from presidio_anonymizer.entities import OperatorConfig

        entities = {result.entity_type for result in results}
        operators = {
            entity: OperatorConfig("custom", {"lambda": lambda raw, entity=entity: placeholders.get(entity, raw)})
            for entity in entities
        }
        return get_anonymizer().anonymize(text=value, analyzer_results=results, operators=operators).text
