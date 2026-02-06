import re
from typing import Any, Dict, List

def _as_list(x: Any) -> List[str]:
    if x is None:
        return []
    if isinstance(x, list):
        return [str(i) for i in x]
    return [str(x)]

def _none_if_nullish(x: Any) -> Any:
    if x is None:
        return None
    if isinstance(x, str):
        s = x.strip()
        if s == "" or s.upper() == "NULL":
            return None
    return x

def _as_int(x: Any) -> int | None:
    x = _none_if_nullish(x)
    if x is None:
        return None
    if isinstance(x, bool):
        return int(x)
    if isinstance(x, (int, float)):
        return int(x)
    if isinstance(x, str):
        s = x.strip()
        if s == "":
            return None
        try:
            return int(s)
        except ValueError:
            return None
    return None

def _as_colors(x: Any) -> List[str]:
    """
    L'API/tes scrapes peuvent renvoyer:
    - ["Blue", "Purple"]
    - "Blue Purple"
    - "Blue/Purple" ou "Blue, Purple"
    """
    x = _none_if_nullish(x)
    if x is None:
        return []
    if isinstance(x, list):
        return [str(i).strip() for i in x if str(i).strip()]
    if isinstance(x, str):
        s = x.replace("/", " ").replace(",", " ")
        return [p for p in s.split() if p]
    return [str(x)]

def _normalize_set_id(x: Any) -> Any:
    x = _none_if_nullish(x)
    if not isinstance(x, str):
        return x
    s = x.strip()
    # "OP-01" -> "OP01"
    if re.match(r"^[A-Za-z]+-\d+$", s):
        return s.replace("-", "")
    return s

def normalize_card(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convertit une carte brute (API) -> format interne stable pour ton projet.
    On garde volontairement un sous-ensemble utile pour deckbuilding.
    """
    return {
        # Identifiants
        "card_id": (
            raw.get("card_set_id")
            or raw.get("cardId")
            or raw.get("id")
            or raw.get("card_id")
            or raw.get("card_image_id")
        ),
        "card_set_id": raw.get("card_set_id"),
        "card_image_id": raw.get("card_image_id"),

        # Libellés
        "name": raw.get("card_name") or raw.get("name"),
        "card_type": raw.get("card_type") or raw.get("type"),  # Leader/Character/Event/Stage
        "set_id": _normalize_set_id(raw.get("set_id") or raw.get("set") or raw.get("setId")),
        "set_name": raw.get("set_name"),
        "rarity": raw.get("rarity"),

        # Stats / méta
        "cost": _as_int(raw.get("card_cost") or raw.get("cost")),
        "power": _as_int(raw.get("card_power") or raw.get("power")),
        "counter": _as_int(raw.get("counter_amount") or raw.get("counter")),
        "colors": _as_colors(raw.get("card_color") or raw.get("color") or raw.get("colors")),
        "life": _as_int(raw.get("life")),
        "attribute": raw.get("attribute"),
        "traits": _as_list(raw.get("sub_types") or raw.get("trait") or raw.get("traits")),

        # Texte / image
        "text": _none_if_nullish(raw.get("card_text") or raw.get("effect") or raw.get("text")),
        "image_url": raw.get("card_image") or raw.get("image") or raw.get("images"),

        # Prix (si dispo dans le JSON scrappé)
        "market_price": raw.get("market_price"),
        "inventory_price": raw.get("inventory_price"),
        "date_scraped": raw.get("date_scraped"),
    }
