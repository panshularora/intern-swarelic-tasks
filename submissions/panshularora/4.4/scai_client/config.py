"""Client configuration + validation."""
from dataclasses import dataclass


@dataclass
class SCAIClientConfig:
    base_url: str
    username: str
    password: str
    timeout: int = 30
    max_retries: int = 3
    verify_ssl: bool = True

    def __post_init__(self):
        if not isinstance(self.base_url, str) or not (
            self.base_url.startswith('http://') or self.base_url.startswith('https://')
        ):
            raise ValueError("base_url must start with http:// or https://")
        if not isinstance(self.timeout, (int, float)) or self.timeout <= 0:
            raise ValueError("timeout must be greater than 0")
        if not self.username:
            raise ValueError("username must be a non-empty string")
        if not self.password:
            raise ValueError("password must be a non-empty string")
        self.base_url = self.base_url.rstrip('/')
