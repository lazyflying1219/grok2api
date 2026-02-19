from __future__ import annotations

import app.services.register.runner as runner_module


def test_record_error_logs_and_calls_callback(monkeypatch):
    callback_messages = []
    log_messages = []

    def _on_error(message: str) -> None:
        callback_messages.append(message)

    def _fake_warning(fmt: str, *args):
        log_messages.append(fmt.format(*args) if args else fmt)

    monkeypatch.setattr(runner_module.logger, "warning", _fake_warning)

    runner = runner_module.RegisterRunner(
        target_count=1,
        thread_count=1,
        on_error=_on_error,
    )

    runner._record_error("boom")

    assert callback_messages == ["boom"]
    assert any("boom" in line for line in log_messages)
