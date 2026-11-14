from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint, Uuid, false, true
from sqlalchemy.orm import Mapped, mapped_column

from backend.common.base_model import AuditedModel


class LineageEdge(AuditedModel):
    __tablename__ = "lineage_edges"
    __table_args__ = (
        UniqueConstraint("source_table_dictionary_id", "target_table_dictionary_id", "kind"),
    )

    source_table_dictionary_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("table_dictionaries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_table_dictionary_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("table_dictionaries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    label: Mapped[str | None] = mapped_column(String(32))
    is_hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    is_manual: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    color: Mapped[str | None] = mapped_column(String(16))
