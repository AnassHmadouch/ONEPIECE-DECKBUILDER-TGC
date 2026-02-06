import argparse
from collections import Counter, defaultdict
from typing import Any, Dict, List, Tuple

import pandas as pd

from .client import OptcgClient
from .normalize import normalize_card

PLAYABLE_TYPES = {"character", "event", "stage"}

def unwrap_list(raw: Any) -> List[Dict[str, Any]]:
    if isinstance(raw, dict):
        for k in ("data", "cards", "results"):
            if k in raw and isinstance(raw[k], list):
                return raw[k]
    if isinstance(raw, list):
        return raw
    raise TypeError(f"Format inattendu pour une liste de cartes: {type(raw).__name__}")

def unwrap_card(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        for k in ("data", "card", "result"):
            if k in raw and isinstance(raw[k], dict):
                return raw[k]
        return raw
    if isinstance(raw, list) and raw and isinstance(raw[0], dict):
        # Certaines réponses peuvent être une liste (alt arts etc.)
        return raw[0]
    raise TypeError(f"Format inattendu pour une carte: {type(raw).__name__}")

def is_baroque(traits: List[str] | None) -> bool:
    t = " ".join(traits or []).lower()
    return "baroque works" in t

def score_crocodile_black(row: pd.Series, style: str) -> float:
    ctype = (row.get("card_type") or "").lower()
    text = str(row.get("text") or "").lower()    
    traits = " ".join((row.get("traits") or [])).lower()

    cost = row.get("cost")
    power = row.get("power")
    counter = row.get("counter")

    s = 0.0

    # Base par type
    if ctype == "character":
        s += 1.0
    elif ctype == "event":
        s += 0.7
    elif ctype == "stage":
        s += 0.4

    # Curve (noir control/mid)
    if isinstance(cost, int):
        if style == "control":
            s += (1.0 - abs(cost - 5) / 7.0) * 0.9
        elif style == "midrange":
            s += (1.0 - abs(cost - 4) / 6.0) * 0.9
        else:  # aggro
            s += max(0, 6 - cost) * 0.20

    # Counter utile pour tenir (surtout mid/control)
    if isinstance(counter, int):
        if style in ("control", "midrange"):
            s += min(counter, 2000) / 2000 * 0.85
        else:
            s += min(counter, 2000) / 2000 * 0.35

    # Synergie Baroque Works (bodies à sacrifier)
    if "baroque works" in traits:
        s += 1.1 if ctype == "character" else 0.2

    # Synergie noir: réduction de coût / KO (et KO by cost)
    if "cost" in text and "-" in text:
        s += 1.0
    if "k.o" in text or "ko" in text:
        s += 0.9
        if "cost" in text:
            s += 0.7

    # Trash: Croco en fait déjà (coût). On met faible bonus.
    if "trash" in text:
        s += 0.15

    # Power secondaire en control
    if isinstance(power, int) and style in ("midrange", "aggro"):
        s += min(power, 8000) / 8000 * 0.35

    return s

def build_deck(leader_id: str, style: str) -> Tuple[Dict[str, int], pd.DataFrame, Dict[str, Any]]:
    client = OptcgClient()

    leader_raw = client.card_by_id(leader_id)
    leader = normalize_card(unwrap_card(leader_raw))

    if (leader.get("card_type") or "").lower() != "leader":
        raise ValueError(f"{leader_id} n'est pas un Leader (card_type={leader.get('card_type')})")

    leader_colors = set(leader.get("colors") or [])
    if not leader_colors:
        raise ValueError(f"Couleurs introuvables pour le leader {leader_id}")

    all_raw = client.all_set_cards()
    cards_list = unwrap_list(all_raw)
    normalized = [normalize_card(c) for c in cards_list if isinstance(c, dict)]
    df = pd.DataFrame(normalized)

    # Pool compatible couleur + types jouables
    df["type_l"] = df["card_type"].fillna("").str.lower()
    df = df[df["type_l"].isin(PLAYABLE_TYPES)].copy()

    def compatible(colors):
        colors = set(colors or [])
        return len(colors.intersection(leader_colors)) > 0

    df = df[df["colors"].apply(compatible)].copy()
    df["is_baroque"] = df["traits"].apply(is_baroque)

    style = style.lower()
    if style not in ("aggro", "midrange", "control"):
        style = "control"

    # Scoring spécialisé Crocodile noir
    df["score"] = df.apply(lambda r: score_crocodile_black(r, style), axis=1)

    targets = {
        "aggro": {"character": 38, "event": 12, "stage": 0},
        "midrange": {"character": 36, "event": 12, "stage": 2},
        "control": {"character": 34, "event": 14, "stage": 2},
    }[style]

    deck: Dict[str, int] = defaultdict(int)

    def pick(type_name: str, n: int, extra_filter=None):
        sub = df[df["type_l"] == type_name]
        if extra_filter is not None:
            sub = sub[extra_filter(sub)]
        sub = sub.sort_values("score", ascending=False)

        for _, row in sub.iterrows():
            if n <= 0:
                break
            cid = row.get("card_id")
            if not cid:
                continue
            can_add = min(4 - deck[cid], n)
            if can_add > 0:
                deck[cid] += can_add
                n -= can_add

    # 1) On sécurise un minimum Baroque Works (bodies)
    min_baroque = 12
    pick("character", min_baroque, extra_filter=lambda s: s["is_baroque"] == True)

    # 2) Puis on remplit selon targets
    current_char = sum(deck.values())
    pick("character", max(0, targets["character"] - current_char))
    pick("event", targets["event"])
    pick("stage", targets["stage"])

    # 3) Compléter à 50 avec les meilleurs scores restants
    total = sum(deck.values())
    if total < 50:
        remaining = 50 - total
        sub = df.sort_values("score", ascending=False)
        for _, row in sub.iterrows():
            if remaining <= 0:
                break
            cid = row.get("card_id")
            if not cid:
                continue
            can_add = min(4 - deck[cid], remaining)
            if can_add > 0:
                deck[cid] += can_add
                remaining -= can_add

    deck_df = df[df["card_id"].isin(deck.keys())].copy()
    deck_df["qty"] = deck_df["card_id"].map(deck)

    return dict(deck), deck_df, leader

def summarize(deck_df: pd.DataFrame):
    curve = Counter()
    types = Counter()
    baroque_count = 0

    for _, r in deck_df.iterrows():
        q = int(r.get("qty", 0))
        types[r.get("type_l")] += q

        c = r.get("cost")
        curve[int(c) if isinstance(c, int) else -1] += q

        if bool(r.get("is_baroque")) and r.get("type_l") == "character":
            baroque_count += q

    return curve, types, baroque_count

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--leader", required=True)
    p.add_argument("--style", default="control", choices=["aggro", "midrange", "control"])
    args = p.parse_args()

    deck, deck_df, leader = build_deck(args.leader, args.style)
    curve, types, baroque_count = summarize(deck_df)

    print(f"Leader: {leader.get('name')} ({leader.get('card_id')}) colors={leader.get('colors')} life={leader.get('life')}")
    print(f"Deck size: {sum(deck.values())}")
    print(f"Baroque Works chars (copies): {baroque_count}\n")

    out = deck_df[
        ["qty", "card_id", "name", "card_type", "cost", "power", "counter", "colors", "set_id", "score", "is_baroque"]
    ].copy()
    out = out.sort_values(["qty", "score", "name"], ascending=[False, False, True])
    print(out.to_string(index=False))

    # Affichage curve ( -1 = cost inconnu )
    curve_sorted = dict(sorted(curve.items(), key=lambda x: x[0]))
    print("\nType counts:", dict(types))
    print("Curve:", curve_sorted)

if __name__ == "__main__":
    main()
