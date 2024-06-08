from sqlalchemy import func, select

from archiver.database import Attachment, Consumer, Dispatch, Mail


def test_mail(session):
    mail = Mail(id="test-mail", date=func.now(), text="", data=b"")
    session.add(mail)
    session.commit()


def test_attachment(session, mail):
    attachment = Attachment(
        mail=mail, number=10, type="text/plain", data=b"asdf"
    )
    session.add(attachment)
    session.commit()


def test_consumer(session):
    consumer = Consumer(name="test-consumer")
    session.add(consumer)
    session.commit()


def test_dispatch(session, consumer, mail):
    dispatch = Dispatch(consumer=consumer, mail=mail)
    session.add(dispatch)
    now = session.scalar(select(func.now()))
    session.commit()

    assert now == dispatch.next_time
    assert now == dispatch.created_at
    assert dispatch.last_time is None
