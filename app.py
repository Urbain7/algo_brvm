import streamlit as st
import pandas as pd
import requests
from difflib import get_close_matches

# ==========================================
# 1. MOTEUR D'AUTO-AJUSTEMENT (INTELLIGENT)
# ==========================================
class SmartMapper:
    """Ajuste automatiquement les noms de colonnes si le site change sa structure"""
    
    # Dictionnaire des synonymes probables pour chaque donnée nécessaire
    REQUIRED_MAP = {
        'Ticker': ['Valeur', 'Titre', 'Action', 'Société', 'Ticker', 'Symbol'],
        'Prix': ['Dernier', 'Cours', 'Prix', 'Clôture', 'Price', 'Last'],
        'Change': ['Variation', 'Var%', 'Changement', 'Evolution', '%'],
        'Volume': ['Volume', 'Quantité', 'Titres échangés', 'Vol.'],
        'PER': ['PER', 'P/E', 'Multiple', 'Ratio cours/bénéfice'],
        'Yield': ['Rendement', 'Dividend Yield', 'Yield', 'Div %'],
        'BpA': ['BPA', 'EPS', 'Bénéfice par action', 'Earnings per share']
    }

    @staticmethod
    def auto_fix_columns(df, section_name=""):
        current_columns = df.columns.tolist()
        new_mapping = {}
        
        for key, synonyms in SmartMapper.REQUIRED_MAP.items():
            # On cherche si un synonyme existe exactement dans les colonnes du site
            match = None
            for syn in synonyms:
                matches = get_close_matches(syn, current_columns, n=1, cutoff=0.7)
                if matches:
                    match = matches[0]
                    break
            
            if match:
                new_mapping[match] = key
        
        st.write(f"🔍 Analyse auto ({section_name}) : {len(new_mapping)} colonnes identifiées.")
        return df.rename(columns=new_mapping)

# ==========================================
# 2. SCRAPER AMÉLIORÉ AVEC AUTO-FIX
# ==========================================
class BRVMScraper:
    def __init__(self):
        self.headers = {"User-Agent": "Mozilla/5.0"}
        self.url_perf = "https://www.sikafinance.com/marches/performances"
        self.url_ratios = "https://www.sikafinance.com/marches/ratios"

    def get_data(self):
        try:
            # 1. Récupérer les performances
            res_p = requests.get(self.url_perf, headers=self.headers)
            df_perf = pd.read_html(res_p.text)[0]
            # Ajustement automatique
            df_perf = SmartMapper.auto_fix_columns(df_perf, "Marché")

            # 2. Récupérer les ratios
            res_r = requests.get(self.url_ratios, headers=self.headers)
            df_ratios = pd.read_html(res_r.text)[0]
            # Ajustement automatique
            df_ratios = SmartMapper.auto_fix_columns(df_ratios, "Fondamentaux")

            # Fusion intelligente sur la colonne 'Ticker' auto-identifiée
            if 'Ticker' in df_perf.columns and 'Ticker' in df_ratios.columns:
                df_final = pd.merge(df_perf, df_ratios, on='Ticker', how='inner')
                return self.clean_data(df_final)
            else:
                st.error("Impossible de trouver la colonne 'Ticker' malgré l'auto-ajustement.")
                return None
        except Exception as e:
            st.error(f"Erreur de scraping : {e}")
            return None

    def clean_data(self, df):
        # Nettoyage robuste des données numériques
        cols_to_fix = ['Prix', 'Yield', 'PER', 'BpA']
        for col in cols_to_fix:
            if col in df.columns:
                df[col] = df[col].astype(str).str.replace(r'[^\d.,-]', '', regex=True)
                df[col] = df[col].str.replace(',', '.')
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        return df

# ==========================================
# 3. ANALYSE ET VERDICT (LE "CERVEAU")
# ==========================================
def run_analysis(df):
    # Calcul du Z-Score (Modèle simplifié pour la démo)
    # Dans un vrai modèle, on ajouterait les dettes
    df['Z_Score'] = (df['BpA'] / df['Prix'].replace(0,1)) * 10 + (df['Yield'] / 2)
    
    # Calcul du Verdict Score (Note sur 100)
    # Formule : 40% Yield + 30% Valorisation (PER) + 30% Croissance
    df['Verdict_Score'] = (
        (df['Yield'].clip(0, 15) * 4) + 
        ((20 / (df['PER'] + 1)).clip(0, 30)) + 
        (df['Z_Score'].clip(0, 30))
    )
    return df

# ==========================================
# 4. DASHBOARD FINAL
# ==========================================
def main():
    st.set_page_config(page_title="BRVM AI Quant", layout="wide")
    st.title("🤖 BRVM Self-Adjusting Analyzer")

    scraper = BRVMScraper()
    df_raw = scraper.get_data()

    if df_raw is not None:
        df = run_analysis(df_raw)
        
        # --- Affichage des Tops ---
        top_cols = st.columns(3)
        best = df.sort_values('Verdict_Score', ascending=False).iloc[0]
        top_cols[0].success(f"🔥 MEILLEUR CHOIX : {best['Ticker']}")
        top_cols[0].write(f"Score : {best['Verdict_Score']:.1f}/100")
        
        cheap = df[df['PER'] > 0].sort_values('PER').iloc[0]
        top_cols[1].info(f"💎 SOUS-ÉVALUÉE : {cheap['Ticker']}")
        top_cols[1].write(f"PER : {cheap['PER']:.1f}")

        safe = df.sort_values('Z_Score', ascending=False).iloc[0]
        top_cols[2].warning(f"🛡️ PLUS SOLIDE : {safe['Ticker']}")
        top_cols[2].write(f"Z-Score : {safe['Z_Score']:.1f}")

        # --- Visualisation ---
        import plotly.express as px
        st.subheader("Visualisation du Marché")
        fig = px.scatter(df, x="PER", y="Yield", size="Verdict_Score", color="Ticker",
                         title="Rapport Prix (PER) / Rendement (Yield)",
                         labels={'Yield': 'Rendement (%)', 'PER': 'Multiple de valorisation'})
        st.plotly_chart(fig, use_container_width=True)

        # --- Tableau Final ---
        st.subheader("Détails de l'analyse quantitative")
        st.dataframe(df[['Ticker', 'Prix', 'PER', 'Yield', 'BpA', 'Z_Score', 'Verdict_Score']]
                     .sort_values('Verdict_Score', ascending=False)
                     .style.background_gradient(subset=['Verdict_Score'], cmap='RdYlGn'))

if __name__ == "__main__":
    main()
