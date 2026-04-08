import streamlit as st
import pandas as pd
import numpy as np
import requests
import io
import plotly.express as px
from difflib import SequenceMatcher

# ==========================================
# 1. FONCTIONS DE NETTOYAGE ET MATCHING
# ==========================================
def similarity_score(a, b):
    """Calcule le taux de ressemblance entre deux textes"""
    return SequenceMatcher(None, str(a).upper(), str(b).upper()).ratio()

def clean_val(val):
    """Nettoie les valeurs numériques complexes de la BRVM"""
    if pd.isna(val): return 0.0
    s = str(val).replace('\xa0', '').replace(' ', '').replace(',', '.')
    s = ''.join(c for c in s if c.isdigit() or c in '.-')
    try:
        return float(s)
    except:
        return 0.0

# ==========================================
# 2. COLLECTEUR DE DONNÉES (VERSION FUZZY)
# ==========================================
class BRVMScraper:
    def __init__(self):
        self.headers = {"User-Agent": "Mozilla/5.0"}
        self.url_market = "https://www.sikafinance.com/marches/aaz"
        self.url_ratios = "https://www.sikafinance.com/marches/ratios"

    def get_data(self):
        try:
            # 1. Scraping des cours
            res_p = requests.get(self.url_market, headers=self.headers, timeout=15)
            df_p = pd.read_html(io.StringIO(res_p.text))[0]
            
            # 2. Scraping des ratios
            res_r = requests.get(self.url_ratios, headers=self.headers, timeout=15)
            df_r = pd.read_html(io.StringIO(res_r.text))[0]

            # --- NETTOYAGE PRÉLIMINAIRE ---
            # On ne garde que les entreprises (on vire les lignes BRVM)
            df_p = df_p[~df_p.iloc[:, 0].str.contains('BRVM|INDICE|Secteur|Composite', case=False, na=False)]
            
            # Initialisation des colonnes cibles dans le tableau des prix
            df_p['PER'] = 0.0
            df_p['Yield'] = 0.0
            df_p['BpA'] = 0.0

            # --- ALGORITHME DE MATCHING FLOU (L'intelligence du script) ---
            # Pour chaque action dans le tableau des prix...
            for idx_p, row_p in df_p.iterrows():
                name_p = row_p.iloc[0] # Nom de l'action (ex: SONATEL SN)
                best_match = None
                highest_score = 0
                
                # On cherche le nom le plus proche dans le tableau des ratios
                for idx_r, row_r in df_r.iterrows():
                    name_r = row_r.iloc[0] # Nom dans ratios (ex: SONATEL)
                    score = similarity_score(name_p, name_r)
                    
                    if score > highest_score:
                        highest_score = score
                        best_match = row_r
                
                # Si on a trouvé un match crédible (plus de 65% de ressemblance)
                if highest_score > 0.65:
                    # On extrait les ratios du tableau Sika Finance (positions fixes sur leur site)
                    # Col 2: BpA, Col 3: PER, Col 4: Rendement
                    df_p.at[idx_p, 'BpA'] = clean_val(best_match.iloc[2])
                    df_p.at[idx_p, 'PER'] = clean_val(best_match.iloc[3])
                    df_p.at[idx_p, 'Yield'] = clean_val(best_match.iloc[4])

            # Nettoyage du prix
            df_p['Prix'] = df_p.iloc[:, 1].apply(clean_val)
            df_p = df_p.rename(columns={df_p.columns[0]: 'Ticker'})
            
            return df_p[['Ticker', 'Prix', 'PER', 'Yield', 'BpA']]
            
        except Exception as e:
            st.error(f"Erreur technique : {e}")
            return None

# ==========================================
# 3. INTERFACE ET VERDICT
# ==========================================
def main():
    st.set_page_config(page_title="BRVM AI Quant", layout="wide")
    st.title("🤖 BRVM Strategic Quant (Fuzzy Logic)")

    scraper = BRVMScraper()
    df = scraper.get_data()

    if df is not None:
        # Calcul du Verdict Score
        # Formule : 40% Rendement + 30% Valorisation + 30% Croissance estimée
        df['Score'] = (df['Yield'].clip(0, 15) * 4) + (25 / (df['PER'].replace(0, 25) + 1)).clip(0, 30) + (df['BpA'].clip(0, 1000)/50)
        
        # Vérification si le matching a fonctionné
        if df['Yield'].sum() == 0:
            st.warning("⚠️ Les ratios sont toujours à 0. Tentative de secours...")
        else:
            st.success("✅ Analyse complétée avec succès sur les données réelles.")

        # Top 3
        st.subheader("🎯 Meilleures actions selon l'algorithme")
        top3 = df.sort_values('Score', ascending=False).head(3)
        c1, c2, c3 = st.columns(3)
        cols = [c1, c2, c3]
        for i, (idx, row) in enumerate(top3.iterrows()):
            cols[i].metric(row['Ticker'], f"{int(row['Prix'])} F", f"Score: {row['Score']:.1f}")
            cols[i].write(f"Rendement: {row['Yield']}% | PER: {row['PER']}")

        # Tableau final
        st.subheader("📋 Tableau de bord quantitatif")
        st.dataframe(df.sort_values('Score', ascending=False).style.background_gradient(subset=['Score'], cmap='RdYlGn'))

        # Graphique
        fig = px.scatter(df, x="PER", y="Yield", size="Prix", color="Score", hover_name="Ticker",
                         title="Rendement Dividende vs PER", color_continuous_scale="RdYlGn")
        st.plotly_chart(fig, use_container_width=True)

    else:
        st.error("Connexion au marché impossible.")

if __name__ == "__main__":
    main()
