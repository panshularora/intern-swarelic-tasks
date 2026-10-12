import logging
from django.db import transaction
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import CallQueue, QueuedCall
from .serializers import CallQueueSerializer, EnqueueSerializer, QueuedCallSerializer
from .tasks import alert_queue_threshold

logger = logging.getLogger(__name__)


class CallQueueViewSet(viewsets.ModelViewSet):
    queryset = CallQueue.objects.all()
    serializer_class = CallQueueSerializer
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        qs = CallQueue.objects.all()
        tenant = self.request.query_params.get('tenant')
        if tenant:
            qs = qs.filter(tenant=tenant)
        return qs

    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        queue = self.get_object()
        waiting_qs = queue.calls.filter(status='waiting')
        finished = list(queue.calls.exclude(status='waiting'))
        answered = queue.calls.filter(status='answered').count()
        abandoned = queue.calls.filter(status='abandoned').count()
        done = answered + abandoned

        waits = [c.wait_secs() for c in finished]
        waiting_waits = [c.wait_secs() for c in waiting_qs]
        all_waits = waits + waiting_waits

        payload = {
            'queue_id': queue.id,
            'name': queue.name,
            'tenant': queue.tenant,
            'current_calls': waiting_qs.count(),
            'max_size': queue.max_size,
            'answered': answered,
            'abandoned': abandoned,
            'avg_wait_secs': round(sum(waits) / len(waits), 2) if waits else 0,
            'longest_wait_secs': round(max(all_waits), 2) if all_waits else 0,
            'abandonment_rate': round((abandoned / done) * 100, 2) if done else 0,
        }
        return Response(payload)

    @action(detail=True, methods=['post'])
    def enqueue(self, request, pk=None):
        queue = self.get_object()
        ser = EnqueueSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        with transaction.atomic():
            locked = CallQueue.objects.select_for_update().get(pk=queue.pk)
            waiting = locked.calls.filter(status='waiting').count()
            if waiting >= locked.max_size:
                return Response(
                    {'detail': 'Queue is full.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            call = QueuedCall.objects.create(
                queue=locked,
                caller_number=ser.validated_data['caller_number'],
                priority=ser.validated_data.get('priority', 100),
            )
            locked.current_calls = waiting + 1
            locked.save(update_fields=['current_calls'])

        if locked.current_calls > locked.alert_threshold:
            alert_queue_threshold.delay(locked.id)

        logger.info("Enqueued %s on queue %s", call.caller_number, locked.id)
        return Response(QueuedCallSerializer(call).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def dequeue(self, request, pk=None):
        queue = self.get_object()
        with transaction.atomic():
            locked = CallQueue.objects.select_for_update().get(pk=queue.pk)
            call = (
                locked.calls.select_for_update()
                .filter(status='waiting')
                .order_by('priority', 'enqueued_at')
                .first()
            )
            if call is None:
                return Response(
                    {'detail': 'Queue is empty.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            call.status = 'answered'
            call.left_at = timezone.now()
            call.save(update_fields=['status', 'left_at'])
            locked.current_calls = locked.calls.filter(status='waiting').count()
            locked.save(update_fields=['current_calls'])

        logger.info("Dequeued %s from queue %s", call.caller_number, locked.id)
        return Response(QueuedCallSerializer(call).data)

    @action(detail=True, methods=['post'])
    def abandon(self, request, pk=None):
        """Mark the longest-waiting call as abandoned (caller hung up)."""
        queue = self.get_object()
        with transaction.atomic():
            locked = CallQueue.objects.select_for_update().get(pk=queue.pk)
            call = (
                locked.calls.select_for_update()
                .filter(status='waiting')
                .order_by('enqueued_at')
                .first()
            )
            if call is None:
                return Response(
                    {'detail': 'Queue is empty.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            call.status = 'abandoned'
            call.left_at = timezone.now()
            call.save(update_fields=['status', 'left_at'])
            locked.current_calls = locked.calls.filter(status='waiting').count()
            locked.save(update_fields=['current_calls'])
        return Response(QueuedCallSerializer(call).data)
