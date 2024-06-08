from __future__ import annotations
from datetime import datetime
from typing import Annotated, Any, Optional

from flask import current_app
from pydantic import AliasPath, BaseModel, Field, computed_field


class Resource(BaseModel, frozen=True, strict=True):
    pass


class Attachment(Resource, frozen=True):
    mail_id: str = Field(exclude=True, validation_alias=AliasPath("mail", "id"))
    number: int

    name: Optional[str]
    type: str
    code: Optional[str]

    @computed_field  # type: ignore[misc]
    @property
    def self(self) -> Optional[str]:
        if not current_app:
            return None
        return current_app.url_for(
            "retrieve_attachment", mail_id=self.mail_id, number=self.number
        )


class Target(Resource, frozen=True):
    name: Optional[str]
    addr_spec: str

    def __str__(self) -> str:
        return f"{self.name} <{self.addr_spec}>"

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, str):
            return str(self) == other

        if not isinstance(other, Target):
            return NotImplemented

        return super().__eq__(other)


class Mail(Resource, frozen=True):
    id: str
    date: Annotated[datetime, Field(repr=False)]
    text: Annotated[str, Field(repr=False)]

    from_: Annotated[
        Optional[list[Target]], Field(repr=False, serialization_alias="from")
    ] = None
    sender: Annotated[Optional[Target], Field(repr=False)] = None
    reply_to: Annotated[
        Optional[list[Target]],
        Field(repr=False, serialization_alias="reply-to"),
    ] = None

    to: Annotated[Optional[list[Target]], Field(repr=False)] = None
    cc: Annotated[Optional[list[Target]], Field(repr=False)] = None
    bcc: Annotated[Optional[list[Target]], Field(repr=False)] = None

    subject: Annotated[Optional[str], Field(repr=False)] = None

    in_reply_to: Annotated[
        Optional[list[str]],
        Field(repr=False, serialization_alias="in-reply-to"),
    ] = None
    references: Annotated[Optional[list[str]], Field(repr=False)] = None

    attachments: list[Attachment]

    @computed_field  # type: ignore[misc]
    @property
    def self(self) -> Optional[str]:
        if not current_app:
            return None
        return current_app.url_for("retrieve_mail", id=self.id)
