from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/specgpt/(?P<project_id>\w+)/$', consumers.SpecGptWebSocketConsumer.as_asgi()),
] 