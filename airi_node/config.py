from pathlib import Path
from typing import Literal
import ipaddress
import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


class Settings(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    schema_version: Literal[1] = 1
    node_id: Literal['AIRI_PRIME', 'AIRI_WORKS']
    peer_id: Literal['AIRI_PRIME', 'AIRI_WORKS']
    bind: list[str] = Field(min_length=1)
    port: int = Field(default=8740, ge=1024, le=65535)
    peer_addresses: list[str]
    peer_loopback_port: int | None = Field(default=None,ge=1024,le=65535)
    secret_file: Path
    state_dir: Path
    ollama_url: Literal['http://127.0.0.1:11434'] = 'http://127.0.0.1:11434'
    heartbeat_seconds: float = Field(default=5, ge=1, le=5)
    request_timeout: float = Field(default=1, ge=.1, le=2)
    skew_seconds: int = Field(default=30, ge=1, le=30)
    nonce_seconds: int = Field(default=300, ge=300)
    read_limit: int = Field(default=60, ge=1)
    post_limit: int = Field(default=10, ge=1)
    discovery_enabled: bool = True
    network_refresh_seconds: int = Field(default=60, ge=5)
    reconnect_seconds: list[int] = [1, 2, 5, 10, 30]
    enabled_agents: list[str] = []
    stage_b: bool = False
    queue_enabled: bool = False
    ledger_path: Path | None = None
    redis_secret_file: Path | None = None
    redis_port: int = Field(default=6379,ge=1024,le=65535)
    queue_poll_seconds: float = Field(default=2,ge=1)
    worker_tick_seconds: float = Field(default=10,ge=10)
    reclaim_idle_ms: int = Field(default=120000,ge=120000)
    prime_concurrency: int = Field(default=4,ge=1,le=4)

    @field_validator('bind', 'peer_addresses')
    @classmethod
    def private_addresses(cls, values):
        for value in values:
            ip = ipaddress.ip_address(value)
            if ip.version != 4 or ip.is_unspecified or ip.is_multicast or not (ip.is_private or ip.is_link_local or ip.is_loopback):
                raise ValueError('Explicit private IPv4 addresses only')
        return list(dict.fromkeys(values))


def load(path):
    config = Settings.model_validate(yaml.safe_load(Path(path).read_text()))
    if config.node_id == config.peer_id:
        raise ValueError('Node and peer identities must differ')
    if config.queue_enabled and config.node_id=='AIRI_PRIME' and (not config.ledger_path or not config.redis_secret_file):
        raise ValueError('Primary queue needs the existing ledger and Redis secret paths')
    return config
