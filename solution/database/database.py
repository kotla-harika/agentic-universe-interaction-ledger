from solution.processing.normalization import normalize_phone
import sqlite3
import os
import json
import hmac
import hashlib

from pathlib import Path
from cryptography.fernet import Fernet


# Database location
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "agentic_universe.db"


def get_connection():
    """Connect to SQLite database."""

    connection = sqlite3.connect(DB_PATH)

    return connection


def get_encryption():
    """Load encryption key from environment."""

    key = os.environ.get("AGENTIC_FERNET_KEY")

    if not key:
        raise RuntimeError("Encryption key not found")

    return Fernet(key.encode())


def get_hash_key():
    """Load secure hashing key."""

    key = os.environ.get("AGENTIC_HASH_KEY")

    if not key:
        raise RuntimeError("Hash key not found")

    return bytes.fromhex(key)


def encrypt_value(value):
    """Encrypt sensitive customer information."""

    if value is None:
        return None

    encrypted = get_encryption().encrypt(
        str(value).encode("utf-8")
    )

    return encrypted


def decrypt_value(value):
    """Decrypt customer information."""

    if value is None:
        return None

    decrypted = get_encryption().decrypt(value)

    return decrypted.decode("utf-8")


def hash_phone(phone):
    """Create a secure hash for phone matching."""

    if not phone:
        return None

    return hmac.new(
        get_hash_key(),
        phone.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()


def create_tables():
    """Create the customer database table."""

    connection = get_connection()

    connection.execute("""
        CREATE TABLE IF NOT EXISTS leads (

            lead_id INTEGER PRIMARY KEY AUTOINCREMENT,

            workflow_id TEXT NOT NULL,

            phone_hash TEXT NOT NULL,

            customer_name_enc BLOB NOT NULL,

            phone_enc BLOB NOT NULL,

            batch_id TEXT NOT NULL,

            other_data TEXT NOT NULL DEFAULT '{}',

            created_at TEXT DEFAULT CURRENT_TIMESTAMP,

            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,

            UNIQUE(workflow_id, phone_hash)
        )
    """)

    # Create append-only interaction event table
    connection.execute("""
        CREATE TABLE IF NOT EXISTS interaction_events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            workflow_id TEXT NOT NULL,
            call_id TEXT,
            occurred_at TEXT NOT NULL,
            phone_hash TEXT,
            phone_enc BLOB,
            payload_json TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Link events to customer leads
    connection.execute("""
        CREATE TABLE IF NOT EXISTS event_lead_links (
            event_id TEXT PRIMARY KEY,
            lead_id INTEGER,
            link_status TEXT NOT NULL,
            FOREIGN KEY (event_id)
                REFERENCES interaction_events(event_id),
            FOREIGN KEY (lead_id)
                REFERENCES leads(lead_id)
        )
    """)

    # Prevent editing original events
    connection.execute("""
        CREATE TRIGGER IF NOT EXISTS prevent_event_update
        BEFORE UPDATE ON interaction_events
        BEGIN
            SELECT RAISE(ABORT, 'Events are append-only');
        END
    """)

    # Prevent deleting original events
    connection.execute("""
        CREATE TRIGGER IF NOT EXISTS prevent_event_delete
        BEFORE DELETE ON interaction_events
        BEGIN
            SELECT RAISE(ABORT, 'Events are append-only');
        END
    """)

    connection.commit()
    connection.close()

    print("CUSTOMER TABLE CREATED SUCCESSFULLY")


import json


def save_leads(lead_store):
    """
    Save customer records securely in SQLite.
    Encrypt PII and use a keyed hash for phone matching.
    """

    connection = get_connection()

    try:
        for lead in lead_store.values():

            workflow_id = lead["workflow_id"]
            phone = lead["phone"]
            customer_name = lead["customer_name"]

            phone_hash = hash_phone(phone)

            encrypted_name = encrypt_value(customer_name)
            encrypted_phone = encrypt_value(phone)

            # Keep PII out of the JSON data
            other_data = {
                key: value
                for key, value in lead.items()
                if key not in (
                    "customer_name",
                    "phone",
                    "workflow_id",
                    "batch_id"
                )
            }

            connection.execute("""
                INSERT INTO leads (
                    workflow_id,
                    phone_hash,
                    customer_name_enc,
                    phone_enc,
                    batch_id,
                    other_data
                )
                VALUES (?, ?, ?, ?, ?, ?)

                ON CONFLICT(workflow_id, phone_hash)
                DO UPDATE SET
                    customer_name_enc = excluded.customer_name_enc,
                    phone_enc = excluded.phone_enc,
                    other_data = excluded.other_data,
                    updated_at = CURRENT_TIMESTAMP
            """, (
                workflow_id,
                phone_hash,
                encrypted_name,
                encrypted_phone,
                lead["batch_id"],
                json.dumps(other_data)
            ))

        connection.commit()

        print("CUSTOMERS SAVED SUCCESSFULLY")

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()

def save_event(event):
    """
    Insert one event into the append-only event ledger.
    Duplicate event IDs are ignored.
    """
    connection = get_connection()

    try:
        phone = event.get("phone")
        phone_hash = hash_phone(phone) if phone else None
        encrypted_phone = encrypt_value(phone) if phone else None

        cursor = connection.execute("""
            INSERT OR IGNORE INTO interaction_events (
                event_id,
                event_type,
                workflow_id,
                call_id,
                occurred_at,
                phone_hash,
                phone_enc,
                payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            event["event_id"],
            event["event_type"],
            event["workflow_id"],
            event.get("call_id"),
            event["occurred_at"],
            phone_hash,
            encrypted_phone,
            json.dumps(event.get("payload", {}))
        ))

        connection.commit()
        return cursor.rowcount == 1

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()

def link_event_to_lead(event):
    """
    Link an event to a lead using phone number.
    Disposition overrides are linked using call_id.
    """

    connection = get_connection()

    try:
        lead = None

        # First, try matching by normalized phone number
        phone = event.get("phone")
        normalized_phone = normalize_phone(phone) if phone else None

        if normalized_phone:
            phone_hash = hash_phone(normalized_phone)

            lead = connection.execute(
                """
                SELECT lead_id
                FROM leads
                WHERE workflow_id = ? AND phone_hash = ?
                """,
                (event["workflow_id"], phone_hash)
            ).fetchone()

        # If there is no phone, try matching by call_id
        if not lead and event.get("call_id"):
            lead = connection.execute(
                """
                SELECT l.lead_id
                FROM interaction_events e
                JOIN event_lead_links el
                    ON e.event_id = el.event_id
                JOIN leads l
                    ON el.lead_id = l.lead_id
                WHERE e.workflow_id = ?
                  AND e.call_id = ?
                  AND el.link_status = 'linked'
                LIMIT 1
                """,
                (event["workflow_id"], event["call_id"])
            ).fetchone()

        if lead:
            lead_id = lead[0]
            link_status = "linked"
        else:
            lead_id = None
            link_status = "orphan"

        cursor = connection.execute(
            """
            INSERT INTO event_lead_links
                (event_id, lead_id, link_status)
            VALUES (?, ?, ?)
            ON CONFLICT(event_id)
            DO UPDATE SET
                lead_id = excluded.lead_id,
                link_status = excluded.link_status
            """,
            (event["event_id"], lead_id, link_status)
        )

        connection.commit()
        return link_status

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()