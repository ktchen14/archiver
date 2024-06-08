import json

import jwt
from sqlalchemy import func

import archiver.wsgi
from archiver.database import Dispatch, Mail
from archiver.loader import load_mail_resource


def test_authentication(server, client, consumer):
    server.add_url_rule("/", view_func=lambda: "", methods=["GET"])

    client.authorization = None

    assert client.get("/none").status_code == 404

    data = {"sub": f"consumer_id={consumer.id}"}
    secret = server.secret_key

    # No authorization header
    r = client.get("/")
    assert r.status_code == 401
    assert r.www_authenticate.realm == r.request.host
    assert r.www_authenticate.error is None

    # Incorrect scheme
    r = client.get("/", headers={"Authorization": "Basic dGVzdC1zZWNyZXQ="})
    assert r.status_code == 401
    assert r.www_authenticate.realm == r.request.host
    assert r.www_authenticate.error is None

    # No bearer token
    r = client.get("/", headers={"Authorization": "Bearer"})
    assert r.status_code == 401
    assert r.www_authenticate.error == "invalid_request"

    # Incorrect secret
    code = jwt.encode(data, "none", algorithm="HS256")
    r = client.get("/", headers={"Authorization": f"Bearer {code}"})
    assert r.status_code == 401
    assert r.www_authenticate.error == "invalid_token"

    # Incorrect algorithm
    code = jwt.encode(data, secret, algorithm="HS384")
    r = client.get("/", headers={"Authorization": f"Bearer {code}"})
    assert r.status_code == 401
    assert r.www_authenticate.error == "invalid_token"

    # Missing sub
    code = jwt.encode({"iss": "test"}, secret, algorithm="HS256")
    r = client.get("/", headers={"Authorization": f"Bearer {code}"})
    assert r.status_code == 401
    assert r.www_authenticate.error == "invalid_token"

    # Incorrectly formatted sub
    code = jwt.encode({"sub": "id=1"}, secret, algorithm="HS256")
    r = client.get("/", headers={"Authorization": f"Bearer {code}"})
    assert r.status_code == 401
    assert r.www_authenticate.error == "invalid_token"

    # No such consumer
    data = {"sub": "consumer_id=0"}
    code = jwt.encode(data, secret, algorithm="HS256")
    r = client.get("/", headers={"Authorization": f"Bearer {code}"})
    assert r.status_code == 403


def test_retrieve_mail_absent(client):
    assert client.get("/mail/none").status_code == 404


def test_retrieve_mail_accept_none(client, session, mail, dispatch):
    r = client.get(f"/mail/{mail.id}", headers={"Accept": "none/plain"})
    assert r.status_code == 406

    session.delete(dispatch)
    session.commit()
    r = client.get(f"/mail/{mail.id}", headers={"Accept": "none/plain"})
    assert r.status_code == 404


def test_retrieve_mail_accept_text(client, session, mail, dispatch):
    r = client.get(f"/mail/{mail.id}", headers={"Accept": "text/plain"})
    assert r.status_code == 200
    assert r.content_type == "text/plain; charset=utf-8"
    assert r.data == mail.data

    session.delete(dispatch)
    session.commit()
    r = client.get(f"/mail/{mail.id}", headers={"Accept": "text/plain"})
    assert r.status_code == 404


def test_retrieve_mail_accept_message(client, session, mail, dispatch):
    r = client.get(f"/mail/{mail.id}", headers={"Accept": "message/rfc822"})
    assert r.status_code == 200
    assert r.content_type == "message/rfc822"
    assert r.data == mail.data

    session.delete(dispatch)
    session.commit()
    r = client.get(f"/mail/{mail.id}", headers={"Accept": "message/rfc822"})
    assert r.status_code == 404


