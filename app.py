import streamlit as st
import pandas as pd
import numpy as np
import requests
import io
import plotly.express as px
from difflib import get_close_matches

# ==========================================
# 1. MOTEUR D'INTELLIGENCE COLONNE (SYNONYMES)
# ==========================================
class SmartMapper:
    """Mappe les noms de colonnes du site vers nos noms internes"""
    REQUIRED_MAP = {
        'Ticker': ['Valeur', 'Titre', 'Action', 'Société', 'Ticker', 'Symbol', 'Nom'],
        'Prix': ['Dernier', 'Cours', 'Prix', 'Clôture', 'Price', 'Last', 'Clot'],
        'Change': ['Variation', 'Var%', 'Changement', 'Evolution', '%', 'Var'],
        'Volume': ['Volume', 'Quantité', 'Titres échangés', 'Vol.'],
        'PER': ['PER', 'P/E', 'Multiple'],
        'Yield': ['Rendement', 'Dividend Yield', 'Yield', 'Div %', 'Rend'],
        'BpA': ['BPA', 'EPS', 'Bénéfice par action']
    }

    @staticmethod
    def auto_fix_columns(df):
        current_columns = df.columns.tolist()
        new_mapping = {}
        for key, synonyms in SmartMapper.REQUIRED_MAP.items():
            for syn in synonyms:
                # On cherche une correspondance à 60% de similitude
                matches = get_close_matches(syn, current_columns, n=1, cutoff=0.6)
                if matches:
                    new_mapping[matches[0]] = key
                    break
        return df.rename(columns=new_mapping)

# ==========================================
# 2. COLLECTEUR DE DONNÉES (SCRAPER)
# ==========================================
class BRVMScraper:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
        }
        self.url_market = "https://www.sikafinance.com/marches/aaz"
        self.url_ratios = "https://www.sikafinance.com/marches/ratios"

    def fetch_all_tables(self, url):
        try:
            response = requests.get(url, headers=self.headers, timeout=15)
            if response.status_code != 200: return []
            return pd.read_html(io.StringIO(response.text))
        except:
            return []

    @st.cache_data(ttl=3600) # Garde les données en cache 1h
    def get_clean_data(_self):
        # 1. Récupération des deux sources
        tables_p = _self.fetch_all_tables(_self.url_market)
        tables_r = _self.fetch_all_tables(_self.url_ratios)

        if not tables_p: return None

        # 2. Sélection du tableau le plus grand (les actions, pas les indices)
        df_p = max(tables_p, key=len)
        df_p = SmartMapper.auto_fix_columns(df_p)

        # 3. Filtrage : Supprimer les indices sectoriels (BRVM - ...)
        if 'Ticker' in df_p.columns:
            df_p = df_p[~df_p['Ticker'].str.contains('BRVM|INDICE|Secteur|Composite', case=False, na=False)]

        # 4. Fusion avec les ratios (PER, Yield)
        if tables_r:
            df_r = max(tables_r, key=len)
            df_r = SmartMapper.auto_fix_columns(df_r)
            if 'Ticker' in df_r.columns:
                df_r = df_r[~df_r['Ticker'].str.contains('BRVM|INDICE', case=False, na=False)]
                cols_r = [c for c in ['Ticker', 'PER', 'Yield', 'BpA'] if c in df_r.columns]
                df_p = pd.merge(df_p, df_r[cols_r], on='Ticker', how='left')

        # 5. Sécurité : Initialisation des colonnes si absentes
        for col in ['Yield', 'PER', 'BpA', 'Prix', 'Change']:
            if col not in df_p.columns: df_p[col] = 0.0

        return _self.clean_numeric(df_p)

    def clean_numeric(self, df):
        for col in ['Prix', 'Yield', 'PER', 'BpA']:
            df[col] = df[col].astype(str).str.replace(r'[^\d.,-]', '', regex=True).str.replace(',', '.')
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
        return df

