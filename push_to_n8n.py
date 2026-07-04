from __future__ import annotations

import argparse
from pathlib import Path

import requests
from requests import exceptions as requests_exceptions

from db_utils import get_connection, init_db

WEBHOOK_URL = "http://localhost:5678/webhook/688bc3bc-b06c-49cf-8f41-bd5b7dbcaa3c"
RAM_SAFETY_LIMIT_MB = 500.0


def get_processing_total_mb(conn) -> float:
    row = conn.execute(
        "SELECT COALESCE(SUM(file_size_mb), 0) AS total FROM pdf_queue WHERE status = 'processing';"
    ).fetchone()
    return float(row["total"])


def claim_next_queued(conn):
    """Atomically claim one queued item and switch it to processing."""
    # Only pick items whose next_attempt_at is NULL or <= now
    conn.execute("BEGIN IMMEDIATE;")
    row = conn.execute(
        """
        SELECT hash, file_path, file_size_mb, attempt_count, max_attempts
        FROM pdf_queue
        WHERE status = 'queued' AND (next_attempt_at IS NULL OR next_attempt_at <= datetime('now'))
        ORDER BY created_at ASC
        LIMIT 1;
        """
    ).fetchone()

    if row is None:
        conn.execute("COMMIT;")
        return None

    # Increment attempt_count as we claim it
    cursor = conn.execute(
        """
        UPDATE pdf_queue
        SET status = 'processing', attempt_count = COALESCE(attempt_count,0) + 1
        WHERE hash = ? AND status = 'queued' AND (next_attempt_at IS NULL OR next_attempt_at <= datetime('now'));
        """,
        (row["hash"],),
    )

    if cursor.rowcount != 1:
        conn.execute("ROLLBACK;")
        return None

    conn.execute("COMMIT;")
    return row


def mark_failed(conn, file_hash: str, last_error: str | None = None) -> None:
    if last_error is None:
        conn.execute(
            "UPDATE pdf_queue SET status = 'failed' WHERE hash = ?;",
            (file_hash,),
        )
        return

    conn.execute(
        "UPDATE pdf_queue SET status = 'failed', last_error = ? WHERE hash = ?;",
        (last_error, file_hash),
    )


def schedule_retry(conn, file_hash: str, attempt_count: int, last_error: str) -> None:
    """Schedule a retry using exponential backoff. Mark failed if attempts exceed max_attempts."""
    # Read max_attempts for this item
    row = conn.execute(
        "SELECT max_attempts FROM pdf_queue WHERE hash = ?;", (file_hash,)
    ).fetchone()
    max_attempts = int(row["max_attempts"]) if row and row["max_attempts"] else 5

    if attempt_count >= max_attempts:
        conn.execute(
            "UPDATE pdf_queue SET status = 'failed', last_error = ? WHERE hash = ?;",
            (last_error, file_hash),
        )
        return

    # Exponential backoff in seconds (min 60s, doubles each attempt, cap 3600s)
    backoff_seconds = min(60 * (2 ** (attempt_count - 1)), 3600)
    from datetime import datetime, timedelta

    next_dt = datetime.utcnow() + timedelta(seconds=backoff_seconds)
    next_iso = next_dt.strftime("%Y-%m-%d %H:%M:%S")

    conn.execute(
        "UPDATE pdf_queue SET status = 'queued', last_error = ?, next_attempt_at = ? WHERE hash = ?;",
        (last_error, next_iso, file_hash),
    )


def push_once(webhook_url: str = WEBHOOK_URL) -> None:
    conn = get_connection()
    init_db(conn)

    processing_total_mb = get_processing_total_mb(conn)
    if processing_total_mb > RAM_SAFETY_LIMIT_MB:
        print(
            f"Safety stop: processing={processing_total_mb:.2f} MB > {RAM_SAFETY_LIMIT_MB:.2f} MB."
        )
        return

    item = claim_next_queued(conn)
    if item is None:
        print("Aucun fichier queued à envoyer.")
        return

    pdf_path = Path(item["file_path"])
    file_hash = item["hash"]
    attempt_count = int(item["attempt_count"] or 0)

    if not pdf_path.exists() or not pdf_path.is_file():
        print(f"Fichier introuvable: {pdf_path}")
        mark_failed(conn, file_hash)
        return

    try:
        with pdf_path.open("rb") as f:
            files = {
                "file": (pdf_path.name, f, "application/pdf"),
            }
            data = {
                "hash": file_hash,
                "path": str(pdf_path),
            }
            response = requests.post(webhook_url, files=files, data=data, timeout=60)
        print(
            f"Envoyé: {pdf_path.name} [{file_hash[:10]}...] (HTTP {response.status_code})"
        )
        # Any HTTP response means n8n received the payload.
        # The final success/failure is handled later by the callback API.
        conn.execute(
            "UPDATE pdf_queue SET last_error = NULL, next_attempt_at = NULL WHERE hash = ?;",
            (file_hash,),
        )
    except (requests_exceptions.Timeout, requests_exceptions.ConnectionError) as exc:
        # Retry only when n8n did not answer immediately.
        try:
            schedule_retry(conn, file_hash, attempt_count, str(exc))
            print(f"Échec envoi -> reprogrammée pour retry pour {pdf_path.name}: {exc}")
        except Exception as e:
            # Fallback to final failure
            mark_failed(conn, file_hash, str(e))
            print(f"Échec envoi -> status=failed pour {pdf_path.name}: {e}")
    except requests_exceptions.RequestException as exc:
        # Any other request-level failure is still a transport problem, so retry.
        try:
            schedule_retry(conn, file_hash, attempt_count, str(exc))
            print(f"Échec transport -> reprogrammée pour retry pour {pdf_path.name}: {exc}")
        except Exception as e:
            mark_failed(conn, file_hash, str(e))
            print(f"Échec transport -> status=failed pour {pdf_path.name}: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Push des PDFs vers n8n")
    parser.add_argument(
        "--webhook-url",
        type=str,
        default=WEBHOOK_URL,
        help="Webhook n8n cible",
    )
    args = parser.parse_args()

    push_once(args.webhook_url)
