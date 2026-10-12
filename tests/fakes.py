"""Fake Apify client (no network, no cost) + helpers to raise REAL apify-client errors."""
from types import SimpleNamespace

from apify_client.errors import ApifyApiError


def api_error(status: int, message: str = "boom"):
    """A real ApifyApiError (the right subclass for the status code is chosen by the library)."""
    response = SimpleNamespace(status_code=status, text=message,
                               json=lambda: {"error": {"type": "x", "message": message}})
    return ApifyApiError(response, 1)


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class FakeRun(SimpleNamespace):
    pass


class FakeRunClient:
    def __init__(self, client):
        self.client = client

    def wait_for_finish(self, *, wait_duration=None):
        self.client.clock.now += wait_duration.total_seconds() if wait_duration else 0
        self.client.wait_calls += 1
        if self.client.wait_error:
            raise self.client.wait_error
        statuses = self.client.statuses
        status = statuses[min(self.client.wait_calls - 1, len(statuses) - 1)]
        return FakeRun(id="run1", status=status, default_dataset_id="ds1")

    def abort(self):
        self.client.aborted = True


class FakeActor:
    def __init__(self, client):
        self.client = client

    def start(self, *, run_input=None, run_timeout=None, **kwargs):
        if self.client.start_error:
            raise self.client.start_error
        self.client.run_input = run_input
        self.client.run_timeout = run_timeout
        self.client.actor_id = self.client.requested_actor
        return FakeRun(id="run1", status="READY", default_dataset_id="ds1")


class FakeDataset:
    def __init__(self, client):
        self.client = client

    def iterate_items(self, *, limit=None, **kwargs):
        if self.client.dataset_error:
            raise self.client.dataset_error
        yield from (self.client.items if limit is None else self.client.items[:limit])


class FakeClient:
    """Configure behaviour through attributes, then pass `lambda token: client` as the factory."""

    def __init__(self, items=None, statuses=("RUNNING", "SUCCEEDED"), start_error=None,
                 wait_error=None, dataset_error=None, clock=None):
        self.items = items or []
        self.statuses = list(statuses)
        self.start_error, self.wait_error, self.dataset_error = start_error, wait_error, dataset_error
        self.clock = clock or FakeClock()
        self.wait_calls = 0
        self.aborted = False
        self.run_input = self.run_timeout = self.actor_id = None
        self.requested_actor = None
        self.token = None

    def factory(self):
        def make(token):
            self.token = token
            return self
        return make

    def actor(self, actor_id):
        self.requested_actor = actor_id
        return FakeActor(self)

    def run(self, run_id):
        return FakeRunClient(self)

    def dataset(self, dataset_id):
        return FakeDataset(self)
