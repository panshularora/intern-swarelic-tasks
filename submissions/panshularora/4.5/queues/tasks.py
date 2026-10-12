import logging
from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


@shared_task
def alert_queue_threshold(queue_id: int):
    """Email supervisor when a queue is over its alert threshold."""
    from .models import CallQueue

    try:
        queue = CallQueue.objects.get(id=queue_id)
    except CallQueue.DoesNotExist:
        logger.error("CallQueue %s not found", queue_id)
        return {'status': 'missing', 'queue_id': queue_id}

    waiting = queue.refresh_current_calls()
    if waiting <= queue.alert_threshold:
        logger.info(
            "Queue %s is at %s (threshold %s) — no alert",
            queue_id, waiting, queue.alert_threshold,
        )
        return {'status': 'ok', 'queue_id': queue_id, 'waiting': waiting}

    send_mail(
        subject=f"Queue alert: {queue.tenant}/{queue.name}",
        message=(
            f"Queue {queue.name} for tenant {queue.tenant} has {waiting} waiting calls "
            f"(threshold {queue.alert_threshold}, max {queue.max_size})."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[settings.SUPERVISOR_EMAIL],
        fail_silently=True,
    )
    logger.warning("Queue %s over threshold: %s waiting", queue_id, waiting)
    return {
        'status': 'alerted',
        'queue_id': queue_id,
        'waiting': waiting,
        'threshold': queue.alert_threshold,
    }
