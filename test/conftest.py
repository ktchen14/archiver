import logging
import os
import uuid
from collections.abc import Iterator

import jwt
import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from archiver.database import Attachment, Consumer, Dispatch, Mail, Record
from archiver.loader import load_mail_record
from archiver.wsgi import server as wsgi_server

engine = create_engine("postgresql+psycopg:///")
logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)

ROOT = os.path.dirname(__file__)


class AuthorizationClient(FlaskClient):
    def __init__(self, *args, authorization=None, **kwargs):
        self.authorization = authorization
        super().__init__(*args, **kwargs)

    def open(self, *args, **kwargs):
        if self.authorization is not None:
            headers = kwargs.get("headers", {})
            headers.setdefault("Authorization", self.authorization)
            kwargs["headers"] = headers
        return super().open(*args, **kwargs)


@pytest.fixture(scope="session", autouse=True)
def truncate() -> None:
    with Session(engine) as session:
        quoter = session.get_bind().dialect.identifier_preparer.quote

        # Execute TRUNCATE ONLY ... RESTART IDENTITY against each mapped table
        # in the Record class's metadata
        target = set()
        for table in Record.metadata.tables.values():
            if table.schema is not None:
                target.add(f"{quoter(table.schema)}.{quoter(table.name)}")
            else:
                target.add(quoter(table.name))
        target_text = ", ".join(name for name in target)
        stmt = text(f"TRUNCATE ONLY {target_text} RESTART IDENTITY CASCADE")

        session.execute(stmt)
        session.commit()


@pytest.fixture
def session() -> Iterator[Session]:
    with Session(engine, expire_on_commit=False) as session:
        yield session


@pytest.fixture
def mail(session: Session) -> Mail:
    mail_id = uuid.uuid4().hex.encode("ascii")
    with open(os.path.join(ROOT, "sample.eml"), "rb") as f:
        data = f.read()
    data = data.replace(b"xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx", mail_id)
    session.add(mail := load_mail_record(data))
    session.commit()
    return mail


@pytest.fixture
def attachment(session: Session, mail: Mail) -> Attachment:
    return mail.attachments[1]


@pytest.fixture
def consumer(session: Session) -> Consumer:
    session.add(consumer := Consumer(name="test-consumer"))
    session.commit()
    return consumer


@pytest.fixture
def dispatch(session: Session, mail: Mail, consumer: Consumer) -> Dispatch:
    session.add(dispatch := Dispatch(mail=mail, consumer=consumer))
    session.commit()
    return dispatch


@pytest.fixture
def server() -> Flask:
    wsgi_server.secret_key = "test-secret"
    wsgi_server.test_client_class = AuthorizationClient
    wsgi_server.testing = True
    return wsgi_server


@pytest.fixture
def client(server: Flask, consumer: Consumer) -> FlaskClient:
    data = {"sub": f"consumer_id={consumer.id}"}
    code = jwt.encode(data, server.secret_key, algorithm="HS256")
    return server.test_client(authorization=f"Bearer {code}")
