from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from db_utils import get_connection, init_db


def iter_pdf_files(root: Path):
    """Yield all PDF files recursively (case-insensitive extension)."""
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() == ".pdf":
            yield path


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest()


def index_pdfs(root: Path) -> None:
    conn = get_connection()
    init_db(conn)

    discovered = 0
    inserted = 0
    skipped_duplicates = 0

    for pdf_path in iter_pdf_files(root):
        discovered += 1
        file_hash = sha256_file(pdf_path)
        file_size_mb = pdf_path.stat().st_size / (1024 * 1024)

        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO pdf_queue(hash, file_path, file_size_mb, status)
            VALUES (?, ?, ?, 'queued');
            """,
            (file_hash, str(pdf_path.resolve()), file_size_mb),
        )

        if cursor.rowcount == 1:
            inserted += 1
            print(f"[ADDED] {pdf_path.name} | {file_size_mb:.2f} MB")
        else:
            skipped_duplicates += 1
            print(f"[SKIP ] duplicate hash for {pdf_path.name}")

    print("\nIndexation terminée")
    print(f"- PDFs détectés : {discovered}")
    print(f"- Nouveaux insérés : {inserted}")
    print(f"- Doublons ignorés : {skipped_duplicates}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Indexer les PDFs dans SQLite")
    parser.add_argument(
        "root_folder",
        type=Path,
        help="Dossier racine à parcourir récursivement",
    )
    args = parser.parse_args()

    if not args.root_folder.exists() or not args.root_folder.is_dir():
        raise SystemExit(f"Dossier invalide: {args.root_folder}")

    index_pdfs(args.root_folder.resolve())
