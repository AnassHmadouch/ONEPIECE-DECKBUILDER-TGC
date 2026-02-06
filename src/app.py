import streamlit as st
import pandas as pd
from pathlib import Path

from optcg.client import OptcgClient
from optcg.normalize import normalize_card
from optcg.deckbuild_core import build_deck_for_leader
from optcg.errors import DeckBuilderError

ASSETS_DIR = Path(__file__).parent / "assets"
FALLBACK_IMG = ASSETS_DIR / "DON!!_blackbeard.png"

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
tab1, tab2 = st.tabs(["🃏 Card Browser", "🏗️ Deck Builder"])

with tab1:
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

    grid = st.columns(cols)

    for i, card in enumerate(show):
        with grid[i % cols]:
            img = card.get("image_url")
            if img:
                st.image(img, width="stretch")
            else:
                st.image(str(FALLBACK_IMG), width="stretch")

            st.markdown(f"**{safe_str(card.get('name'))}**")
            st.write(
                f"ID: {safe_str(card.get('card_id'))} | "
                f"Type: {safe_str(card.get('card_type'))} | "
                f"Cost: {safe_str(card.get('cost'))} | "
                f"Power: {safe_str(card.get('power'))}"
            )
            if st.toggle("Voir texte", key=f"t_{i}"):
                st.write(safe_str(card.get("text")))

with tab2:
    st.subheader("Deck Builder (V1)")

    leader_id = st.text_input("Leader ID", value="", placeholder="Ex: OP14-079", key="leader_id_input")
    style = st.selectbox("Style", ["control", "midrange", "aggro"], index=0, key="style_select")

    if st.button("Générer le deck", key="build_btn"):
        try:
            leader_id_clean = (leader_id or "").strip().upper()
            # Optionnel: validation UI directe (évite même d’aller dans le backend)
            if not leader_id_clean:
                st.error("Leader ID manquant. Exemple : OP14-079")
                st.stop()

            with st.spinner("Génération du deck..."):
                deck_df, leader = build_deck_for_leader(leader_id_clean, style)

        except DeckBuilderError as e:
            # 👉 ERREUR “PROPRE” sans traceback
            st.error(str(e))
            st.stop()

        except Exception as e:
            # 👉 fallback (pas de crash)
            st.error("Erreur inattendue pendant la génération du deck.")
            with st.expander("Détails (debug)"):
                st.exception(e)  # tu peux aussi enlever ce bloc si tu ne veux aucun détail
            st.stop()

        # ✅ Si on arrive ici, tout va bien
        st.success(f"Deck généré pour {leader.get('name')} ({leader.get('card_id')})")

        deck_lines = [f"{int(r['qty'])}x {r['card_id']} - {r['name']}" for _, r in deck_df.iterrows()]
        deck_text = "\n".join(deck_lines)

        st.download_button(
            "Télécharger decklist (.txt)",
            data=deck_text,
            file_name=f"deck_{leader_id_clean}_{style}.txt",
            mime="text/plain",
        )
        st.divider()
        st.subheader("Cartes du deck")

        deck_cols = st.slider("Colonnes (deck)", 2, 8, 5, key="deck_cols")
        grid = st.columns(deck_cols)

        cards = deck_df.to_dict("records")
        for i, card in enumerate(cards):
            with grid[i % deck_cols]:
                img = card.get("image_url")
                if img:
                    st.image(img, width="stretch")
                else:
                    st.image(str(FALLBACK_IMG), width="stretch")


                st.markdown(f"**{int(card.get('qty', 0))}x {safe_str(card.get('name'))}**")
                st.caption(
                    f"{safe_str(card.get('card_id'))} | "
                    f"{safe_str(card.get('card_type'))} | "
                    f"cost={safe_str(card.get('cost'))}"
                )

                if st.toggle("Voir texte", key=f"deck_text_{i}"):
                    st.write(safe_str(card.get("text")))
