# Christopher Mee
# 2026-07-09
# Rate limiter to avoid '429' rate limited error.

import threading
import time
from functools import wraps


class RateLimiter:
    def __init__(self, callsPerSecond):
        self.lock = threading.Lock()
        self.minInterval = 1.0 / callsPerSecond
        self.lastCall = 0.0

    # Wait if necessary, until minimum interval has passed.
    def wait(self):
        with self.lock:
            now = time.monotonic()
            elapsed = now - self.lastCall
            if elapsed < self.minInterval:
                time.sleep(self.minInterval - elapsed)
                self.lastCall = time.monotonic()


def rateLimited(rateLimiter):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            rateLimiter.wait()
            return func(*args, **kwargs)

        return wrapper

    return decorator
