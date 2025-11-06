# Redis Channel Layer Fix

## Problem
WebSocket connections were failing with:
```
redis.exceptions.ConnectionError: Error -2 connecting to redis:6379. Name or service not known.
```

## Root Cause
- Django Channels was configured to use Redis for its channel layer
- Redis service was commented out in `docker-compose.yml`
- WebSocket consumer was trying to use channel layers (group messaging) but Redis wasn't available

## Solution Applied

### 1. Updated Channel Layer Configuration (`the_link/settings.py`)

Changed from always using Redis:
```python
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [REDIS_URL],
        },
    },
}
```

To environment-based configuration:
```python
# Use in-memory channel layer for local development, Redis for production
if ENVIRONMENT == 'local':
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer"
        }
    }
else:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {
                "hosts": [REDIS_URL],
            },
        },
    }
```

### 2. Simplified WebSocket Consumer (`apps/deliverables/consumers.py`)

Removed channel layer dependency (group messaging) since it's not needed:
- Removed `channel_layer.group_add()` in `connect()`
- Removed `channel_layer.group_discard()` in `disconnect()`

Each user has their own WebSocket connection and doesn't need to broadcast to other users.

## Benefits

### Local Development
- ✅ No Redis required for development
- ✅ Simpler setup (just PostgreSQL)
- ✅ Faster startup time
- ✅ WebSocket connections work immediately

### Production
- ✅ Still uses Redis for scalability
- ✅ Can handle multiple server instances
- ✅ Better performance at scale

## Alternative Solution (If You Need Redis)

If you want to use Redis in local development (for Celery or other features), uncomment the Redis service in `docker-compose.yml`:

```yaml
redis:
  image: redis
  # persistent storage
  command: redis-server --appendonly yes
  volumes:
    - redis_data:/data
  healthcheck:
    test: bash -c 'exec 6<>/dev/tcp/redis/6379'
    interval: 2s
    retries: 10
```

And update the web service dependency:
```yaml
web:
  depends_on:
    db:
      condition: service_healthy
    redis:
      condition: service_healthy
```

And add the volume:
```yaml
volumes:
  postgres_data:
  redis_data:
```

## Testing

After applying the fix, verify WebSocket connections work:

1. Start the application: `docker-compose up`
2. Navigate to Compass chat
3. Enable the `specgpt_websockets` feature flag
4. Send a message
5. Verify you see streaming responses (tokens appearing in real-time)

## Notes

- **InMemoryChannelLayer** works fine for single-server deployments
- For production with multiple servers, Redis is recommended
- The change is backwards compatible - existing functionality still works
- No data migration needed

## Related Files

- `the_link/settings.py` - Channel layer configuration
- `apps/deliverables/consumers.py` - WebSocket consumer
- `docker-compose.yml` - Redis service configuration (commented out)









