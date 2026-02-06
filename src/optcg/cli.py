from .client import OptcgClient
from .normalize import normalize_card

def _s(x) -> str:
    return "" if x is None else str(x)

def _format_colors(x) -> str:
    if x is None:
        return ""
    if isinstance(x, list):
        return " ".join(str(i) for i in x if str(i))
    return str(x)

def list_leaders() -> None:
    client = OptcgClient()
    raw_cards = client.all_set_cards()

    # selon l’API, la liste peut être directe ou encapsulée
    cards_list = raw_cards
    if isinstance(raw_cards, dict):
        # fallback: si l'API renvoie un objet avec une clé
        for k in ("data", "cards", "results"):
            if k in raw_cards and isinstance(raw_cards[k], list):
                cards_list = raw_cards[k]
                break

    if not isinstance(cards_list, list):
        raise TypeError(f"Format inattendu pour allSetCards: {type(cards_list).__name__}")

    leaders_by_id: dict[str, dict] = {}
    for raw in cards_list:
        if not isinstance(raw, dict):
            continue
        card = normalize_card(raw)
        card_type = _s(card.get("card_type")).strip().lower()
        if card_type != "leader":
            continue

        card_id = _s(card.get("card_id")).strip()
        name = _s(card.get("name")).strip()
        if not card_id or not name:
            continue

        leaders_by_id.setdefault(card_id, card)

    leaders = sorted(
        leaders_by_id.values(),
        key=lambda c: (_s(c.get("set_id")), _s(c.get("name"))),
    )

    print(f"Leaders trouvés: {len(leaders)}")
    if not leaders:
        return

    rows = [
        {
            "card_id": _s(c.get("card_id")),
            "name": _s(c.get("name")),
            "colors": _format_colors(c.get("colors")),
            "life": _s(c.get("life")),
            "set_id": _s(c.get("set_id")),
        }
        for c in leaders
    ]

    cols = ["card_id", "name", "colors", "life", "set_id"]
    widths = {
        col: max(len(col), max(len(_s(r.get(col))) for r in rows))
        for col in cols
    }

    print(" ".join(col.ljust(widths[col]) for col in cols))
    print(" ".join(("-" * widths[col]) for col in cols))
    for r in rows:
        print(" ".join(_s(r.get(col)).ljust(widths[col]) for col in cols))

if __name__ == "__main__":
    list_leaders()
