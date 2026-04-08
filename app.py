import streamlit as st
import pandas as pd
import numpy as np
import requests
import io
import plotly.express as px
from difflib import get_close_matches

# ==========================================
# 1. MOTEUR DE CORRESPONDANCE INTELLIGENTE
# ==========================================
class SmartMapper:
    REQUIRED_MAP = {
        'Ticker': ['Valeur', 'Titre', 'Action', 'Société', 'Ticker', 'Symbol', 'Nom'],
        'Prix': ['Dernier', 'Cours', 'Prix', 'Clôture', 'Price', 'Last', 'Clot'],
        'Change': ['Variation', 'Var%', 'Changement', 'Evolution', '%', 'Var'],
        'PER': ['PER', 'P/E', 'Multiple', 'Ratio'],
        'Yield': ['Rendement', 'Dividend Yield', 'Yield', 'Div %', 'Rend'],
        'BpA': ['BPA', 'EPS', 'Bénéfice par action', 'BpA']
    }

    @staticmethod
    def auto_fix_columns(df):
        current_columns = df.columns.tolist()
        new_mapping = {}
        for key, synonyms in SmartMapper.REQUIRED_MAP.items():
            for syn in synonyms:
                matches = get_close_matches(syn, current_columns, n=1, cutoff=0.6)
                if matches:
                    new_mapping[matches[0]] = key
                    break
        return df.rename(columns=new_mapping)

# ==========================================
# 2. SCRAPER AMÉLIORÉ (LOGIQUE DE FUSION)
# ==========================================
class BRVMScraper:
    def __init__(self):
        self.headers = {"User-Agent": "Mozilla/5.0"}
        self.url_market = "https://www.sikafinance.com/marches/aaz"
        self.url_ratios = "https://www.sikafinance.com/marches/ratios"

    def fetch_best_table(self, url):
        try:
            response = requests.get(url, headers=self.headers, timeout=15)
            tables = pd.read_html(io.StringIO(response.text))
            # On prend le tableau qui a le plus de colonnes (souvent le vrai tableau de données)
            return max(tables, key=lambda x: x.shape[1])
        except:
            return None

    @st.cache_data(ttl=3600)
    def get_combined_data(_self):
        df_p = _self.fetch_best_table(_self.url_market)
        df_r = _self.fetch_best_table(_self.url_ratios)

        if df_p is None: return None

        df_p = SmartMapper.auto_fix_columns(df_p)
        
        # --- NETTOYAGE DES NOMS POUR LA FUSION ---
        if 'Ticker' in df_p.columns:
            # On retire les indices et on nettoie les noms
            df_p = df_p[~df_p['Ticker'].str.contains('BRVM|INDICE|Secteur|Composite', case=False, na=False)]
            df_p['ID_Merge'] = df_p['Ticker'].str.lower().str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.strip()

        if df_r is not None:
            df_r = SmartMapper.auto_fix_columns(df_r)
            if 'Ticker' in df_r.columns:
                df_r['ID_Merge'] = df_r['Ticker'].str.lower().str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.strip()
                cols_r = [c for c in ['ID_Merge', 'PER', 'Yield', 'BpA'] if c in df_r.columns]
                # Fusion sur l'ID nettoyé
                df_p = pd.merge(df_p, df_r[cols_r], on='ID_Merge', how='left')

        # Initialisation si colonnes absentes
        for col in ['Yield', 'PER', 'BpA', 'Prix']:
            if col not in df_p.columns: df_p[col] = 0.0

        return _self.clean_numeric(df_p)

    def clean_numeric(self, df):
        for col in ['Prix', 'Yield', 'PER', 'BpA']:
            df[col] = df[col].astype(str).str.replace(r'[^\d.,-]', '', regex=True).str.replace(',', '.')
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
        return df

# ==========================================
# 3. CALCULS ET AFFICHAGE
# ==========================================
def main():
    st.set_page_config(page_title="BRVM Quant Pro", layout="wide")
    st.title("🤖 BRVM Strategic Analyzer")

    scraper = BRVMScraper()
    df = scraper.get_combined_data()

    if df is not None:
        # On calcule les scores (uniquement si les données sont là)
        # On évite la division par zéro
        df['Verdict_Score'] = (df['Yield'] * 3) + (25 / (df['PER'].replace(0, 30) + 1)) + (df['BpA'].clip(0, 1000) / 50)
        
        # Si après la fusion on a toujours des 0, on avertit l'utilisateur
        if df['Yield'].sum() == 0:
            st.error("⚠️ Les ratios n'ont pas pu être liés aux actions. Vérification du lien en cours...")

        # Top Picks
        st.subheader("🏆 Meilleures opportunités détectées")
        top_df = df.sort_values('Verdict_Score', ascending=False).head(5)
        cols = st.columns(5)
        for i, (idx, row) in enumerate(top_df.iterrows()):
            cols[i].metric(row['Ticker'], f"{int(row['Prix'])} F", f"Score: {row['Verdict_Score']:.1f}")

        # Tableau
        st.subheader("📋 Analyse détaillée")
        st.dataframe(df[['Ticker', 'Prix', 'PER', 'Yield', 'BpA', 'Verdict_Score']]
                     .sort_values('Verdict_Score', ascending=False))

        # Graphique
        fig = px.scatter(df, x="PER", y="Yield", size="Prix", color="Ticker", 
                         title="Rendement vs Valorisation (PER)")
        st.plotly_chart(fig, use_container_width=True)

    else:
        st.error("Impossible de récupérer les données.")

if __name__ == "__main__":
    main()
