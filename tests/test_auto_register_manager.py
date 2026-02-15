from __future__ import annotations

import asyncio
from contextlib import suppress

import app.services.register.manager as manager_module


def test_stop_job_timeout_does_not_cancel_underlying_task(monkeypatch):
    async def _case():
        mgr = manager_module.AutoRegisterManager()
        job = manager_module.RegisterJob(
            job_id="job1",
            total=1,
            pool="ssoBasic",
            status="running",
        )
        never = asyncio.Event()

        async def _long_running() -> None:
            await never.wait()

        task = asyncio.create_task(_long_running())
        mgr._job = job
        mgr._task = task

        class _DummySolver:
            def stop(self) -> None:
                return None

        mgr._solver = _DummySolver()

        async def _fake_wait_for(awaitable, _timeout):
            # Simulate asyncio.wait_for timeout semantics:
            # when passing the raw task it gets cancelled on timeout.
            if awaitable is task:
                task.cancel()
            raise TimeoutError()

        monkeypatch.setattr(manager_module.asyncio, "wait_for", _fake_wait_for)

        await mgr.stop_job()
        await asyncio.sleep(0)

        assert job.status == "stopping"
        assert job.stop_event.is_set()
        assert not task.cancelled()

        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    asyncio.run(_case())


def test_run_job_respects_pre_stop_and_does_not_enter_running(monkeypatch):
    calls = {"runner_run": 0}

    class _DummySolver:
        def __init__(self, config):
            self.config = config

        def start(self) -> None:
            return None

        def stop(self) -> None:
            return None

    class _DummyRunner:
        def __init__(self, **_kwargs):
            pass

        def run(self):
            calls["runner_run"] += 1
            return []

    def _fake_get_config(key, default=None):
        if key == "register.auto_start_solver":
            return False
        if key == "register.yescaptcha_key":
            return ""
        if key == "register.max_errors":
            return 5
        if key == "register.max_runtime_minutes":
            return 1
        return default

    monkeypatch.setattr(manager_module, "TurnstileSolverProcess", _DummySolver)
    monkeypatch.setattr(manager_module, "RegisterRunner", _DummyRunner)
    monkeypatch.setattr(manager_module, "get_config", _fake_get_config)

    mgr = manager_module.AutoRegisterManager()
    job = manager_module.RegisterJob(job_id="job2", total=1, pool="ssoBasic")
    job.stop_event.set()

    asyncio.run(mgr._run_job(job))

    assert job.status == "stopped"
    assert calls["runner_run"] == 0
