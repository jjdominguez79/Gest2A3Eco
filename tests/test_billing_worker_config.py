"""Tests de BillingWorkerConfig: secretos por archivo, defaults, limites."""

from __future__ import annotations

import pytest

from billing_worker.config import BillingWorkerConfig


def test_from_environment_reads_secret_from_file(tmp_path, monkeypatch):
    secret_file = tmp_path / "billing_key"
    secret_file.write_text("  super-secret-key  \n", encoding="utf-8")

    monkeypatch.setenv("BILLING_WORKER_BACKEND_URL", "https://backend.example/")
    monkeypatch.setenv("BILLING_WORKER_API_KEY_FILE", str(secret_file))
    monkeypatch.delenv("BILLING_WORKER_ID", raising=False)

    config = BillingWorkerConfig.from_environment()

    assert config.backend_url == "https://backend.example"  # sin barra final
    assert config.api_key == "super-secret-key"
    assert config.instance_id  # generado automaticamente
    assert config.poll_interval_seconds == 15
    assert config.lease_minutes == 10
    assert config.heartbeat_interval_seconds == 60
    assert config.max_backoff_seconds == 300


def test_missing_backend_url_raises(tmp_path, monkeypatch):
    secret_file = tmp_path / "billing_key"
    secret_file.write_text("secret", encoding="utf-8")
    monkeypatch.delenv("BILLING_WORKER_BACKEND_URL", raising=False)
    monkeypatch.setenv("BILLING_WORKER_API_KEY_FILE", str(secret_file))

    with pytest.raises(ValueError):
        BillingWorkerConfig.from_environment()


def test_missing_secret_file_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("BILLING_WORKER_BACKEND_URL", "https://backend.example")
    monkeypatch.setenv("BILLING_WORKER_API_KEY_FILE", str(tmp_path / "does-not-exist"))

    with pytest.raises(ValueError):
        BillingWorkerConfig.from_environment()


def test_lease_minutes_is_clamped_to_sixty(tmp_path, monkeypatch):
    secret_file = tmp_path / "billing_key"
    secret_file.write_text("secret", encoding="utf-8")
    monkeypatch.setenv("BILLING_WORKER_BACKEND_URL", "https://backend.example")
    monkeypatch.setenv("BILLING_WORKER_API_KEY_FILE", str(secret_file))
    monkeypatch.setenv("BILLING_WORKER_LEASE_MINUTES", "999")

    config = BillingWorkerConfig.from_environment()
    assert config.lease_minutes == 60


def test_explicit_instance_id_is_honored(tmp_path, monkeypatch):
    secret_file = tmp_path / "billing_key"
    secret_file.write_text("secret", encoding="utf-8")
    monkeypatch.setenv("BILLING_WORKER_BACKEND_URL", "https://backend.example")
    monkeypatch.setenv("BILLING_WORKER_API_KEY_FILE", str(secret_file))
    monkeypatch.setenv("BILLING_WORKER_ID", "railway-replica-2")

    config = BillingWorkerConfig.from_environment()
    assert config.instance_id == "railway-replica-2"