def test_retrieve_mail_accept_json(client, session, mail, dispatch):
    r = client.get(f"/mail/{mail.id}")
    assert r.status_code == 200
    assert r.content_type == "application/json"
    implicit_json = r.json

    r = client.get(f"/mail/{mail.id}", headers={"Accept": "application/json"})
    assert r.status_code == 200
    assert r.content_type == "application/json"
    assert r.json == {
        "self": f"/mail/{mail.id}",
        "id": mail.id,
        "date": mail.date.isoformat(),
        "text": mail.text,
        "from": [
            {"name": "Sample User 1", "addr_spec": "sample-user-1@kaimel.io"}
        ],
        "sender": None,
        "reply-to": None,
        "to": [
            {
                "name": "pgsql-hackers",
                "addr_spec": "pgsql-hackers@postgresql.org",
            }
        ],
        "cc": [
            {"name": "Sample User 5", "addr_spec": "sample-user-5@kaimel.io"},
            {"name": "Sample User 6", "addr_spec": "sample-user-6@kaimel.io"},
        ],
        "bcc": None,
        "subject": "Sample Message",
        "in-reply-to": ["1bd5f0e9-690d-47a2-bfca-d4c1dc78daf8@kaimel.io"],
        "references": [
            "1bd5f0e9-690d-47a2-bfca-d4c1dc78daf8@kaimel.io",
            "3a3b8895-fd56-4d0a-95e4-82efaaeb0fb2@kaimel.io",
            "64431af8-9984-4eaf-a7fd-fcfd03ea114b@kaimel.io",
        ],
        "attachments": [
            {
                "self": f"/mail/{mail.id}/attachment/3",
                "name": "attachment.html",
                "number": 3,
                "type": "text/html",
                "code": "utf-8",
            },
            {
                "self": f"/mail/{mail.id}/attachment/4",
                "name": "test-attachment.txt",
                "number": 4,
                "type": "text/plain",
                "code": "utf-8",
            },
        ],
    }
    assert implicit_json == r.json

    session.delete(dispatch)
    session.commit()
    r = client.get(f"/mail/{mail.id}", headers={"Accept": "application/json"})
    assert r.status_code == 404


def test_delete_mail(client, session, dispatch):
    assert client.delete(f"/mail/{dispatch.mail.id}").status_code == 200
    assert client.delete(f"/mail/{dispatch.mail.id}").status_code == 404


def test_retrieve_attachment_absent(client, mail):
    assert client.get("/mail/no-mail-id/attachment/1").status_code == 404
    assert client.get(f"/mail/{mail.id}/attachment/5").status_code == 404


def test_retrieve_attachment_accept_none(client, session, attachment, dispatch):
    target = f"/mail/{attachment.mail.id}/attachment/{attachment.number}"

    r = client.get(target, headers={"Accept": "none/plain"})
    assert r.status_code == 406

    session.delete(dispatch)
    session.commit()
    r = client.get(target, headers={"Accept": "none/plain"})
    assert r.status_code == 404


def test_retrieve_attachment_accept_native(
    client, session, attachment, dispatch
):
    target = f"/mail/{attachment.mail.id}/attachment/{attachment.number}"

    r = client.get(target, headers={"Accept": attachment.type})
    assert r.status_code == 200
    assert r.mimetype == attachment.type
    assert r.mimetype_params == {"charset": attachment.code}
    assert r.data == attachment.data

    session.delete(dispatch)
    session.commit()
    r = client.get(target, headers={"Accept": attachment.type})
    assert r.status_code == 404


def test_retrieve_attachment_accept_text(client, session, attachment, dispatch):
    target = f"/mail/{attachment.mail.id}/attachment/{attachment.number}"

    r = client.get(target, headers={"Accept": "text/plain"})
    assert r.status_code == 200
    assert r.mimetype == "text/plain"
    assert r.mimetype_params == {"charset": attachment.code}
    assert r.data == attachment.data

    session.delete(dispatch)
    session.commit()
    r = client.get(target, headers={"Accept": "text/plain"})
    assert r.status_code == 404


