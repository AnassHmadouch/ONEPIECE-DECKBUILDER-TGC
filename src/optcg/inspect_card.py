from .client import OptcgClient
from .normalize import normalize_card

def main():
    card_id = "OP14-079"
    client = OptcgClient()
    raw = client.card_by_id(card_id)

    # parfois l’API renvoie directement la carte, parfois un wrapper
    card = raw
    if isinstance(raw, dict):
        for k in ("data", "card", "result"):
            if k in raw and isinstance(raw[k], dict):
                card = raw[k]
                break
    elif isinstance(raw, list):
        card = raw

    if isinstance(card, list):
        for c in card:
            if isinstance(c, dict):
                print(normalize_card(c))
    else:
        norm = normalize_card(card)
        print(norm)

if __name__ == "__main__":
    main()
