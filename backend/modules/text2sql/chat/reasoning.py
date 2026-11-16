from ..dataset.field_service import FindFieldsOut
from ..dataset.join_schemas import JoinOption, JoinPlan
from ..vector_store.ingestion.documents.context import CatalogContext
from .analysis_context import QueryReport
from .dataset_flow import MappedDatasetPlan, describe_option
from .planner import MetricCandidate, PlannedQuery
from .service import MAX_CANDIDATES, CandidateSearch

MAX_LISTED_FIELDS = 6
LINK_REASONS = {
    "glossary_link": "liên kết với thuật ngữ đã chọn khi viết lại câu hỏi",
    "rule_link": "liên kết với quy tắc chuyên gia đã chọn khi viết lại câu hỏi",
}
TO_DATASET = (
    "Chuyển sang luồng dataset: tìm trực tiếp các cột liên quan trong data dictionary, lập kế hoạch rồi để server tự "
    "nối bảng."
)
MATCH_LEVELS = {
    "ok": "Các cột đã được Jev chấm điểm và chỉ giữ cột đạt ngưỡng liên quan.",
    "unverified": "Chưa chấm được điểm liên quan bằng Jev (không bật hoặc lỗi) nên các cột chỉ mang tính tham khảo.",
}


def _metric_label(candidate: MetricCandidate) -> str:
    return candidate.metric.label or candidate.metric.name


def metric_search_lines(search: CandidateSearch) -> list[str]:
    lines = [f"Giữ metric '{_metric_label(item)}' vì {LINK_REASONS.get(item.source, 'liên kết với tri thức đã chọn')}."
             for item in search.linked]
    linked = {item.metric.id for item in search.linked}
    for item in search.kept:
        label = _metric_label(item.candidate)
        if item.candidate.metric.id in linked:
            continue
        if item.score is None:
            lines.append(f"Giữ metric '{label}' theo tìm kiếm ngữ nghĩa (chưa chấm được điểm Jev).")
        else:
            lines.append(
                f"Giữ metric '{label}': điểm Jev {item.score:.2f} đạt ngưỡng {search.threshold:.2f}."
            )
    for item in search.dropped:
        lines.append(
            f"Loại metric '{_metric_label(item.candidate)}': điểm Jev {(item.score or 0.0):.2f} dưới ngưỡng "
            f"{search.threshold:.2f}."
        )
    total = len(search.linked) + len([item for item in search.kept if item.candidate.metric.id not in linked])
    if total > MAX_CANDIDATES:
        lines.append(f"Chỉ giữ {MAX_CANDIDATES} ứng viên đầu tiên để lập kế hoạch.")
    if not search.candidates:
        lines.append("Không có metric nào đủ liên quan tới câu hỏi. " + TO_DATASET)
    return lines


def metric_rule_lines(planned: list[PlannedQuery]) -> list[str]:
    lines: list[str] = []
    for item in planned:
        label = item.metric.label or item.metric.name
        for rule in item.rules:
            if rule.filters:
                lines.append(f"Metric '{label}': áp dụng quy tắc '{rule.name}' ({'; '.join(rule.filters)}).")
            if rule.overridden:
                lines.append(
                    f"Metric '{label}': quy tắc '{rule.name}' nhường điều kiện {'; '.join(rule.overridden)} vì câu "
                    "hỏi đã lọc riêng trên cùng cột."
                )
    return lines


def query_line(report: QueryReport, label: str | None = None) -> str:
    subject = f"Truy vấn metric '{label}'" if label else "Truy vấn"
    line = f"{subject} chạy xong, trả về {report.row_count} dòng"
    if report.truncated:
        line += ", đã bị cắt ở giới hạn số dòng tối đa"
    line += "."
    if report.pii.masked_columns:
        line += " Các cột chứa dữ liệu cá nhân đã được che: " + ", ".join(report.pii.masked_columns) + "."
    return line


def field_lines(found: FindFieldsOut) -> list[str]:
    if found.match == "none" or not found.tables:
        return ["Không tìm thấy cột nào đủ liên quan tới câu hỏi nên dừng, không đoán."]
    count = sum(len(table.fields) for table in found.tables)
    lines = [f"Tìm được {count} cột liên quan trong {len(found.tables)} bảng."]
    for table in found.tables:
        names = [item.display_name for item in table.fields[:MAX_LISTED_FIELDS]]
        more = len(table.fields) - len(names)
        lines.append(f"Bảng {table.display_name}: " + ", ".join(names) + (f" và {more} cột khác." if more else "."))
    if found.match in MATCH_LEVELS:
        lines.append(MATCH_LEVELS[found.match])
    return lines


def mapping_lines(mapped: MappedDatasetPlan, catalog: CatalogContext) -> list[str]:
    tables = [catalog.tables[item].label for item in mapped.table_ids]
    lines = [
        f"Ánh xạ kế hoạch thành công: bảng gốc {catalog.tables[mapped.root_table_id].label}, dùng {len(tables)} bảng "
        f"({', '.join(tables)})."
    ]
    if mapped.added_tables:
        added = ", ".join(mapped.added_tables)
        lines.append(f"Tự thêm bảng có cột được dùng nhưng kế hoạch chưa liệt kê: {added}.")
    return lines


def _option_lines(catalog: CatalogContext, option: JoinOption) -> list[str]:
    described = describe_option(catalog, option)
    lines = [f"Bảng gốc: {described['root_table']}."]
    for step, join in zip(option.steps, described["joins"], strict=True):
        line = f"LEFT JOIN: {join}."
        if step.multiplies_rows:
            line += " Bước này có thể nhân số dòng (quan hệ một-nhiều)."
        lines.append(line)
    lines += option.warnings
    return lines


def join_lines(join: JoinPlan, catalog: CatalogContext, used: set[str] | None = None) -> list[str]:
    if join.status == "not_declared":
        return ["Các bảng cần dùng chưa được khai báo quan hệ với nhau nên không tự nối: " + join.message]
    if join.status == "ambiguous":
        lines = [f"Có {len(join.options)} cách nối hợp lệ; không tự chọn mà hỏi lại người dùng."]
        for number, option in enumerate(join.options, start=1):
            text = f"Cách {number}: {describe_option(catalog, option)['description']}"
            if used and option.signature in used:
                text += " (đã dùng trước đây)"
            lines.append(text + ".")
        return lines
    option = join.options[0]
    if not option.steps:
        return [f"Chỉ cần một bảng ({catalog.tables[option.root_table_id].label}), không phải nối."]
    return ["Chỉ có một cách nối hợp lệ nên dùng luôn.", *_option_lines(catalog, option)]


def store_line(dataset_saved: bool, created: bool, added: int, warning: str | None) -> str:
    if not dataset_saved:
        return warning or "Không lưu được dataset cho lần truy vấn này."
    line = "Tạo dataset mới cho cách nối này" if created else "Dùng lại dataset đã lưu với cùng cách nối"
    line += f", thêm {added} cột mới." if added else ", không cần thêm cột."
    if warning:
        line += f" {warning}"
    return line