def test_retrieve_attachment_accept_json(client, session, attachment, dispatch):
    target = f"/mail/{attachment.mail.id}/attachment/{attachment.number}"

    r = client.get(target)
    assert r.status_code == 200
    assert r.content_type == "application/json"
    implicit_json = r.json

    r = client.get(target, headers={"Accept": "application/json"})
    assert r.status_code == 200
    assert r.content_type == "application/json"
    assert r.json == {
        "self": target,
        "name": "test-attachment.txt",
        "number": 4,
        "type": "text/plain",
        "code": "utf-8",
    }
    assert implicit_json == r.json

    session.delete(dispatch)
    session.commit()
    r = client.get(target, headers={"Accept": "application/json"})
    assert r.status_code == 404


def test_retrieve_attachment_accept_byte(client, session, attachment, dispatch):
    target = f"/mail/{attachment.mail.id}/attachment/{attachment.number}"

    r = client.get(target, headers={"Accept": "application/octet-stream"})
    assert r.status_code == 200
    assert r.content_type == "application/octet-stream"
    assert r.data == attachment.data

    session.delete(dispatch)
    session.commit()
    r = client.get(target, headers={"Accept": "application/octet-stream"})
    assert r.status_code == 404


def test_select_mail_accept_none(client, session, mail, dispatch):
    r = client.get("/mail", headers={"Accept": "none/plain"})
    assert r.status_code == 406

    session.delete(dispatch)
    session.commit()
    r = client.get("/mail", headers={"Accept": "none/plain"})
    assert r.status_code == 406


def test_select_mail_accept_json(server, client, session, dispatch):
    ignore = Mail(id="test-select-x", date=func.now(), text="", data=b"")
    session.add(ignore)
    session.commit()

    r = client.get("/mail", headers={"Accept": "application/json"})
    assert r.status_code == 200
    assert r.content_type == "application/json"

    resource = load_mail_resource(dispatch.mail)
    with server.test_request_context("/mail"):
        dump = resource.model_dump(mode="json", by_alias=True)
    assert r.json == [dump]

    r = client.get("/mail", headers={"Accept": "application/json"})
    assert r.status_code == 200
    assert r.content_type == "application/json"
    assert r.json == []


def test_select_mail_accept_stream(server, client, session, consumer):
    # Create, add, and commit three mails, of which two are relevant

    mail_1 = Mail(id="test-stream-1", date=func.now(), text="", data=b"")
    dispatch_1 = Dispatch(consumer=consumer, mail=mail_1)

    mail_2 = Mail(id="test-stream-2", date=func.now(), text="", data=b"")
    dispatch_2 = Dispatch(consumer=consumer, mail=mail_2)

    ignore = Mail(id="test-stream-x", date=func.now(), text="", data=b"")

    session.add_all((mail_1, dispatch_1, mail_2, dispatch_2, ignore))
    session.commit()

    # Issue the GET request and open an iterator
    r = client.get("/mail", headers={"Accept": "application/x-ndjson"})
    assert r.status_code == 200
    assert r.content_type == "application/x-ndjson"
    iterator = r.iter_encoded()

    # Ensure that the next result is the expected mail (mail_1)
    with server.test_request_context("/mail"):
        dump = load_mail_resource(mail_1).model_dump(mode="json", by_alias=True)
    assert json.loads(next(iterator)) == dump

    # Ensure that the next result is the expected mail (mail_2)
    with server.test_request_context("/mail"):
        dump = load_mail_resource(mail_2).model_dump(mode="json", by_alias=True)
    assert json.loads(next(iterator)) == dump

    # Define a hook function to create, add, and commit mail_3
    def create_mail_dispatch_3() -> None:
        mail = Mail(id="test-stream-3", date=func.now(), text="", data=b"")
        dispatch = Dispatch(consumer=consumer, mail=mail)
        session.add(dispatch)
        session.commit()

    archiver.wsgi.stream_mail_test_hook = create_mail_dispatch_3

    # Load the next result and, in the process, invoke the hook function
    item = json.loads(next(iterator))

    mail_3 = session.get_one(Mail, "test-stream-3")
    with server.test_request_context("/mail"):
        dump = load_mail_resource(mail_3).model_dump(mode="json", by_alias=True)
    assert item == dump
