import os.path
from datetime import datetime, timedelta, timezone
from textwrap import dedent

from archiver.loader import load_mail_record, load_mail_resource

ROOT = os.path.dirname(__file__)
DATE = datetime(2024, 6, 10, 8, 0, 0, tzinfo=timezone(timedelta(hours=-4)))


def test_load_1(session):
    with open(os.path.join(ROOT, "1.eml"), "rb") as f:
        data = f.read()
    session.add(record := load_mail_record(data))
    session.commit()

    assert record.id == "12b13e25-5ee2-471c-b78c-e3178668864d@kaimel.io"
    assert record.date == DATE
    assert record.text == "This is some *sample* text"
    assert record.data == data
    assert len(record.attachments) == 2

    attachment = record.attachments[0]
    assert attachment.number == 3
    assert attachment.name == "attachment.html"
    assert attachment.type == "text/html"
    assert attachment.code == "utf-8"
    assert attachment.data.strip() == """
        <div dir="ltr">This is some <b>sample</b> text<br></div>
    """.strip().encode("utf-8")  # fmt: skip

    attachment = record.attachments[1]
    assert attachment.number == 4
    assert attachment.name == "test-attachment.txt"
    assert attachment.type == "text/plain"
    assert attachment.code == "utf-8"
    assert attachment.data.strip() == """
        This is a test attachment
    """.strip().encode("utf-8")  # fmt: skip

    resource = load_mail_resource(record)
    assert resource.id == record.id
    assert resource.date == record.date
    assert resource.text == record.text

    assert resource.from_ == [
        "Sample User 1 <sample-user-1@kaimel.io>",
        "Sample User 2 <sample-user-2@kaimel.io>",
    ]
    assert resource.sender == "Sample User 0 <sample-user-0@kaimel.io>"
    assert resource.reply_to == [
        "pgsql-hackers <pgsql-hackers@postgresql.org>",
        "Sample User 3 <sample-user-3@kaimel.io>",
    ]
    assert resource.to == [
        "pgsql-hackers <pgsql-hackers@postgresql.org>",
        "Sample User 4 <sample-user-4@kaimel.io>",
    ]
    assert resource.cc == [
        "Sample User 5 <sample-user-5@kaimel.io>",
        "Sample User 6 <sample-user-6@kaimel.io>",
    ]
    assert resource.bcc == [
        "Sample User 7 <sample-user-7@kaimel.io>",
        "Sample User 8 <sample-user-8@kaimel.io>",
    ]
    assert resource.in_reply_to == [
        "1bd5f0e9-690d-47a2-bfca-d4c1dc78daf8@kaimel.io",
        "b5634a34-5770-476b-bcdf-5d2551b1a94d@kaimel.io",
    ]
    assert resource.references == [
        "1bd5f0e9-690d-47a2-bfca-d4c1dc78daf8@kaimel.io",
        "b5634a34-5770-476b-bcdf-5d2551b1a94d@kaimel.io",
        "3a3b8895-fd56-4d0a-95e4-82efaaeb0fb2@kaimel.io",
        "64431af8-9984-4eaf-a7fd-fcfd03ea114b@kaimel.io",
    ]
    assert resource.subject == "Test Message"

    for a, b in zip(resource.attachments, record.attachments, strict=True):
        assert a.number == b.number
        assert a.name == b.name
        assert a.type == b.type


def test_load_2(session):
    with open(os.path.join(ROOT, "2.eml"), "rb") as f:
        data = f.read()
    session.add(record := load_mail_record(data))
    session.commit()

    assert record.id == "30da3ae3-f1f1-44a4-966a-073eb75e1b70@kaimel.io"
    assert record.date == DATE
    assert record.text == ""
    assert record.data == data
    assert len(record.attachments) == 1

    attachment = record.attachments[0]
    assert attachment.number == 0
    assert attachment.name == "attachment.html"
    assert attachment.type == "text/html"
    assert attachment.code == "utf-8"
    assert attachment.data.strip() == """
        <div dir="ltr">This is some <b>sample</b> text<br></div>
    """.strip().encode("utf-8")  # fmt: skip

    resource = load_mail_resource(record)
    assert resource.id == record.id
    assert resource.date == record.date
    assert resource.text == record.text

    assert resource.from_ == ["Sample User 1 <sample-user-1@kaimel.io>"]
    assert resource.sender is None
    assert resource.reply_to is None
    assert resource.to is None
    assert resource.cc is None
    assert resource.bcc is None
    assert resource.in_reply_to is None
    assert resource.references is None
    assert resource.subject is None

    for a, b in zip(resource.attachments, record.attachments, strict=True):
        assert a.number == b.number
        assert a.name == b.name
        assert a.type == b.type


def test_load_3(session):
    with open(os.path.join(ROOT, "3.eml"), "rb") as f:
        data = f.read()
    session.add(record := load_mail_record(data))
    session.commit()

    assert record.id == "aa9451e1-e155-4f01-b765-db7a3b99f153@kaimel.io"
    assert record.date == DATE
    assert record.text == "This is some *sample* text"
    assert record.data == data

    resource = load_mail_resource(record)
    assert resource.id == record.id
    assert resource.date == record.date
    assert resource.text == record.text

    assert resource.from_ == ["Sample User 1 <sample-user-1@kaimel.io>"]
    assert resource.sender is None
    assert resource.reply_to is None
    assert resource.to is None
    assert resource.cc is None
    assert resource.bcc is None
    assert resource.in_reply_to is None
    assert resource.references is None
    assert resource.subject is None
    assert resource.attachments == []


def test_load_4(session):
    with open(os.path.join(ROOT, "4.eml"), "rb") as f:
        data = f.read()
    session.add(record := load_mail_record(data))
    session.commit()

    assert record.id == "39669c1f-692f-467c-a0cd-f51a13e1fe12@kaimel.io"
    assert record.date == DATE
    assert record.text == "This is some *sample* text"
    assert record.data == data
    assert len(record.attachments) == 1

    attachment = record.attachments[0]
    assert attachment.number == 2
    assert attachment.name == "sample.diff"
    assert attachment.type == "text/x-diff"
    assert attachment.code == "utf-8"
    assert attachment.data.strip() == dedent("""
        commit 0000000000000000000000000000000000000000
        Author: Sample User 1 <sample-user-1@kaimel.io>
        Date:   Mon Jun 10 08:00:00 2024 -0400

            Sample change

        diff --git a/test/sample b/test/sample
        index 7898192..6178079 100644
        --- a/test/sample
        +++ b/test/sample
        @@ -1 +1 @@
        -a
        +b
    """).strip().encode("utf-8")  # fmt: skip

    resource = load_mail_resource(record)
    assert resource.id == record.id
    assert resource.date == record.date
    assert resource.text == record.text

    assert resource.from_ == ["Sample User 1 <sample-user-1@kaimel.io>"]
    assert resource.sender is None
    assert resource.reply_to is None
    assert resource.to is None
    assert resource.cc is None
    assert resource.bcc is None
    assert resource.in_reply_to is None
    assert resource.references is None
    assert resource.subject is None

    for a, b in zip(resource.attachments, record.attachments, strict=True):
        assert a.number == b.number
        assert a.name == b.name
        assert a.type == b.type
