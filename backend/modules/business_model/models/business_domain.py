
from sqlalchemy import Column, ForeignKey, String, Table, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from backend.common.base_model import AuditedModel, Base

business_domain_tables = Table(
    "business_domain_tables",
    Base.metadata,
    Column("domain_id", Uuid(as_uuid=True), ForeignKey("business_domains.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "table_dictionary_id", Uuid(as_uuid=True), ForeignKey("table_dictionaries.id", ondelete="CASCADE"),
        primary_key=True, index=True,
    ),
)


class BusinessDomain(AuditedModel):
    __tablename__ = "business_domains"

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    color: Mapped[str | None] = mapped_column(String(16))
