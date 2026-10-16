from pathlib import Path

from app.config import BACKEND_ENV_FILE, Settings


def test_backend_env_file_is_absolute_and_loads_from_any_working_directory(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    assert BACKEND_ENV_FILE.is_absolute()
    assert BACKEND_ENV_FILE == Path(__file__).resolve().parents[1] / ".env"

    env_file = tmp_path / "backend.env"
    env_file.write_text("GEMINI_API_KEY=test-only-key\nGEMINI_MODEL=test-model\n", encoding="utf-8")
    loaded = Settings(_env_file=env_file)
    assert loaded.GEMINI_API_KEY == "test-only-key"
    assert loaded.GEMINI_MODEL == "test-model"


def test_missing_env_file_leaves_gemini_unconfigured(monkeypatch, tmp_path):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    loaded = Settings(_env_file=tmp_path / "missing.env")

    assert loaded.GEMINI_API_KEY == ""
    assert loaded.GEMINI_MODEL == "gemini-2.0-flash"