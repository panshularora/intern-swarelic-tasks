# Exercise 4.5 — Call Queue API

Standalone Django + DRF mini feature. Option A from the brief.

## What it does

- `CallQueue` per tenant, with `max_size` and `alert_threshold`
- Calls sit on the queue as `QueuedCall` rows (waiting / answered / abandoned)
- VIP-ish ordering via `priority` (lower number is served first)
- Celery task mails a supervisor when waiting > threshold

## Endpoints

| Method | Path | Notes |
|--------|------|--------|
| GET | `/api/v1/queues/` | list, `?tenant=` filter |
| POST | `/api/v1/queues/` | create |
| GET | `/api/v1/queues/<id>/stats/` | avg wait, longest wait, abandonment rate |
| POST | `/api/v1/queues/<id>/enqueue/` | body: `caller_number`, optional `priority` |
| POST | `/api/v1/queues/<id>/dequeue/` | next waiting call → answered |
| POST | `/api/v1/queues/<id>/abandon/` | oldest waiting call hung up |

## Run locally

```bash
cd submissions/panshularora/4.5
python -m venv venv
venv\Scripts\activate          # linux: source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py test queues
python manage.py runserver
```

Celery is set to `ALWAYS_EAGER` so you don't need Redis for the homework. To run a real worker later, point `CELERY_BROKER_URL` at Redis and flip eager off.
