"""Runtime-owned review horizon; estimates reserve capacity, never fake usage."""
import time
import inspect
import asyncio


class ReviewBudget:
    def __init__(self, records, *, max_calls=20, max_tokens=150000, seconds=300):
        self.records = records
        self.calls = 0
        self.max_calls, self.max_tokens = max_calls, max_tokens
        self.deadline = time.monotonic() + seconds
        self.last_known = True

    def status(self, provider):
        remaining = {'calls': self.max_calls - self.calls,
                     'tokens': self.max_tokens - sum(r.total_tokens for r in self.records),
                     'seconds': self.deadline - time.monotonic()}
        # An outer campaign may have spent tokens before entering this review.
        external = getattr(provider, 'review_budget_status', None)
        if callable(external) and not inspect.iscoroutinefunction(external):
            outer = external()
            if isinstance(outer, dict):
                for key in remaining:
                    if type(outer.get(key)) in (int, float):
                        remaining[key] = min(remaining[key], outer[key])
        # Include retained history plus an unseen maximum-sized source page and
        # output allowance. This is conservative capacity planning, not billing.
        reserve = (self.records[-1].input_tokens if self.records else 0) + 14000 + 4096
        remaining.update(reserved_tokens=reserve, usage_known=self.last_known,
            conclude_now=(remaining['calls'] <= 2 or remaining['tokens'] <= 2 * reserve
                          or remaining['seconds'] <= 45 or not self.last_known))
        return remaining

    async def call(self, provider, **kwargs):
        status = self.status(provider)
        if min(status[k] for k in ('calls', 'tokens', 'seconds')) <= 0:
            raise RuntimeError('Review budget exhausted; no inference authorized')
        before = len(self.records)
        self.calls += 1
        try:
            return await asyncio.wait_for(provider.chat_complete(**kwargs), timeout=status['seconds'])
        finally:
            self.last_known = len(self.records) > before
