from __future__ import annotations
import contextlib
import re
from datetime import timedelta
from typing import TYPE_CHECKING, Any, Optional, cast

import jwt
from flask import Flask, g, jsonify, make_response, request
from psycopg import Connection, Notify
from sqlalchemy import create_engine, delete, func, select, text, update
from sqlalchemy.orm import (
    Session,
    aliased,
    contains_eager,
    defer,
    joinedload,
    lazyload,
    load_only,
    scoped_session,
    selectinload,
    sessionmaker,
)
from werkzeug.datastructures import WWWAuthenticate
from werkzeug.utils import get_content_type

from archiver.database import Attachment, Consumer, Dispatch, Mail
from archiver.loader import load_mail_resource
from archiver.resource import Attachment as AttachmentResource

if TYPE_CHECKING:
    from collections.abc import Iterator
    from wsgiref.types import WSGIEnvironment

    from flask.typing import ResponseReturnValue as View

server = Flask(__name__)

engine = create_engine("postgresql+psycopg:///")
database = scoped_session(sessionmaker(engine, expire_on_commit=False))


@server.teardown_appcontext
def remove_database(exception: Optional[BaseException] = None) -> None:
    database.remove()


@server.before_request
def authenticate() -> Optional[View]:
    """Authenticate and record the consumer in *g.consumer*."""

    if request.routing_exception is not None:
        return None

    authorization = request.authorization
    if authorization is None or authorization.type != "bearer":
        return reject()

    if not (token := authorization.token):
        return reject(error="invalid_request")

    secret = server.secret_key
    try:
        data = jwt.decode(
            token, secret, algorithms=["HS256"], options={"require": ["sub"]}
        )
    except jwt.exceptions.InvalidTokenError:
        return reject(error="invalid_token")

    if not (m := re.match(r"^consumer_id=([0-9]+)$", data["sub"])):
        return reject(error="invalid_token")

    if (consumer := database.get(Consumer, int(m.group(1)))) is None:
        return "Forbidden", 403

    g.consumer = consumer


def reject(**kwargs: str | None) -> View:
    """Return 401 with a custom WWW-Authenticate header."""

    kwargs = {"realm": request.host, **kwargs}
    r = make_response("Unauthorized", 401)
    r.www_authenticate = WWWAuthenticate("bearer", kwargs)
    return r


@server.route("/mail/<string:id>", methods=["GET"])
def retrieve_mail(id: str) -> View:
    """Retrieve the mail identified by *id*."""

    mime = ("text/plain", "application/json", "message/rfc822")
    if request.accept_mimetypes:
        mimetype = request.accept_mimetypes.best_match(mime)
    else:
        mimetype = "application/json"

    if mimetype in ("text/plain", "message/rfc822"):
        return retrieve_mail_as_text(id, mimetype)

    if mimetype == "application/json":
        return retrieve_mail_as_json(id)

    stmt = Mail.consumer_select(g.consumer).filter_by(id=id)
    if not database.scalar(select(stmt.exists())):
        return "Not Found", 404

    return "Not Acceptable", 406


def retrieve_mail_as_text(id: str, mimetype: str) -> View:
    """Retrieve the mail identified by *id* as text."""

    stmt = Mail.consumer_select(g.consumer).filter_by(id=id)
    stmt = stmt.options(load_only(Mail.data, raiseload=True))
    if (mail := database.scalars(stmt).one_or_none()) is None:
        return "Not Found", 404

    data = mail.data.decode("utf-8")
    return server.response_class(data, mimetype=mimetype)


def retrieve_mail_as_json(id: str) -> View:
    """Retrieve the mail identified by *id* as JSON."""

    stmt = Mail.consumer_select(g.consumer).filter_by(id=id)
    stmt = stmt.options(joinedload(Mail.attachments))
    if (mail := database.scalars(stmt).unique().one_or_none()) is None:
        return "Not Found", 404

    resource = load_mail_resource(mail)
    return resource.model_dump(mode="json", by_alias=True)


@server.route("/mail/<string:id>", methods=["DELETE"])
def delete_mail(id: str) -> View:
    """Delete the consumer's dispatch identified by *id*."""

    stmt = delete(Dispatch).where(
        Dispatch.mail_id == id, Dispatch.consumer == g.consumer
    )
    result = database.execute(stmt).rowcount
    database.commit()

    return ("Not Found", 404) if result == 0 else ("", 200)


