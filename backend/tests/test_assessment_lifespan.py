import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.main import app, lifespan


class AssessmentLifespanTests(unittest.IsolatedAsyncioTestCase):
    async def test_shutdown_waits_for_worker_cancellation_before_disposing_database(self):
        started, stopped = asyncio.Event(), asyncio.Event()

        async def worker(*_):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

        async def dispose():
            self.assertTrue(stopped.is_set())

        with patch("app.main.create_tables", new_callable=AsyncMock), \
             patch("app.main.worker_loop", new=worker), \
             patch("app.main.engine", new=SimpleNamespace(dispose=dispose)), \
             patch("app.main.settings.assessment_worker_enabled", True):
            async with lifespan(app):
                await asyncio.wait_for(started.wait(), timeout=2)
        self.assertTrue(stopped.is_set())

    async def test_worker_can_be_disabled(self):
        with patch("app.main.create_tables", new_callable=AsyncMock), \
             patch("app.main.worker_loop", new_callable=AsyncMock) as worker, \
             patch("app.main.engine", new=SimpleNamespace(dispose=AsyncMock())), \
             patch("app.main.settings.assessment_worker_enabled", False):
            async with lifespan(app):
                pass
            worker.assert_not_called()
