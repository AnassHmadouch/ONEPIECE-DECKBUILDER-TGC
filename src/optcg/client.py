import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import requests

from .config import OptcgConfig

@dataclass
class OptcgClient:
    cfg: OptcgConfig = OptcgConfig()

    def _cache_path(self, key: str) -> Path:
        safe = (
            key.replace("/", "_")
               .replace("?", "_")
               .replace("&", "_")
               .replace("=", "_")
               .replace(":", "_")
        )
        return self.cfg.cache_dir / f"{safe}.json"

    def _get_json(self, url: str, cache_key: str) -> Any:
        path = self._cache_path(cache_key)

        if path.exists():
            age = time.time() - path.stat().st_mtime
            if age < self.cfg.ttl_seconds:
                return json.loads(path.read_text(encoding="utf-8"))

        last_err: Optional[Exception] = None
        for attempt in range(3):
            try:
                r = requests.get(url, timeout=25)
                r.raise_for_status()
                data = r.json()
                path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                return data
            except Exception as e:
                last_err = e
                time.sleep(1 + attempt)

        raise RuntimeError(f"API call failed after retries: {url}") from last_err

    def all_set_cards(self) -> Any:
        # Doc: /api/allSetCards/ :contentReference[oaicite:1]{index=1}
        url = f"{self.cfg.base_url}/api/allSetCards/"
        return self._get_json(url, "allSetCards")

    def card_by_id(self, card_id: str) -> Any:
        # Doc: /api/sets/card/{card_id}/ :contentReference[oaicite:2]{index=2}
        url = f"{self.cfg.base_url}/api/sets/card/{card_id}/"
        return self._get_json(url, f"card_{card_id}")
