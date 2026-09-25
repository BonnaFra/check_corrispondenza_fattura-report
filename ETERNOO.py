import pdfplumber
import pandas as pd
import re
import os
import shutil
import tkinter as tk
from tkinter import messagebox
from datetime import datetime
import sys

# ==============================================================================
# 1. FUNZIONI DI UTILITÀ GLOBALI
# ==============================================================================

def pulisci_numero(valore_str):
    if not isinstance(valore_str, str): return valore_str
    v = str(valore_str).replace('\n', '').strip()
    if not v: return 0.0
    if ',' in v:
        v = v.replace('.', '').replace(',', '.')
    try: return float(v)
    except ValueError: return 0.0

def evidenzia_discrepanze(row):
    stile_base = [''] * len(row)
    rosso_sfumato = 'background-color: #FADBD8;'
    giallo_warning = 'background-color: #FFF2CC;'
    
    if pd.isna(row['Qta_Report']):
        return [giallo_warning] * len(row)
        
    if row['Qta_Fattura'] != row['Qta_Report']:
        stile_base[row.index.get_loc('Qta_Fattura')] = rosso_sfumato
        stile_base[row.index.get_loc('Qta_Report')] = rosso_sfumato
    if row['Prezzo_Unit_Fattura'] != row['Prezzo_Unit_Report']:
        stile_base[row.index.get_loc('Prezzo_Unit_Fattura')] = rosso_sfumato
        stile_base[row.index.get_loc('Prezzo_Unit_Report')] = rosso_sfumato
    if row['UM_Fattura'] != row['UM_Report']:
        stile_base[row.index.get_loc('UM_Fattura')] = rosso_sfumato
        stile_base[row.index.get_loc('UM_Report')] = rosso_sfumato
    if row['Totale_Fattura'] != row['Totale_Report']:
        stile_base[row.index.get_loc('Totale_Fattura')] = rosso_sfumato
        stile_base[row.index.get_loc('Totale_Report')] = rosso_sfumato

    return stile_base

# ==============================================================================
# 2. ESTRATTORE STANDARD: REPORT MANAGER (AGGIORNATO CON LETTURA LINEARE)
# ==============================================================================

def estrai_report(pdf_path):
    dati_estratti = []
    
    # REGEX MASTER PER IL REPORT ETERNOO
    # Cattura in modo infallibile la sequenza dati a prescindere dai salti pagina.
    # REGEX AGGIORNATA: Ora accetta il punto "." nel gruppo del codice articolo (gruppo 3)
    pattern_riga = r'^(?:M|E)?\s*(\d{3,8})\s+(?:M|E)?\s*(\d{2}/\d{2}/\d{4})\s+([a-zA-Z0-9\.]+)\s+(.*?)\s+([\d\,\.]+)\s+([a-zA-Z0-9\.]{1,4})\s+([\d\,\.]+)\s+([\d\,\.]+)(?:\s+[\d\,\.]+)?[\s\*]*$'
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                # Layout=True ci permette di avere gli spazi reali tra le colonne
                testo_pagina = page.extract_text(layout=True)
                if not testo_pagina: continue
                
                righe = testo_pagina.split('\n')
                for line in righe:
                    # Pulizia preventiva per artefatti grafici
                    line = line.replace('|', '').strip()
                    if not line: continue
                    
                    # Il motore Regex aggancia direttamente la "firma" della riga dati
                    match = re.search(pattern_riga, line)
                    
                    if match:
                        ddt_greggio = match.group(1).strip()
                        data = match.group(2).strip()
                        codice = match.group(3).strip()

                        if codice.endswith('.1'):
                            codice = codice[:-2]  # Rimuove il ".1" finale se presente

                        descrizione = match.group(4).strip()
                        
                        # Parsing numerico
                        prezzo_unit = pulisci_numero(match.group(5))
                        quantita = pulisci_numero(match.group(7))
                        totale = pulisci_numero(match.group(8))
                        
                        # Normalizzazione Unità di Misura
                        um = match.group(6).upper().replace('.', '').strip()
                        if um in ["N", "PZ"]: um = "NR"
                        
                        dati_estratti.append({
                            'DDT': str(int(ddt_greggio)),
                            'Data_Report': data,
                            'Codice': codice,
                            'Descrizione_Report': descrizione,
                            'Qta_Report': quantita,
                            'Prezzo_Unit_Report': prezzo_unit,
                            'UM_Report': um,
                            'Totale_Report': totale
                        })
                        
    except Exception as e:
        print(f"Errore estrazione report ({pdf_path}): {e}")
        return pd.DataFrame()  # Ritorna un DataFrame vuoto in caso di errore
    
    return pd.DataFrame(dati_estratti)

