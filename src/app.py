import streamlit as st
import pandas as pd

from optcg.client import OptcgClient
from optcg.normalize import normalize_card

st.set_page_config(page_title="One Piece TCG – Card Browser", layout="wide")

@st.cache_data(ttl=24 * 3600)
def load_cards() -> pd.DataFrame:
    client = OptcgClient()
    raw = client.all_set_cards()  # API + cache disque côté client :contentReference[oaicite:2]{index=2}

    # unwrap list (même logique que ton cli.py)
    cards_list = raw
    if isinstance(raw, dict):
        for k in ("data", "cards", "results"):
            if k in raw and isinstance(raw[k], list):
                cards_list = raw[k]
                break

    if not isinstance(cards_list, list):
        raise TypeError(f"Format inattendu pour all_set_cards: {type(cards_list).__name__}")

    norm = [normalize_card(c) for c in cards_list if isinstance(c, dict)]  # :contentReference[oaicite:3]{index=3}
    df = pd.DataFrame(norm)
    return df

def safe_str(x) -> str:
    return "" if x is None else str(x)

st.title("One Piece TCG – Card Browser (OPTCGAPI)")

df = load_cards()

# Sidebar filters
st.sidebar.header("Filtres")

q = st.sidebar.text_input("Recherche (nom / id / texte)", "")

card_type = st.sidebar.multiselect(
    "Type",
    options=sorted(df["card_type"].dropna().unique().tolist()),
    default=[]
)

colors = st.sidebar.multiselect(
    "Couleur",
    options=sorted({c for lst in df["colors"].dropna().tolist() for c in (lst if isinstance(lst, list) else [])}),
    default=[]
)

set_id = st.sidebar.multiselect(
    "Set",
    options=sorted(df["set_id"].dropna().unique().tolist()),
    default=[]
)

max_cost = st.sidebar.slider("Coût max (si dispo)", 0, 12, 12)

trait_query = st.sidebar.text_input("Trait contient (ex: Baroque Works)", "")

# Apply filters
filtered = df.copy()

if card_type:
    filtered = filtered[filtered["card_type"].isin(card_type)]

if colors:
    def has_any_color(lst):
        if not isinstance(lst, list):
            return False
        return any(c in lst for c in colors)
    filtered = filtered[filtered["colors"].apply(has_any_color)]

if set_id:
    filtered = filtered[filtered["set_id"].isin(set_id)]

# cost filter (None => on garde)
filtered = filtered[(filtered["cost"].isna()) | (filtered["cost"] <= max_cost)]

if trait_query.strip():
    tq = trait_query.strip().lower()
    def has_trait(lst):
        if not isinstance(lst, list):
            return False
        return tq in " ".join(lst).lower()
    filtered = filtered[filtered["traits"].apply(has_trait)]

if q.strip():
    qq = q.strip().lower()
    filtered = filtered[
        filtered["name"].fillna("").str.lower().str.contains(qq)
        | filtered["card_id"].fillna("").str.lower().str.contains(qq)
        | filtered["text"].fillna("").astype(str).str.lower().str.contains(qq)
    ]

st.caption(f"{len(filtered)} cartes affichées (sur {len(df)})")

# Gallery settings
cols = st.slider("Nombre de colonnes", 2, 8, 5)
limit = st.number_input("Limiter l’affichage (perf)", min_value=20, max_value=2000, value=200, step=20)

show = filtered.head(int(limit)).to_dict("records")

# Display as gallery
grid = st.columns(cols)

for i, card in enumerate(show):
    with grid[i % cols]:
        img = card.get("image_url")
        if img:
            st.image(img, width="stretch")
        st.markdown(f"**{safe_str(card.get('name'))}**")
        st.write(
            f"ID: {safe_str(card.get('card_id'))} | "
            f"Type: {safe_str(card.get('card_type'))} | "
            f"Cost: {safe_str(card.get('cost'))} | "
            f"Power: {safe_str(card.get('power'))}"
        )
        if st.toggle("Voir texte", key=f"t_{i}"):
            st.write(safe_str(card.get("text")))
