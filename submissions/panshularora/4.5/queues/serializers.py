from rest_framework import serializers
from .models import CallQueue, QueuedCall


class CallQueueSerializer(serializers.ModelSerializer):
    class Meta:
        model = CallQueue
        fields = [
            'id', 'name', 'tenant', 'max_size', 'current_calls',
            'alert_threshold', 'created_at',
        ]
        read_only_fields = ['id', 'current_calls', 'created_at']

    def validate_max_size(self, value):
        if value < 1:
            raise serializers.ValidationError('max_size must be at least 1.')
        return value

    def validate_alert_threshold(self, value):
        if value < 1:
            raise serializers.ValidationError('alert_threshold must be at least 1.')
        return value


class EnqueueSerializer(serializers.Serializer):
    caller_number = serializers.CharField(max_length=20)
    priority = serializers.IntegerField(min_value=1, required=False, default=100)

    def validate_caller_number(self, value):
        cleaned = value.strip()
        if len(cleaned) < 7:
            raise serializers.ValidationError('Caller number must be at least 7 characters.')
        allowed = set('0123456789+- ')
        if any(ch not in allowed for ch in cleaned):
            raise serializers.ValidationError(
                'Caller number can only contain digits, +, - and spaces.'
            )
        return cleaned


class QueuedCallSerializer(serializers.ModelSerializer):
    wait_secs = serializers.SerializerMethodField()

    class Meta:
        model = QueuedCall
        fields = [
            'id', 'caller_number', 'priority', 'status',
            'enqueued_at', 'left_at', 'wait_secs',
        ]

    def get_wait_secs(self, obj):
        return round(obj.wait_secs(), 2)
