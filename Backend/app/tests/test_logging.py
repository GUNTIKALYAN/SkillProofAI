import logging

from app import logging_config
from app.logging_config import configure_logging


def test_running_app_writes_backend_worker_and_mcp_logs(monkeypatch, tmp_path) -> None:
    original = logging_config._LOG_DIR
    monkeypatch.setattr(logging_config, "_LOG_DIR", tmp_path)
    try:
        configure_logging()
        logging.getLogger("app.main").info("api started")
        logging.getLogger("app.mcp_client.transport").error("mcp transport failed server=github")
        configure_logging("worker")
        logging.getLogger("app.worker").info("worker started")
        for handler in logging.getLogger().handlers:
            handler.flush()
        backend = (tmp_path / "backend-logs").read_text(encoding="utf-8")
        mcp = (tmp_path / "mcp-logs").read_text(encoding="utf-8")
        worker = (tmp_path / "worker-logs").read_text(encoding="utf-8")
    finally:
        monkeypatch.setattr(logging_config, "_LOG_DIR", original)
        configure_logging()
    assert "api started" in backend
    assert "mcp transport failed" in mcp
    assert "api started" not in mcp
    assert "worker started" in worker
    assert "api started" not in worker
