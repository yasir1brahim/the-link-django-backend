from apps.group_chat.routing import websocket_urlpatterns as group_chat_patterns
from apps.deliverables.routing import websocket_urlpatterns as specgpt_patterns


urlpatterns = group_chat_patterns + specgpt_patterns
