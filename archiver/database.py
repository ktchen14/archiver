from __future__ import annotations
from datetime import datetime
from typing import Optional, Self

from sqlalchemy import DateTime, ForeignKey, Identity, Select, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Record(DeclarativeBase):
    type_annotation_map = {datetime: DateTime(timezone=True)}


class Mail(Record):
    __tablename__ = "mail"

    id: Mapped[str] = mapped_column(primary_key=True)
    date: Mapped[datetime]
    text: Mapped[str]
    data: Mapped[bytes]

    attachments: Mapped[list[Attachment]] = relationship(
        back_populates="mail",
        order_by=lambda: Attachment.number.asc(),
        passive_deletes="all",
    )

    dispatches: Mapped[list[Dispatch]] = relationship(
        back_populates="mail",
        order_by=lambda: Dispatch.next_time.asc(),
        passive_deletes="all",
    )

    def __repr__(self) -> str:
        return f"Mail<{self.id}>"

    @classmethod
    def consumer_select(cls, consumer: Consumer) -> Select[tuple[Self]]:
        """Return a Select on Mail filtered by *consumer*."""

        stmt = select(cls).select_from(Dispatch).filter_by(consumer=consumer)
        return stmt.join(Dispatch.mail)


class Attachment(Record):
    __tablename__ = "attachment"

    mail_id: Mapped[str] = mapped_column(ForeignKey(Mail.id), primary_key=True)
    mail: Mapped[Mail] = relationship(back_populates="attachments")

    number: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[Optional[str]]
    type: Mapped[str]
    code: Mapped[Optional[str]]
    data: Mapped[bytes] = mapped_column(deferred_raiseload=True)

    def __repr__(self) -> str:
        return f"Attachment<{self.mail.id}#{self.number}>"


class Consumer(Record):
    __tablename__ = "consumer"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)

    dispatches: Mapped[list[Dispatch]] = relationship(
        back_populates="consumer",
        order_by=lambda: Dispatch.next_time.asc(),
        passive_deletes="all",
    )

    name: Mapped[str]


class Dispatch(Record):
    __tablename__ = "dispatch"

    consumer_id: Mapped[int] = mapped_column(
        ForeignKey(Consumer.id), primary_key=True
    )
    consumer: Mapped[Consumer] = relationship(back_populates="dispatches")

    mail_id: Mapped[str] = mapped_column(ForeignKey(Mail.id), primary_key=True)
    mail: Mapped[Mail] = relationship(back_populates="dispatches")

    last_time: Mapped[Optional[datetime]]
    next_time: Mapped[datetime] = mapped_column(server_default="NOW()")

    created_at: Mapped[datetime] = mapped_column(server_default="NOW()")
