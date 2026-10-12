from django.db import models
from django.utils import timezone


class CallQueue(models.Model):
    name = models.CharField(max_length=120)
    tenant = models.CharField(max_length=120)
    max_size = models.PositiveIntegerField(default=50)
    current_calls = models.PositiveIntegerField(default=0)
    alert_threshold = models.PositiveIntegerField(default=10)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        unique_together = ('tenant', 'name')

    def __str__(self):
        return f"{self.tenant}/{self.name}"

    def refresh_current_calls(self):
        waiting = self.calls.filter(status='waiting').count()
        if waiting != self.current_calls:
            self.current_calls = waiting
            self.save(update_fields=['current_calls'])
        return waiting


class QueuedCall(models.Model):
    STATUS_CHOICES = [
        ('waiting', 'Waiting'),
        ('answered', 'Answered'),
        ('abandoned', 'Abandoned'),
    ]

    queue = models.ForeignKey(CallQueue, related_name='calls', on_delete=models.CASCADE)
    caller_number = models.CharField(max_length=20)
    # lower number is served first (VIP = 1)
    priority = models.PositiveIntegerField(default=100)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='waiting')
    enqueued_at = models.DateTimeField(auto_now_add=True)
    left_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['priority', 'enqueued_at']

    def __str__(self):
        return f"{self.caller_number} @ {self.queue.name} ({self.status})"

    def wait_secs(self) -> float:
        end = self.left_at or timezone.now()
        return (end - self.enqueued_at).total_seconds()