# ==============================================================================
# 3. ESTRATTORE SPECIFICO: FATTURA FORNITORE (DA PERSONALIZZARE)
# ==============================================================================

def estrai_fattura_fornitore(pdf_path):
    """
    MODULO ESTRAZIONE: ETERNOO S.P.A.
    Questa funzione sostituisce il placeholder nel 'main_template.py'.
    Usa un'estrazione lineare e regex specifiche per il layout di Eternoo.
    """
    dati_estratti = []
    current_ddt = None
    current_data = None
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                # Manteniamo il layout True per preservare gli spazi
                testo_pagina = page.extract_text(layout=True) 
                if not testo_pagina: continue
                
                righe = testo_pagina.split('\n')
                for line in righe:
                    line = line.strip()
                    if not line: continue
                    
                    # 1. CERCA DDT
                    # Es: "DDT BL/VEN/0005514 del 31-03-2026"
                    match_ddt = re.search(r'DDT.*?/0*(\d+)\s+del\s+(\d{2}-\d{2}-\d{4})', line, re.IGNORECASE)
                    if match_ddt:
                        current_ddt = match_ddt.group(1) # Estrae il numero pulito senza zeri
                        current_data = match_ddt.group(2).replace('-', '/')
                        continue 
                    
                    # 2. CERCA ARTICOLO
                    # Es: "05508491 (ARTCLI) MISTINO 0/13 1,80 28,705 TN 22,00 51,67"
                    pattern_articolo = r'^(\d{6,})\s*\(ARTCLI\)\s+(.*?)\s+([\d\,\.]+)\s+([\d\,\.]+)\s+([A-Za-z]+)\s+([\d\,\.]+)\s+([\d\,\.]+)$'
                    match_art = re.match(pattern_articolo, line)
                    
                    if match_art and current_ddt:
                        codice = match_art.group(1).strip()
                        descrizione = match_art.group(2).strip()
                        qta = pulisci_numero(match_art.group(3))
                        prezzo_u = pulisci_numero(match_art.group(4))
                        
                        # Normalizzazione Unità di Misura (come da direttive Master)
                        um = match_art.group(5).strip().upper()
                        if um in ["N", "PZ", "N."]: 
                            um = "NR"
                            
                        totale = pulisci_numero(match_art.group(7))
                        
                        dati_estratti.append({
                            'DDT': current_ddt,
                            'Data_Fattura': current_data,
                            'Codice': codice,
                            'Descrizione_Fattura': descrizione,
                            'Qta_Fattura': qta,
                            'Prezzo_Unit_Fattura': prezzo_u,
                            'UM_Fattura': um,
                            'Totale_Fattura': totale
                        })
    except Exception as e:
         print(f"Errore estrazione fattura {pdf_path}: {e}")
         
    return pd.DataFrame(dati_estratti)

# ==============================================================================
# 4. WORKFLOW MANAGER E CORE ENGINE
# ==============================================================================

