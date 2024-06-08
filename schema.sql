DROP TABLE IF EXISTS mail CASCADE;
DROP TABLE IF EXISTS attachment CASCADE;
DROP TABLE IF EXISTS consumer CASCADE;
DROP TABLE IF EXISTS dispatch CASCADE;
DROP FUNCTION IF EXISTS dispatch_notify() CASCADE;

CREATE TABLE mail (
  -- The Message-ID Identification Field, with the enclosing angle brackets, "<"
  -- and ">", removed
  id TEXT PRIMARY KEY,

  -- The Origination Date Field
  date TIMESTAMPTZ NOT NULL,

  -- The text extracted from the concatenation of each textual part of the email
  -- message
  text TEXT NOT NULL,

  -- The literal email message as received
  data BYTEA NOT NULL
);

CREATE TABLE attachment (
  -- Reference to the mail that the attachment belongs to
  mail_id TEXT CONSTRAINT attachment_to_mail REFERENCES mail(id)
    ON UPDATE CASCADE ON DELETE CASCADE,

  -- Sequence number of the attachment within the mail. This is greater than or
  -- equal to zero and indexes to the part that carried the attachment within
  -- the email message. Sequence numbers don't need to be contiguous, but they
  -- are ordered in accordance with their sequence number.
  number INTEGER CONSTRAINT number CHECK (number >= 0),

  -- The natural primary key of an attachment is the combination of the mail
  -- that it belongs to and its sequence number within that mail
  PRIMARY KEY (mail_id, number),

  -- The name of the attachment
  name TEXT,

  -- The MIME type of the attachment
  type TEXT NOT NULL,

  -- An optional charset to indicate the encoding of a textual attachment
  code TEXT,

  -- The literal attachment as received within the email message
  data BYTEA NOT NULL
);

CREATE TABLE consumer (
  -- Synthetic identifier
  id INTEGER PRIMARY KEY GENERATED BY DEFAULT AS IDENTITY,

  -- Name of the consumer
  name TEXT NOT NULL
);

CREATE TABLE dispatch (
  -- Reference to the consumer that the dispatch should be sent to. If the
  -- consumer is deleted, then each dispatch to it should be deleted as well.
  consumer_id INTEGER NOT NULL
    CONSTRAINT dispatch_to_consumer REFERENCES consumer(id)
    ON DELETE CASCADE,

  -- Reference to the mail that should be sent in the dispatch
  mail_id TEXT NOT NULL
    CONSTRAINT dispatch_to_mail REFERENCES mail(id),

  -- The natural primary key of a dispatch is the combination of its consumer
  -- and mail. A mail shouldn't be dispatched more than once to a consumer.
  PRIMARY KEY (consumer_id, mail_id),

  -- The last time that we attempted to send the dispatch. This is ``NULL`` if
  -- no attempts have been made.
  last_time TIMESTAMPTZ,

  -- The next time that we should attempt to send the dispatch. This can't
  -- predate `last_time` and it can't be ``NULL`` -- a dispatch that shouldn't
  -- be sent should be deleted.
  next_time TIMESTAMPTZ NOT NULL DEFAULT NOW()
    CONSTRAINT next_time CHECK (next_time > last_time),

  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE FUNCTION dispatch_notify() RETURNS TRIGGER AS $$
BEGIN
  PERFORM pg_notify('consumer_id=' || NEW.consumer_id, NEW.mail_id);
  RETURN NEW;
END; $$ LANGUAGE plpgsql;

CREATE TRIGGER dispatch_notify AFTER INSERT ON dispatch
FOR EACH ROW EXECUTE PROCEDURE dispatch_notify();