@server.route("/mail/<string:mail_id>/attachment/<int:number>")
def retrieve_attachment(mail_id: str, number: int) -> View:
    """Retrieve the attachment identified by *mail_id* and *number*."""

    stmt = (
        select(Attachment)
        .select_from(Dispatch)
        .filter_by(consumer=g.consumer)
        .join(Dispatch.mail)
        .filter_by(id=mail_id)
        .join(Mail.attachments)
        .filter_by(number=number)
        .with_for_update(of=Attachment, read=True)
        .options(contains_eager(Attachment.mail))
        .options(defer(Attachment.data))
    )
    if (attachment := database.scalars(stmt).one_or_none()) is None:
        return "Not Found", 404

    mime: tuple[str, ...] = (attachment.type, "application/json")
    if attachment.type.startswith("text/"):
        mime = (*mime, "text/plain")
    mime = (*mime, "application/octet-stream")

    if request.accept_mimetypes:
        mimetype = request.accept_mimetypes.best_match(mime)
    else:
        mimetype = "application/json"

    if mimetype == attachment.type:
        return retrieve_attachment_as_native(attachment)

    if mimetype == "text/plain":
        return retrieve_attachment_as_text(attachment)

    if mimetype == "application/json":
        return retrieve_attachment_as_json(attachment)

    if mimetype == "application/octet-stream":
        return retrieve_attachment_as_byte(attachment)

    return "Not Acceptable", 406


def retrieve_attachment_as_text(attachment: Attachment) -> View:
    """Return the *attachment* as text."""

    r = make_response(attachment.data, 200)
    if attachment.code is not None:
        r.content_type = get_content_type("text/plain", attachment.code)
    else:
        r.content_type = "text/plain"
    return r


def retrieve_attachment_as_native(attachment: Attachment) -> View:
    """Return the *attachment* in its native format."""

    r = make_response(attachment.data, 200)
    if attachment.code is not None:
        r.content_type = get_content_type(attachment.type, attachment.code)
    else:
        r.content_type = attachment.type
    return r


def retrieve_attachment_as_json(attachment: Attachment) -> View:
    """Return the *attachment* as JSON."""

    resource = AttachmentResource.model_validate(
        attachment, from_attributes=True
    )
    return resource.model_dump(mode="json", by_alias=True)


def retrieve_attachment_as_byte(attachment: Attachment) -> View:
    """Return the *attachment* as ``application/octet-stream``."""

    r = make_response(attachment.data, 200)
    r.content_type = "application/octet-stream"
    return r


@server.route("/mail", methods=["GET"])
def select_mail() -> View:
    """Update and return or stream dispatches relevant to the consumer."""

    mime = ("application/json", "application/x-ndjson")
    if request.accept_mimetypes:
        mimetype = request.accept_mimetypes.best_match(mime)
    else:
        mimetype = "application/json"

    if mimetype == "application/json":
        return select_mail_as_json()

    if mimetype == "application/x-ndjson":
        head = {"Content-Type": mimetype}
        return stream_mail(g.consumer.id, request.environ), head

    return "Not Acceptable", 406


def select_mail_as_json() -> View:
    """Update and return dispatches relevant to the consumer as JSON."""

    # This mode isn't incremental so we'll update each dispatch in a single
    # selection with a CTE.
    dispatch_update = aliased(
        Dispatch,
        update(Dispatch)
        .values(last_time=func.now())
        .values(next_time=func.now() + timedelta(hours=1))
        .where(Dispatch.consumer == g.consumer)
        .where(Dispatch.next_time <= func.now())
        .returning(Dispatch)
        .cte(name="dispatch_update"),
    )
    stmt = select(Mail).select_from(dispatch_update).join(dispatch_update.mail)
    stmt = stmt.order_by(dispatch_update.next_time.asc())

    # Load each attachment with a SELECT ... IN ... load. Take a FOR KEY SHARE
    # lock on mail to ensure that the attachment load is consistent.
    stmt = stmt.with_for_update(of=Mail, read=True, key_share=True)
    stmt = stmt.options(selectinload(Mail.attachments))

    result = [load_mail_resource(mail) for mail in database.scalars(stmt)]
    database.commit()

    return jsonify([i.model_dump(mode="json", by_alias=True) for i in result])


