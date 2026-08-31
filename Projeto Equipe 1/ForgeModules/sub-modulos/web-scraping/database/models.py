"""Modelos SQLAlchemy normalizados."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class DataSource(Base):
    """Fonte de dados configurável (API, scraper ou portal)."""

    __tablename__ = "data_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    base_url: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    updates: Mapped[list["EventUpdate"]] = relationship(back_populates="source")


class Location(Base):
    """Localização associada aos eventos acadêmicos."""

    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    updates: Mapped[list["EventUpdate"]] = relationship(back_populates="location")


class EventUpdate(Base):
    """Registro de atualização coletada (histórico completo)."""

    __tablename__ = "event_updates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"), nullable=False)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    source: Mapped["DataSource"] = relationship(back_populates="updates")
    location: Mapped["Location"] = relationship(back_populates="updates")
    metrics: Mapped[list["EventMetric"]] = relationship(
        back_populates="update", cascade="all, delete-orphan"
    )


class EventMetric(Base):
    """Métricas normalizadas de cada atualização."""

    __tablename__ = "event_metrics"
    __table_args__ = (UniqueConstraint("update_id", "metric_key", name="uq_update_metric"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    update_id: Mapped[int] = mapped_column(ForeignKey("event_updates.id", ondelete="CASCADE"))
    metric_key: Mapped[str] = mapped_column(String(50), nullable=False)
    metric_value: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)

    update: Mapped["EventUpdate"] = relationship(back_populates="metrics")


class CollectorStatus(Base):
    """Status em tempo real do coletor."""

    __tablename__ = "collector_status"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    is_running: Mapped[bool] = mapped_column(Boolean, default=False)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_message: Mapped[str | None] = mapped_column(Text)
    total_records: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
