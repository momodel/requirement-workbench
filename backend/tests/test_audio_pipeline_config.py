import app.config as config_module
from app.config import AppSettings


AUDIO_ENV_KEYS = (
    "REQUIREMENT_WORKBENCH_QINIU_ACCESS_KEY",
    "REQUIREMENT_WORKBENCH_QINIU_SECRET_KEY",
    "REQUIREMENT_WORKBENCH_QINIU_BUCKET",
    "REQUIREMENT_WORKBENCH_QINIU_DOMAIN",
    "REQUIREMENT_WORKBENCH_QINIU_KEY_PREFIX",
    "REQUIREMENT_WORKBENCH_AUDIO_TRANSCRIPTION_BACKEND",
    "REQUIREMENT_WORKBENCH_AUDIO_TRANSCRIPTION_TIMEOUT_SECONDS",
    "REQUIREMENT_WORKBENCH_AUDIO_TRANSCRIPTION_POLL_INTERVAL_SECONDS",
    "REQUIREMENT_WORKBENCH_ALIYUN_AK_ID",
    "REQUIREMENT_WORKBENCH_ALIYUN_AK_SECRET",
    "REQUIREMENT_WORKBENCH_ALIYUN_APP_KEY",
    "REQUIREMENT_WORKBENCH_ALIYUN_FILETRANS_REGION",
)


def _clear_audio_env(monkeypatch) -> None:
    for key in AUDIO_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_from_env_reads_qiniu_and_aliyun_audio_settings(monkeypatch) -> None:
    monkeypatch.setattr(config_module, "_load_local_env_file", lambda _root_dir: None)
    _clear_audio_env(monkeypatch)

    monkeypatch.setenv("REQUIREMENT_WORKBENCH_QINIU_ACCESS_KEY", "qiniu-ak")
    monkeypatch.setenv("REQUIREMENT_WORKBENCH_QINIU_SECRET_KEY", "qiniu-sk")
    monkeypatch.setenv("REQUIREMENT_WORKBENCH_QINIU_BUCKET", "audio-bucket")
    monkeypatch.setenv("REQUIREMENT_WORKBENCH_QINIU_DOMAIN", "https://audio.example.com/")
    monkeypatch.setenv("REQUIREMENT_WORKBENCH_QINIU_KEY_PREFIX", "customer-audio")
    monkeypatch.setenv(
        "REQUIREMENT_WORKBENCH_AUDIO_TRANSCRIPTION_BACKEND",
        "aliyun_filetrans",
    )
    monkeypatch.setenv(
        "REQUIREMENT_WORKBENCH_AUDIO_TRANSCRIPTION_TIMEOUT_SECONDS",
        "321",
    )
    monkeypatch.setenv(
        "REQUIREMENT_WORKBENCH_AUDIO_TRANSCRIPTION_POLL_INTERVAL_SECONDS",
        "0.5",
    )
    monkeypatch.setenv("REQUIREMENT_WORKBENCH_ALIYUN_AK_ID", "aliyun-ak")
    monkeypatch.setenv("REQUIREMENT_WORKBENCH_ALIYUN_AK_SECRET", "aliyun-sk")
    monkeypatch.setenv("REQUIREMENT_WORKBENCH_ALIYUN_APP_KEY", "aliyun-app-key")
    monkeypatch.setenv(
        "REQUIREMENT_WORKBENCH_ALIYUN_FILETRANS_REGION",
        "cn-shanghai",
    )

    settings = AppSettings.from_env()

    assert settings.qiniu_access_key == "qiniu-ak"
    assert settings.qiniu_secret_key == "qiniu-sk"
    assert settings.qiniu_bucket == "audio-bucket"
    assert settings.qiniu_domain == "https://audio.example.com/"
    assert settings.qiniu_key_prefix == "customer-audio"
    assert settings.audio_transcription_backend == "aliyun_filetrans"
    assert settings.audio_transcription_timeout_seconds == 321.0
    assert settings.audio_transcription_poll_interval_seconds == 0.5
    assert settings.aliyun_ak_id == "aliyun-ak"
    assert settings.aliyun_ak_secret == "aliyun-sk"
    assert settings.aliyun_app_key == "aliyun-app-key"
    assert settings.aliyun_filetrans_region == "cn-shanghai"


def test_from_env_uses_audio_pipeline_defaults_when_env_is_missing(monkeypatch) -> None:
    monkeypatch.setattr(config_module, "_load_local_env_file", lambda _root_dir: None)
    _clear_audio_env(monkeypatch)

    settings = AppSettings.from_env()

    assert settings.qiniu_key_prefix == "audio"
    assert settings.audio_transcription_backend == "aliyun_filetrans"
    assert settings.audio_transcription_timeout_seconds == 300.0
    assert settings.audio_transcription_poll_interval_seconds == 2.0
    assert settings.aliyun_filetrans_region == "cn-shanghai"
