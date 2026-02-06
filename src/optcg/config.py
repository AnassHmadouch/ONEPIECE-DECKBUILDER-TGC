from dataclasses import dataclass
import os
from pathlib import Path

@dataclass(frozen=True)
class OptcgConfig:
    base_url: str = os.getenv("OPTCG_API_BASE_URL", "https://optcgapi.com")
    cache_dir: Path = Path(os.getenv("OPTCG_CACHE_DIR", ".cache_optcg"))
    ttl_seconds: int = int(os.getenv("OPTCG_CACHE_TTL", str(24 * 3600)))  # 24h

    def __post_init__(self):
        self.cache_dir.mkdir(parents=True, exist_ok=True)