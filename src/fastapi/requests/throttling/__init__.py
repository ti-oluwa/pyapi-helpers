"""
Utilities for API routes throttling in FastAPI.

Uses Redis as the backend for storing throttling data.

Adapted from `fastapi-limiter` package.

Usage:

In a FastAPI application setup:
```python

import fastapi

from src.fastapi.requests.throttling import configure

def lifespan(app: fastapi.FastAPI):
    try:
        async configure(
            persistent=app.debug is False,
            # Disables persistent rate limiting in debug mode,
            # Useful in development environments.
            redis="redis://localhost/0"
        ):
            yield
    finally:
        pass

app = fastapi.FastAPI(lifespan=lifespan)
```

In a FastAPI route/endpoint:
```python
from src.fastapi.requests.throttling import throttle

router = fastapi.APIRouter()

@router.get("some-route")
@throttle(limit=20, seconds=10) # Burst limit of 20 requests in 10 seconds
@throttle(limit=10000, hours=4) # Sustained limit of 10000 requests in 4 hours
async def some_route():
    pass
"""

from src.dependencies import deps_required

deps_required({"redis": "redis"})

from .base import *  # noqa
from .throttles import *  # noqa
from .shortcuts import throttle  # noqa