def stream_mail(
    consumer_id: int, environment: Optional[WSGIEnvironment] = None
) -> Iterator[str]:
    """Update and stream dispatches relevant to the consumer as JSON."""

    # Used to serialize "self" in MailResource and AttachmentResource
    dump_context: contextlib.AbstractContextManager[Any]
    if environment is not None:
        dump_context = server.request_context(environment)
    else:
        dump_context = contextlib.nullcontext()

    with contextlib.ExitStack() as exit:
        # Open a connection to handle LISTEN/NOTIFY. The reason that this must
        # be on a separate connection is that Psycopg acquires a lock around
        # the entire Connection.notifies() function. Thus, when a notification
        # is received, without another connection, we can't execute SQL.
        connection = exit.enter_context(engine.connect())

        # There's a race condition between SQLAlchemy's "connection fairy" and
        # Psycopg's notification generator:
        #
        #   1. SQLAlchemy issues a rollback when a connection is closed before
        #      returning it to the connection pool.
        #   2. Psycopg's notification generator holds a lock on the underlying
        #      DB-API connection until it's terminated.
        #
        # If the SQLAlchemy connection is closed while iterating through the
        # results of the notification generator (i.e. an exception is raised),
        # then (2) will block the rollback in (1), causing a deadlock. To
        # workaround this, we wrap the generator in a contextlib.closing().
        def notification_stream() -> Iterator[Notify]:
            c: Connection = cast(Connection, connection.connection)
            with contextlib.closing(c.notifies(timeout=60)) as socket:
                yield from socket

        # Execute and commit a LISTEN on the connection. Ensure that we execute
        # and commit an UNLISTEN on exit.
        quoter = connection.dialect.identifier_preparer.quote
        listen_to = quoter(f"consumer_id={consumer_id}")

        @exit.callback
        def unlisten() -> None:
            with connection.begin():
                connection.execute(text(f"UNLISTEN {listen_to}"))

        with connection.begin():
            connection.execute(text(f"LISTEN {listen_to}"))

        database = exit.enter_context(Session(engine, expire_on_commit=True))

        # This SELECT is used to retrieve and lock an active dispatch relevant
        # to the consumer.
        dispatch_select = (
            select(Dispatch)
            .filter_by(consumer_id=consumer_id)
            .where(Dispatch.next_time <= func.now())
            .with_for_update(key_share=True)
            .options(lazyload(Dispatch.mail).joinedload(Mail.attachments))
        )

        while True:
            # In this incremental mode, we'll update a single dispatch at a
            # time so that, if the client disconnects before we've sent the
            # next item, only a single update to dispatch will be erroneous.
            # Note that ORDER BY ... FOR NO KEY UPDATE is able to return rows
            # out of order.
            #
            # We don't have to take a lock on mail because the FOR NO KEY
            # UPDATE on dispatch, in conjunction with the dispatch_to_mail
            # FOREIGN KEY, is an effective lock on mail.
            stmt = dispatch_select.order_by(Dispatch.next_time).limit(1)

            while (dispatch := database.scalar(stmt)) is not None:
                dispatch.last_time = func.now()
                dispatch.next_time = func.now() + timedelta(hours=1)
                resource = load_mail_resource(dispatch.mail)
                database.commit()

                with dump_context:
                    yield f"{resource.model_dump_json(by_alias=True)}\n"
            database.rollback()

            stream_mail_test_hook()

            for item in notification_stream():
                stmt = dispatch_select.filter_by(mail_id=item.payload)

                # If we can't locate a dispatch for the notified mail, then
                # assume that we handled it earlier.
                if (dispatch := database.scalar(stmt)) is None:
                    continue
                database.rollback()

                dispatch.last_time = func.now()
                dispatch.next_time = func.now() + timedelta(hours=1)
                resource = load_mail_resource(dispatch.mail)
                database.commit()

                with dump_context:
                    yield f"{resource.model_dump_json(by_alias=True)}\n"


def stream_mail_test_hook() -> None:
    """Hook to inject test code into the stream_mail() function."""
