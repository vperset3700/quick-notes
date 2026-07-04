from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from db_utils import get_connection, init_db

app = FastAPI(title="Auto Ficheur Callback API", version="1.0.0")


class CallbackPayload(BaseModel):
    hash: str = Field(..., min_length=8)
    status: Literal["completed", "failed"]
    error: str | None = None


@app.on_event("startup")
def startup() -> None:
    conn = get_connection()
    init_db(conn)
    conn.close()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/callback")
def callback(payload: CallbackPayload) -> dict[str, str]:
    conn = get_connection()
    init_db(conn)

    row = conn.execute(
        "SELECT hash, status FROM pdf_queue WHERE hash = ?;",
        (payload.hash,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Unknown hash")

    if payload.status == "completed":
        conn.execute(
            """
            UPDATE pdf_queue
            SET status = 'completed', last_error = NULL, next_attempt_at = NULL
            WHERE hash = ?;
            """,
            (payload.hash,),
        )
    else:
        conn.execute(
            """
            UPDATE pdf_queue
            SET status = 'failed', last_error = ?, next_attempt_at = NULL
            WHERE hash = ?;
            """,
            (payload.error or "Unknown error", payload.hash),
        )

    conn.close()
    return {"ok": "true", "hash": payload.hash, "status": payload.status}
