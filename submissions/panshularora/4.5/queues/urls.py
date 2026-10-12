from rest_framework.routers import DefaultRouter
from .views import CallQueueViewSet

router = DefaultRouter()
router.register(r'queues', CallQueueViewSet, basename='queue')

urlpatterns = router.urls
