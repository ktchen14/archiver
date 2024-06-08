import contextlib
import email.utils
from email.headerregistry import AddressHeader
from email.parser import BytesParser
from email.policy import default as DEFAULT_POLICY  # noqa: N812
from typing import Optional

from django_mailman3.lib.scrub import Scrubber  # type: ignore
from magic import Magic, MagicException

from archiver.database import Attachment, Mail
from archiver.resource import Attachment as AttachmentResource
from archiver.resource import Mail as MailResource
from archiver.resource import Target

MAGIC = Magic(mime=True, mime_encoding=True)
PARSER = BytesParser(policy=DEFAULT_POLICY)


def load_mail_record(origin: bytes) -> Mail:
    """Create a Mail object from the RFC 5322 email message in *origin*."""

    message = PARSER.parsebytes(origin)

    id = email.utils.unquote(message["Message-ID"])
    date = message["Date"].datetime

    text, attachments = Scrubber(message).scrub()
    text = text.strip()

    mail = Mail(id=id, date=date, text=text, data=origin)

    number: int
    name: str
    type: str
    code: Optional[str]
    data: bytes | str
    for number, name, type, code, data in attachments:
        attachment = Attachment(number=number, name=name)

        if type in ("application/octet-stream", "text/plain"):
            type, code = estimate_type(data) or (type, code)

        if type.startswith("text/") and isinstance(data, bytes):
            with contextlib.suppress(ValueError):
                data = data.decode(code or "utf-8")

        if isinstance(data, str):
            data, code = data.encode(code or "utf-8"), "utf-8"
        attachment.data = data

        if type.startswith("text/") and code is not None:
            attachment.code = code
        attachment.type = type

        mail.attachments.append(attachment)

    return mail


def load_mail_resource(mail: Mail) -> MailResource:
    """Create a Mail resource from the Mail record."""

    message = PARSER.parsebytes(mail.data, headersonly=True)

    if (from_ := message["From"]) is not None:
        from_ = unroll(from_)

    if (sender := message["Sender"]) is not None:
        sender = sender.address
        sender = Target(name=sender.display_name, addr_spec=sender.addr_spec)

    if (reply_to := message["Reply-To"]) is not None:
        reply_to = unroll(reply_to)

    if (to := message["To"]) is not None:
        to = unroll(to)

    if (cc := message["Cc"]) is not None:
        cc = unroll(cc)

    if (bcc := message["Bcc"]) is not None:
        bcc = unroll(bcc)

    if (in_reply_to := message["In-Reply-To"]) is not None:
        in_reply_to = [email.utils.unquote(i) for i in in_reply_to.split()]

    if (references := message["References"]) is not None:
        references = [email.utils.unquote(i) for i in references.split()]

    if (subject := message["Subject"]) is not None:
        subject = subject.strip()

    attachments = [
        AttachmentResource.model_validate(attachment, from_attributes=True)
        for attachment in mail.attachments
    ]

    return MailResource(
        id=mail.id,
        date=mail.date,
        text=mail.text,
        from_=from_,
        sender=sender,
        reply_to=reply_to,
        to=to,
        cc=cc,
        bcc=bcc,
        in_reply_to=in_reply_to,
        references=references,
        subject=subject,
        attachments=attachments,
    )


def unroll(header: AddressHeader) -> list[Target]:
    """Unroll the address *header* into a list of addresses."""

    result = []
    for address in header.addresses:
        target = Target(name=address.display_name, addr_spec=address.addr_spec)
        if target not in result:
            result.append(target)
    return result


def estimate_type(data: bytes | str) -> Optional[tuple[str, str]]:
    """Guess the Content-Type and charset of *data*."""

    try:
        estimate = MAGIC.from_buffer(data)
    except MagicException:
        return None

    if estimate is None:
        return None

    header = DEFAULT_POLICY.header_factory("Content-Type", estimate)
    return (header.content_type, header.params.get("charset"))
