from collections import defaultdict
from typing import Any, Dict, List, Tuple
from optcg.errors import InvalidLeaderIdError, LeaderNotFoundError, ApiUnavailableError
import re

import pandas as pd

from optcg.client import OptcgClient
from optcg.normalize import normalize_card

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
        return raw[0]
    raise TypeError(f"Format inattendu pour une carte: {type(raw).__name__}")

def is_baroque(traits) -> bool:
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

    if ctype == "character":
        s += 1.0
    elif ctype == "event":
        s += 0.7
    elif ctype == "stage":
        s += 0.4

    if isinstance(cost, int):
        if style == "control":
            s += (1.0 - abs(cost - 5) / 7.0) * 0.9
        elif style == "midrange":
            s += (1.0 - abs(cost - 4) / 6.0) * 0.9
        else:
            s += max(0, 6 - cost) * 0.20

    if isinstance(counter, int):
        if style in ("control", "midrange"):
            s += min(counter, 2000) / 2000 * 0.85
        else:
            s += min(counter, 2000) / 2000 * 0.35

    if "baroque works" in traits:
        s += 1.1 if ctype == "character" else 0.2

    if "cost" in text and "-" in text:
        s += 1.0
    if "k.o" in text or "ko" in text:
        s += 0.9
        if "cost" in text:
            s += 0.7

    if "trash" in text:
        s += 0.15

    if isinstance(power, int) and style in ("midrange", "aggro"):
        s += min(power, 8000) / 8000 * 0.35

    return s

def build_deck_for_leader(leader_id: str, style: str = "control") -> Tuple[pd.DataFrame, Dict[str, Any]]:
    if not leader_id or not leader_id.strip():
        raise InvalidLeaderIdError("Leader ID manquant. Exemple : OP14-079")

    leader_id = leader_id.strip().upper()
    if not re.match(r"^OP\d{2}-\d{3}$", leader_id):
        raise InvalidLeaderIdError("Leader ID invalide. Format : OPxx-xxx (ex: OP14-079)")

    client = OptcgClient()

    try:
        leader_raw = client.card_by_id(leader_id)
    except RuntimeError as e:
        # typiquement: API call failed after retries
        raise ApiUnavailableError("API indisponible ou Leader ID introuvable.") from e

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
    
    # 1) Nettoyage: éviter que les Alt Art / Reprint biaisent le scoring
    # On garde 1 seule ligne par card_id (la "meilleure" selon quelques critères)
    df = df[df["card_id"].notna()].copy()
    df["name_l"] = df["name"].fillna("").astype(str).str.lower()

    # score de "qualité d'édition" : normal > reprint > alternate art
    def print_rank(name_l: str) -> int:
        if "alternate art" in name_l:
            return 0
        if "reprint" in name_l:
            return 1
        return 2

    df["print_rank"] = df["name_l"].apply(print_rank)

    # bonus: on préfère une image_url non vide
    df["has_img"] = df["image_url"].notna().astype(int)

    # tri pour garder la meilleure ligne par card_id
    df = df.sort_values(
        ["card_id", "print_rank", "has_img"],
        ascending=[True, False, False]
    )

    df = df.drop_duplicates(subset=["card_id"], keep="first").copy()

    # nettoyage
    df = df.drop(columns=["name_l", "print_rank", "has_img"], errors="ignore")

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

    # Pour l’instant, on applique le scoring Crocodile noir uniquement
    # (on généralisera ensuite par leader/couleur)
    df["score"] = df.apply(lambda r: score_crocodile_black(r, style), axis=1)

    targets = {
        "aggro": {"character": 38, "event": 12, "stage": 0},
        "midrange": {"character": 36, "event": 12, "stage": 2},
        "control": {"character": 34, "event": 14, "stage": 2},
    }[style]

    deck = defaultdict(int)

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

    # Forcer Baroque Works si le leader est Crocodile OP14-079 (V1 hardcodée)
    if leader_id == "OP14-079":
        pick("character", 12, extra_filter=lambda s: s["is_baroque"] == True)

    current_char = sum(deck.values())
    pick("character", max(0, targets["character"] - current_char))
    pick("event", targets["event"])
    pick("stage", targets["stage"])

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

    # tri pour affichage
    deck_df = deck_df.sort_values(["qty", "score", "name"], ascending=[False, False, True])
    return deck_df, leader