# ==========================================
# 3. ANALYSE ET SCORE (QUANT ENGINE)
# ==========================================
def run_analysis(df):
    # Calcul du Z-Score (Proxy basé sur Rentabilité et Dividende)
    # Plus le BpA est élevé par rapport au prix et le rendement est fort, plus le score monte
    df['Z_Score'] = ((df['BpA'] / df['Prix'].replace(0, 1)) * 100).clip(0, 20) + (df['Yield'] / 2)
    
    # Verdict Score (Note de 0 à 100)
    # Pondération : Dividende (40%) + Valorisation/PER (30%) + Santé/Z-Score (30%)
    df['Verdict_Score'] = (
        (df['Yield'].clip(0, 15) * 4) + 
        (25 / (df['PER'].replace(0, 20) + 1)).clip(0, 30) +
        (df['Z_Score'] * 1.5)
    ).clip(0, 100)
    
    return df

# ==========================================
# 4. INTERFACE UTILISATEUR (STREAMLIT)
# ==========================================
def main():
    st.set_page_config(page_title="BRVM Quant Pro", layout="wide")
    st.title("🤖 BRVM Strategic Quantitative Analyzer")
    st.markdown("Analyse en temps réel des actions de la BRVM basée sur les fondamentaux.")

    scraper = BRVMScraper()
    df = scraper.get_clean_data()

    if df is not None:
        df = run_analysis(df)
        
        # --- BLOC 1 : TOP 3 VERDICTS ---
        st.subheader("🏆 Verdict Final : Meilleures Opportunités")
        top_df = df.sort_values('Verdict_Score', ascending=False).head(3)
        t_cols = st.columns(3)
        for i, (idx, row) in enumerate(top_df.iterrows()):
            t_cols[i].success(f"**{i+1}. {row['Ticker']}**")
            t_cols[i].metric("Score", f"{row['Verdict_Score']:.1f}/100", f"Div: {row['Yield']}%")
            t_cols[i].caption(f"Prix: {int(row['Prix'])} FCFA | PER: {row['PER']:.1f}")

        # --- BLOC 2 : GRAPHIQUE ---
        st.subheader("📊 Visualisation Risque / Rendement")
        fig = px.scatter(df, x="PER", y="Yield", size="Prix", color="Verdict_Score",
                         hover_name="Ticker", labels={'Yield': 'Rendement (%)', 'PER': 'PER (Valorisation)'},
                         color_continuous_scale='RdYlGn', title="Positionnement des Actions")
        st.plotly_chart(fig, use_container_width=True)

        # --- BLOC 3 : TABLEAU DÉTAILLÉ ---
        st.subheader("🔍 Liste Complète des Analyses")
        # Formatage pour l'affichage
        display_df = df[['Ticker', 'Prix', 'BpA', 'PER', 'Yield', 'Z_Score', 'Verdict_Score']]
        display_df = display_df.sort_values('Verdict_Score', ascending=False)
        
        st.dataframe(display_df.style.background_gradient(subset=['Verdict_Score'], cmap='RdYlGn').format(precision=2))

        # --- BLOC 4 : ÉDUCATION ---
        with st.expander("📖 Comment interpréter ces résultats ?"):
            col_a, col_b = st.columns(2)
            col_a.markdown("""
            **1. Verdict Score (0-100)** : Note globale de l'action. 
            - > 70 : **Achat Fort**. L'action est rentable et pas chère.
            - 40-70 : **À Surveiller**. Bons fondamentaux mais prix élevé.
            - < 40 : **Prudence**. Rendement faible ou action surévaluée.
            
            **2. BpA (Bénéfice par Action)** : Ce que l'entreprise a réellement gagné par titre. C'est le moteur de la hausse du cours.
            """)
            col_b.markdown("""
            **3. Z-Score (Santé)** : Mesure de la solidité. Un score élevé indique une entreprise qui génère du profit sainement.
            
            **4. Yield (Rendement)** : Le pourcentage du prix reversé en cash. À la BRVM, un rendement > 8% est considéré comme excellent.
            """)
    else:
        st.error("Impossible de charger les données. Sika Finance bloque peut-être la requête. Réessayez dans 1 minute.")

if __name__ == "__main__":
    main()
