from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from queues.models import CallQueue, QueuedCall
from queues.tasks import alert_queue_threshold


@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
)
class CallQueueApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.queue = CallQueue.objects.create(
            name='support',
            tenant='acme',
            max_size=2,
            alert_threshold=1,
        )

    def test_list_queues(self):
        resp = self.client.get('/api/v1/queues/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['count'], 1)
        self.assertEqual(resp.data['results'][0]['name'], 'support')

    def test_list_queues_tenant_filter(self):
        CallQueue.objects.create(name='sales', tenant='other', max_size=5)
        resp = self.client.get('/api/v1/queues/', {'tenant': 'acme'})
        self.assertEqual(resp.data['count'], 1)

    def test_create_queue(self):
        resp = self.client.post('/api/v1/queues/', {
            'name': 'billing',
            'tenant': 'acme',
            'max_size': 10,
            'alert_threshold': 8,
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(CallQueue.objects.filter(name='billing').count(), 1)

    def test_create_queue_rejects_zero_max_size(self):
        resp = self.client.post('/api/v1/queues/', {
            'name': 'bad',
            'tenant': 'acme',
            'max_size': 0,
        }, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_enqueue_adds_call(self):
        resp = self.client.post(
            f'/api/v1/queues/{self.queue.id}/enqueue/',
            {'caller_number': '+91-9876543210'},
            format='json',
        )
        self.assertEqual(resp.status_code, 201)
        self.queue.refresh_from_db()
        self.assertEqual(self.queue.current_calls, 1)
        self.assertEqual(QueuedCall.objects.filter(status='waiting').count(), 1)

    def test_enqueue_rejects_short_number(self):
        resp = self.client.post(
            f'/api/v1/queues/{self.queue.id}/enqueue/',
            {'caller_number': '12'},
            format='json',
        )
        self.assertEqual(resp.status_code, 400)

    def test_enqueue_when_full_returns_400(self):
        self.client.post(
            f'/api/v1/queues/{self.queue.id}/enqueue/',
            {'caller_number': '+91-1111111111'},
            format='json',
        )
        self.client.post(
            f'/api/v1/queues/{self.queue.id}/enqueue/',
            {'caller_number': '+91-2222222222'},
            format='json',
        )
        resp = self.client.post(
            f'/api/v1/queues/{self.queue.id}/enqueue/',
            {'caller_number': '+91-3333333333'},
            format='json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn('full', resp.data['detail'].lower())

    def test_dequeue_empty_returns_400(self):
        resp = self.client.post(f'/api/v1/queues/{self.queue.id}/dequeue/')
        self.assertEqual(resp.status_code, 400)

    def test_dequeue_serves_vip_first(self):
        self.client.post(
            f'/api/v1/queues/{self.queue.id}/enqueue/',
            {'caller_number': '+91-1111111111', 'priority': 100},
            format='json',
        )
        self.client.post(
            f'/api/v1/queues/{self.queue.id}/enqueue/',
            {'caller_number': '+91-9999999999', 'priority': 1},
            format='json',
        )
        resp = self.client.post(f'/api/v1/queues/{self.queue.id}/dequeue/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['caller_number'], '+91-9999999999')
        self.assertEqual(resp.data['status'], 'answered')

    def test_abandon_updates_stats(self):
        self.client.post(
            f'/api/v1/queues/{self.queue.id}/enqueue/',
            {'caller_number': '+91-1111111111'},
            format='json',
        )
        self.client.post(f'/api/v1/queues/{self.queue.id}/abandon/')
        resp = self.client.get(f'/api/v1/queues/{self.queue.id}/stats/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['abandoned'], 1)
        self.assertEqual(resp.data['abandonment_rate'], 100.0)
        self.assertEqual(resp.data['current_calls'], 0)

    def test_stats_on_empty_queue(self):
        resp = self.client.get(f'/api/v1/queues/{self.queue.id}/stats/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['avg_wait_secs'], 0)
        self.assertEqual(resp.data['longest_wait_secs'], 0)
        self.assertEqual(resp.data['abandonment_rate'], 0)

    def test_missing_queue_404(self):
        resp = self.client.get('/api/v1/queues/999/stats/')
        self.assertEqual(resp.status_code, 404)

    def test_alert_task_when_over_threshold(self):
        self.client.post(
            f'/api/v1/queues/{self.queue.id}/enqueue/',
            {'caller_number': '+91-1111111111'},
            format='json',
        )
        # threshold is 1, second call should trip the celery task (eager)
        self.client.post(
            f'/api/v1/queues/{self.queue.id}/enqueue/',
            {'caller_number': '+91-2222222222'},
            format='json',
        )
        result = alert_queue_threshold(self.queue.id)
        self.assertEqual(result['status'], 'alerted')
        self.assertEqual(result['waiting'], 2)
