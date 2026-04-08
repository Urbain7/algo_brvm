import streamlit as st
import pandas as pd
import requests
import io
from difflib import get_close_matches
import plotly.express as px

# ==========================================
# 1. MOTEUR D'AUTO-AJUSTEMENT AMÉLIORÉ
# ==========================================
class SmartMapper:
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
                matches = get_close_matches(syn, current_columns, n=1, cutoff=0.6)
                if matches:
                    new_mapping[matches[0]] = key
                    break
        return df.rename(columns=new_mapping)

# ==========================================
# 2. SCRAPER AVEC SÉCURITÉ DE COLONNES
# ==========================================
class BRVMScraper:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
        }
        self.url_market = "https://www.sikafinance.com/marches/aaz"
        self.url_ratios = "https://www.sikafinance.com/marches/ratios"

    def fetch_table(self, url):
        try:
            response = requests.get(url, headers=self.headers, timeout=15)
            if response.status_code != 200:
                return None
            tables = pd.read_html(io.StringIO(response.text))
            return tables[0] if tables else None
        except Exception:
            return None

    def get_combined_data(self):
        df_p = self.fetch_table(self.url_market)
        df_r = self.fetch_table(self.url_ratios)

        if df_p is None:
            return None

        # Nettoyage Table 1 (Cours)
        df_p = SmartMapper.auto_fix_columns(df_p)
        
        # Nettoyage Table 2 (Ratios)
        if df_r is not None:
            df_r = SmartMapper.auto_fix_columns(df_r)
            if 'Ticker' in df_r.columns:
                # On ne garde que les colonnes nécessaires
                cols_to_keep = [c for c in ['Ticker', 'PER', 'Yield', 'BpA'] if c in df_r.columns]
                df_p = pd.merge(df_p, df_r[cols_r], on='Ticker', how='left')
        
        # --- SÉCURITÉ CRUCIALE : Initialisation des colonnes manquantes ---
        for col in ['Yield', 'PER', 'BpA', 'Prix', 'Change']:
            if col not in df_p.columns:
                df_p[col] = 0.0  # Crée la colonne si elle n'existe pas
        
        return self.clean_numeric(df_p)

    def clean_numeric(self, df):
        for col in ['Prix', 'Yield', 'PER', 'BpA']:
            df[col] = df[col].astype(str).str.replace(r'[^\d.,-]', '', regex=True).str.replace(',', '.')
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
        return df

# ==========================================
# 3. INTERFACE DE DÉCISION
# ==========================================
def main():
    st.set_page_config(page_title="BRVM AI Quant", layout="wide")
    st.title("🤖 BRVM Quantitative Analyzer")

    scraper = BRVMScraper()
    df = scraper.get_combined_data()

    if df is not None:
        # Calcul du Score avec sécurité (maintenant Yield et PER existent forcément)
        # On évite la division par zéro avec .replace(0, 1)
        df['Verdict_Score'] = (df['Yield'].clip(0, 15) * 4) + (20 / (df['PER'].replace(0, 20) + 1)).clip(0, 30)
        
        # Si tous les scores sont à zéro (données fondamentales HS)
        if df['Verdict_Score'].sum() == 0:
            st.warning("⚠️ Données fondamentales indisponibles. Le calcul du verdict est limité.")

        # Affichage Metrics
        st.subheader("📊 Résumé du Marché")
        top_df = df.sort_values('Verdict_Score', ascending=False).head(5)
        m_cols = st.columns(5)
        for i, (idx, row) in enumerate(top_df.iterrows()):
            m_cols[i].metric(row['Ticker'], f"{int(row['Prix'])} F", f"Score: {row['Verdict_Score']:.1f}")

        # Tableau
        st.subheader("🔍 Analyse des Valeurs")
        st.dataframe(df[['Ticker', 'Prix', 'PER', 'Yield', 'Verdict_Score']]
                     .sort_values('Verdict_Score', ascending=False)
                     .style.background_gradient(subset=['Verdict_Score'], cmap='RdYlGn'))

        # Graphique
        if df['Yield'].any():
            fig = px.scatter(df, x="PER", y="Yield", size="Prix", color="Ticker", title="Rendement vs PER")
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.error("❌ Erreur critique : Impossible de joindre le flux BRVM. Vérifiez votre connexion ou réessayez plus tard.")

if __name__ == "__main__":
    main()