def avvia_elaborazione():
    root = tk.Tk()
    root.withdraw()
    
    if getattr(sys, 'frozen', False):
        # Se il programma sta girando come file .exe compilato
        base_dir = os.path.dirname(sys.executable)
    else:
        # Se il programma sta girando come normale script .py
        base_dir = os.path.dirname(os.path.abspath(__file__))
        
    loading_dir = os.path.join(base_dir, "Files loader")
    
    # Crea cartella Files loader se non esiste
    if not os.path.exists(loading_dir):
        os.makedirs(loading_dir)
        messagebox.showinfo("Setup", f"Ho creato la cartella 'Files loader' in:\n{base_dir}\n\nInserisci lì dentro il Report e la Fattura e riavvia il programma.")
        return

    # Trova i PDF in Files loader
    pdf_files = [f for f in os.listdir(loading_dir) if f.lower().endswith('.pdf')]
    
    if len(pdf_files) != 2:
        messagebox.showwarning("Errore File", f"Nella cartella 'Files loader' ci devono essere ESATTAMENTE 2 file PDF (Fattura e Report).\nAttualmente ce ne sono {len(pdf_files)}.")
        return

    # Riconoscimento automatico dei file (Report vs Fattura) leggendo il nome del file
    file_report = None
    file_fattura = None
    
    for file in pdf_files:
        nome_lower = file.lower()
        percorso = os.path.join(loading_dir, file)
        if "fattura" in nome_lower:
            file_fattura = percorso
        elif "report" in nome_lower:
            file_report = percorso

    if not file_report or not file_fattura:
        messagebox.showerror("Errore Riconoscimento", "Non sono riuscito a distinguere il Report dalla Fattura. Assicurati che i nomi dei file contengano le parole 'Fattura' e 'Report'.")
        return

    # Estrazione Dati
    df_report = estrai_report(file_report)
    df_fattura = estrai_fattura_fornitore(file_fattura)

    if df_report.empty or df_fattura.empty:
        messagebox.showwarning("Dati Mancanti", "Uno dei due documenti non contiene dati validi o l'estrazione è fallita.")
        return

    # --- FIX PUNTO 1: DIZIONARIO CODICI STORPIATI (Data Entry Errato) ---
    mappatura_codici = {
        'TRE00000': 'TRE0',
        'GRUN0000': 'GRUN000'
    }

    # Applichiamo il dizionario alla colonna Codice della FATTURA
    if 'Codice' in df_fattura.columns:
        df_fattura['Codice'] = df_fattura['Codice'].replace(mappatura_codici)

    # Arrotondamento (Fix Floating Point)
    for col in ['Qta_Fattura', 'Prezzo_Unit_Fattura', 'Totale_Fattura']:
        if col in df_fattura.columns: df_fattura[col] = df_fattura[col].round(2)
    for col in ['Qta_Report', 'Prezzo_Unit_Report', 'Totale_Report']:
        if col in df_report.columns: df_report[col] = df_report[col].round(2)

