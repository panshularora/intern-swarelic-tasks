from django.contrib import admin
from .models import CallQueue, QueuedCall


@admin.register(CallQueue)
class CallQueueAdmin(admin.ModelAdmin):
    list_display = ('name', 'tenant', 'current_calls', 'max_size', 'alert_threshold')
    list_filter = ('tenant',)


@admin.register(QueuedCall)
class QueuedCallAdmin(admin.ModelAdmin):
    list_display = ('caller_number', 'queue', 'status', 'priority', 'enqueued_at')
    list_filter = ('status',)
