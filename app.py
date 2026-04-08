import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import io
from difflib import get_close_matches
import plotly.express as px

# ==========================================
# 1. MOTEUR D'AUTO-AJUSTEMENT
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
# 2. SCRAPER RÉEL AVEC URLS MISES À JOUR
# ==========================================
class BRVMScraper:
    def __init__(self):
        # On utilise des headers qui imitent un vrai navigateur Chrome
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
        }
        # URLs de secours
        self.url_market = "https://www.sikafinance.com/marches/aaz" # Page "Actions de A à Z" (plus stable)
        self.url_ratios = "https://www.sikafinance.com/marches/ratios"

    def fetch_table(self, url):
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            if "Erreur d'affichage" in response.text or response.status_code != 200:
                return None
            
            # Utilisation de io.StringIO pour éviter l'erreur de fichier
            tables = pd.read_html(io.StringIO(response.text))
            return tables[0] if tables else None
        except Exception as e:
            st.error(f"Erreur sur {url}: {e}")
            return None

    def get_combined_data(self):
        df_p = self.fetch_table(self.url_market)
        df_r = self.fetch_table(self.url_ratios)

        if df_p is None:
            st.error("Impossible de récupérer les cours. Le site Sika Finance bloque peut-être la connexion.")
            return None

        # Nettoyage automatique
        df_p = SmartMapper.auto_fix_columns(df_p)
        
        if df_r is not None:
            df_r = SmartMapper.auto_fix_columns(df_r)
            # On garde seulement les colonnes utiles des ratios pour la fusion
            cols_r = [c for c in ['Ticker', 'PER', 'Yield', 'BpA'] if c in df_r.columns]
            df_final = pd.merge(df_p, df_r[cols_r], on='Ticker', how='left')
        else:
            df_final = df_p
            st.warning("Données fondamentales (ratios) indisponibles, analyse limitée aux cours.")

        return self.clean_numeric(df_final)

    def clean_numeric(self, df):
        for col in ['Prix', 'Yield', 'PER', 'BpA']:
            if col in df.columns:
                df[col] = df[col].astype(str).str.replace(r'[^\d.,-]', '', regex=True).str.replace(',', '.')
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        return df

# ==========================================
# 3. INTERFACE STREAMLIT
# ==========================================
def main():
    st.set_page_config(page_title="BRVM Quant Analyzer", layout="wide")
    st.title("🤖 BRVM Quantitative Analyzer")

    scraper = BRVMScraper()
    df = scraper.get_combined_data()

    if df is not None:
        # Calcul des scores
        df['Verdict_Score'] = (df['Yield'].clip(0, 15) * 4) + (20 / (df['PER'] + 1)).clip(0, 30)
        
        # Affichage
        st.subheader("🔥 Top 5 Opportunités (Score / 100)")
        top_df = df.sort_values('Verdict_Score', ascending=False).head(5)
        cols = st.columns(5)
        for i, (idx, row) in enumerate(top_df.iterrows()):
            cols[i].metric(row['Ticker'], f"{row['Prix']} FCFA", f"{row['Verdict_Score']:.1f} pts")

        st.subheader("Analyse Complète")
        st.dataframe(df.style.background_gradient(subset=['Verdict_Score'], cmap='RdYlGn'))

        # Graphique
        fig = px.scatter(df, x="PER", y="Yield", size="Prix", color="Ticker", title="Rendement vs PER")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Tentative de reconnexion au flux BRVM...")

if __name__ == "__main__":
    main()