# --- FIX PUNTO 3: AGGREGAZIONE (GROUPBY) ARTICOLI DIVISI SU PIU' CANTIERI ---
    if not df_report.empty:
        df_report = df_report.groupby(['DDT', 'Codice'], as_index=False).agg({
            'Data_Report': 'first',         # Mantiene la prima data trovata
            'Descrizione_Report': 'first',  # Mantiene la prima descrizione trovata
            'UM_Report': 'first',           # Mantiene la prima UM trovata
            'Prezzo_Unit_Report': 'first',  # Il prezzo unitario resta invariato (NON si somma)
            'Qta_Report': 'sum',            # SOMMA le quantità dei vari cantieri
            'Totale_Report': 'sum'          # SOMMA i totali dei vari cantieri
        })

    # Core Engine: Outer Merge
    df_merged = pd.merge(df_fattura, df_report, on=['DDT', 'Codice'], how='outer')
    
    # Layout Excel
    colonne_finali = [
        'DDT', 'Codice', 
        'Descrizione_Fattura', 'Descrizione_Report', 
        'Data_Fattura', 'Data_Report',
        'UM_Fattura', 'UM_Report',
        'Qta_Fattura', 'Qta_Report',
        'Prezzo_Unit_Fattura', 'Prezzo_Unit_Report',
        'Totale_Fattura', 'Totale_Report'
    ]
    df_export = df_merged[[c for c in colonne_finali if c in df_merged.columns]]

    # Statistiche
    totale_righe = len(df_export)
    mancanti_a_report = df_export['Qta_Report'].isna().sum()
    discrepanze_valori = df_export[
        df_export['Qta_Report'].notna() & (
            (df_export['Qta_Fattura'] != df_export['Qta_Report']) | 
            (df_export['Prezzo_Unit_Fattura'] != df_export['Prezzo_Unit_Report']) |
            (df_export['UM_Fattura'] != df_export['UM_Report']) |
            (df_export['Totale_Fattura'] != df_export['Totale_Report'])
        )
    ].shape[0]
    match_perfetti = totale_righe - mancanti_a_report - discrepanze_valori

    # GESTIONE CARTELLE E SPOSTAMENTO FILE (Workflow In/Out)
    # Creiamo la cartella di destinazione estraendo la data dal nome del file della fattura
    nome_fattura = os.path.basename(file_fattura)
    
    # Cerca un pattern di data come gg.mm.aa oppure gg-mm-aaaa nel nome del file
    date_match = re.search(r'(\d{2})[\.\-](\d{2})[\.\-](\d{2,4})', nome_fattura)
    
    if date_match:
        dd, mm, yy = date_match.groups()
        if len(yy) == 2:
            yy = "20" + yy # Normalizziamo l'anno a 4 cifre
        data_cartella = f"{dd}-{mm}-{yy}"
    else:
        # Fallback se non c'è una data nel nome
        data_cartella = datetime.now().strftime("%d-%m-%Y")

    nome_cartella_out = f"Confronto_Fattura_ETERNOO_{data_cartella}"
    cartella_output = os.path.join(base_dir, nome_cartella_out)
    
    # Sicurezza: Se esiste già una cartella per questa data, aggiungiamo l'ora per non sovrascriverla
    if os.path.exists(cartella_output):
        nome_cartella_out = f"Confronto_Fattura_ETERNOO_{data_cartella}_{datetime.now().strftime('%H%M%S')}"
        cartella_output = os.path.join(base_dir, nome_cartella_out)
        
    os.makedirs(cartella_output)

    # Salvataggio Excel
    file_output_excel = os.path.join(cartella_output, f"Esito_Confronto_Fattura_ETERNOO_{data_cartella}.xlsx")
    styled_df = df_export.style.apply(evidenzia_discrepanze, axis=1)
    styled_df.to_excel(file_output_excel, engine='openpyxl', index=False)

    # Spostamento dei PDF originali dalla cartella Files loader alla nuova cartella
    try:
        shutil.move(file_report, os.path.join(cartella_output, os.path.basename(file_report)))
        shutil.move(file_fattura, os.path.join(cartella_output, os.path.basename(file_fattura)))
    except Exception as e:
        messagebox.showwarning("Attenzione", f"Excel generato, ma impossibile spostare i PDF (forse sono aperti in un altro programma?).\nErrore: {e}")

    # Esito
    msg = (f"Elaborazione Completata con Successo!\n\n"
           f"Tutti i file sono stati spostati in:\n-> {nome_cartella_out}\n\n"
           f"Riepilogo Analisi:\n"
           f"- Totale righe: {totale_righe}\n"
           f"- Match perfetti: {match_perfetti}\n"
           f"- Discrepanze (Rosso): {discrepanze_valori}\n"
           f"- Fatturati ma mancanti a report (Giallo): {mancanti_a_report}")
           
    messagebox.showinfo("Report M2G", msg)

if __name__ == "__main__":
    avvia_elaborazione()