# Quick Notes

Quick Notes turns a folder of PDFs into structured study sheets and pushes the result into n8n workflows that publish the content to Notion.

## What is in the repo

- `index_pdfs.py` converts PDFs to text and estimates token usage.
- `push_to_n8n.py` sends queued PDFs to the n8n webhook.
- `run_push.sh` keeps the push loop running.
- `callback_api/` contains the FastAPI callback used by n8n when a document is processed.
- `docker-compose.yml` starts the n8n stack, the callback API, and a SQLite viewer.
- `Dockerfile.push` builds the small container that runs the push loop.
- `n8n_exports/` contains reusable workflow exports.
- `n8n_custom_nodes/package.json` declares the custom n8n node needed by the workflow.
- `systemd/push_to_n8n.service` is a host install template that starts the compose stack once Docker is ready.

## Prerequisites

- Docker and Docker Compose.
- Python 3.11+ with `venv`.
- A Notion integration token with access to the target pages or databases.
- A Google Gemini API key for the `Google Gemini(PaLM) Api account` credential used in n8n.
- Optional but recommended: your own n8n encryption key if you want to keep the same local instance across restarts.

The imported workflows expect these n8n credentials to exist:

- `Notion account`
- `Google Gemini(PaLM) Api account`

The `tool_wikimedia_search` workflow only uses public Wikipedia requests, so it does not need an external token.

## Setup

1. Create and activate a virtual environment.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-callback.txt
```

2. Start the container stack.

```bash
docker compose up -d
```

3. Open n8n at `http://localhost:5678`.

4. Import the workflows from `n8n_exports/` if they are not already present in your instance.

5. Recreate the credentials in n8n using the names listed above, then bind them to the imported workflows.

6. Replace the Notion root page URLs inside the workflow with your own pages or databases before running it, so the workflow populates your Notion workspace instead of the original one.

## Running the services

### Callback API

```bash
uvicorn callback_api.main:app --host 0.0.0.0 --port 8000
```

The callback API exposes:

- `GET /health`
- `POST /callback`

### SQLite viewer

The `sqlite-web` service is available at `http://localhost:8081`.

To retry every failed item from the SQLite UI, open the SQL editor and run:

```sql
UPDATE pdf_queue
SET status = 'queued',
	attempt_count = 0,
	last_error = NULL,
	next_attempt_at = NULL
WHERE status = 'failed';
```

If you want to confirm the rows before re-queuing them, use:

```sql
SELECT hash, file_path, status, attempt_count, last_error
FROM pdf_queue
WHERE status = 'failed'
ORDER BY updated_at DESC;
```

### Push queued PDFs to n8n

```bash
python push_to_n8n.py
```

Or keep the loop alive:

```bash
bash run_push.sh
```

The containerized version uses the same script through the `push-to-n8n` compose service.

### Convert PDFs to text

`index_pdfs.py` can be used to extract text and estimate token usage for a folder of PDFs.

## Reusable n8n export

The repository keeps a clean export of the workflows in `n8n_exports/` and leaves the live n8n database out of Git.

The `push-to-n8n` service is gated by Docker healthchecks on `callback-api` and `n8n`, so it only starts once the stack is actually ready.

To refresh the export from the running container:

```bash
docker compose exec -T n8n n8n export:workflow --all --pretty --separate --output=/exports
```

The custom node dependency is declared in `n8n_custom_nodes/package.json`, which is mounted into the container as `/home/node/.n8n/nodes`.

## Optional systemd install

Use `systemd/push_to_n8n.service` as the template for a boot-time launcher. For example:

```bash
sudo cp systemd/push_to_n8n.service /etc/systemd/system/push_to_n8n.service
sudo systemctl daemon-reload
sudo systemctl enable --now push_to_n8n.service
```

The unit runs `docker compose up -d --wait`, which lets Docker start `push-to-n8n` only after the `callback-api` and `n8n` healthchecks pass.

## Notes

- The current workflow export includes the active `ficheur` workflow and the reusable `tool_wikimedia_search` workflow.
