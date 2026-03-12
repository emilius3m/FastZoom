from __future__ import annotations

"""
Vocabolari ICCD centralizzati.

Fonte riferimento:
- TMA-3.00_INV_01 (campo NCTR "Codice regione")
- ICCD / ISTAT per codici territoriali
"""

# Vocabolario chiuso LIR (Livello di Ricerca)
LIVELLI_RICERCA: dict[str, str] = {
    "I": "Inventario",
    "P": "Precatalogo",
    "C": "Catalogo",
}


# Codici Regione ICCD (NCTR) - Lista chiusa, fonte ISTAT/ICCD
CODICI_REGIONE: dict[str, str] = {
    "00": "Estero",
    "01": "Piemonte",
    "02": "Valle d'Aosta",
    "03": "Lombardia",
    "04": "Trentino-Alto Adige",
    "05": "Veneto",
    "06": "Friuli-Venezia Giulia",
    "07": "Liguria",
    "08": "Emilia-Romagna",
    "09": "Toscana",
    "10": "Umbria",
    "11": "Marche",
    "12": "Lazio",
    "13": "Abruzzo",
    "14": "Molise",
    "15": "Campania",
    "16": "Puglia",
    "17": "Basilicata",
    "18": "Calabria",
    "19": "Sicilia",
    "20": "Sardegna",
}


# PVCR - Denominazioni ufficiali regioni italiane (Lista Regioni ICCD)
DENOMINAZIONI_REGIONE: dict[str, str] = {
    "01": "Piemonte",
    "02": "Valle d'Aosta/Vallée d'Aoste",
    "03": "Lombardia",
    "04": "Trentino-Alto Adige/Südtirol",
    "05": "Veneto",
    "06": "Friuli-Venezia Giulia",
    "07": "Liguria",
    "08": "Emilia-Romagna",
    "09": "Toscana",
    "10": "Umbria",
    "11": "Marche",
    "12": "Lazio",
    "13": "Abruzzo",
    "14": "Molise",
    "15": "Campania",
    "16": "Puglia",
    "17": "Basilicata",
    "18": "Calabria",
    "19": "Sicilia",
    "20": "Sardegna",
    "00": "00",  # bene situato all'estero
}


# PVCP - Sigle province italiane (Lista Province ICCD)
# Vocabolario chiuso - 107 province + valore speciale estero
SIGLE_PROVINCE: dict[str, str] = {
    # Piemonte
    "AL": "Alessandria", "AT": "Asti", "BI": "Biella", "CN": "Cuneo",
    "NO": "Novara", "TO": "Torino", "VB": "Verbano-Cusio-Ossola", "VC": "Vercelli",
    # Valle d'Aosta
    "AO": "Aosta",
    # Lombardia
    "BG": "Bergamo", "BS": "Brescia", "CO": "Como", "CR": "Cremona",
    "LC": "Lecco", "LO": "Lodi", "MB": "Monza-Brianza", "MI": "Milano",
    "MN": "Mantova", "PV": "Pavia", "SO": "Sondrio", "VA": "Varese",
    # Trentino-Alto Adige
    "BZ": "Bolzano", "TN": "Trento",
    # Veneto
    "BL": "Belluno", "PD": "Padova", "RO": "Rovigo", "TV": "Treviso",
    "VE": "Venezia", "VI": "Vicenza", "VR": "Verona",
    # Friuli-Venezia Giulia
    "GO": "Gorizia", "PN": "Pordenone", "TS": "Trieste", "UD": "Udine",
    # Liguria
    "GE": "Genova", "IM": "Imperia", "SP": "La Spezia", "SV": "Savona",
    # Emilia-Romagna
    "BO": "Bologna", "FC": "Forlì-Cesena", "FE": "Ferrara", "MO": "Modena",
    "PC": "Piacenza", "PR": "Parma", "RA": "Ravenna", "RE": "Reggio nell'Emilia",
    "RN": "Rimini",
    # Toscana
    "AR": "Arezzo", "FI": "Firenze", "GR": "Grosseto", "LI": "Livorno",
    "LU": "Lucca", "MS": "Massa-Carrara", "PI": "Pisa", "PO": "Prato",
    "PT": "Pistoia", "SI": "Siena",
    # Umbria
    "PG": "Perugia", "TR": "Terni",
    # Marche
    "AN": "Ancona", "AP": "Ascoli Piceno", "FM": "Fermo",
    "MC": "Macerata", "PU": "Pesaro-Urbino",
    # Lazio
    "FR": "Frosinone", "LT": "Latina", "RI": "Rieti", "RM": "Roma", "VT": "Viterbo",
    # Abruzzo
    "AQ": "L'Aquila", "CH": "Chieti", "PE": "Pescara", "TE": "Teramo",
    # Molise
    "CB": "Campobasso", "IS": "Isernia",
    # Campania
    "AV": "Avellino", "BN": "Benevento", "CE": "Caserta", "NA": "Napoli", "SA": "Salerno",
    # Puglia
    "BA": "Bari", "BR": "Brindisi", "BT": "Barletta-Andria-Trani",
    "FG": "Foggia", "LE": "Lecce", "TA": "Taranto",
    # Basilicata
    "MT": "Matera", "PZ": "Potenza",
    # Calabria
    "CS": "Cosenza", "CZ": "Catanzaro", "KR": "Crotone",
    "RC": "Reggio Calabria", "VV": "Vibo Valentia",
    # Sicilia
    "AG": "Agrigento", "CL": "Caltanissetta", "CT": "Catania", "EN": "Enna",
    "ME": "Messina", "PA": "Palermo", "RG": "Ragusa", "SR": "Siracusa", "TP": "Trapani",
    # Sardegna
    "CA": "Cagliari", "NU": "Nuoro", "OR": "Oristano", "SS": "Sassari", "SU": "Sud Sardegna",
    # Estero
    "00": "Bene situato all'estero",
}

SIGLE_PROVINCE_VALIDE = set(SIGLE_PROVINCE.keys())


# Helper: province per regione (per select dipendente da PVCR)
PROVINCE_PER_REGIONE: dict[str, list[str]] = {
    "Piemonte": ["AL", "AT", "BI", "CN", "NO", "TO", "VB", "VC"],
    "Valle d'Aosta/Vallée d'Aoste": ["AO"],
    "Lombardia": ["BG", "BS", "CO", "CR", "LC", "LO", "MB", "MI", "MN", "PV", "SO", "VA"],
    "Trentino-Alto Adige/Südtirol": ["BZ", "TN"],
    "Veneto": ["BL", "PD", "RO", "TV", "VE", "VI", "VR"],
    "Friuli-Venezia Giulia": ["GO", "PN", "TS", "UD"],
    "Liguria": ["GE", "IM", "SP", "SV"],
    "Emilia-Romagna": ["BO", "FC", "FE", "MO", "PC", "PR", "RA", "RE", "RN"],
    "Toscana": ["AR", "FI", "GR", "LI", "LU", "MS", "PI", "PO", "PT", "SI"],
    "Umbria": ["PG", "TR"],
    "Marche": ["AN", "AP", "FM", "MC", "PU"],
    "Lazio": ["FR", "LT", "RI", "RM", "VT"],
    "Abruzzo": ["AQ", "CH", "PE", "TE"],
    "Molise": ["CB", "IS"],
    "Campania": ["AV", "BN", "CE", "NA", "SA"],
    "Puglia": ["BA", "BR", "BT", "FG", "LE", "TA"],
    "Basilicata": ["MT", "PZ"],
    "Calabria": ["CS", "CZ", "KR", "RC", "VV"],
    "Sicilia": ["AG", "CL", "CT", "EN", "ME", "PA", "RG", "SR", "TP"],
    "Sardegna": ["CA", "NU", "OR", "SS", "SU"],
    "00": ["00"],
}


# DTM - Motivazione cronologia - Vocabolario chiuso scheda TMA 3.00
# Campo ripetitivo: l'utente può selezionare più valori
DTM_MOTIVAZIONI_TMA: list[str] = [
    "analisi dei materiali",
    "analisi chimico-fisica",
    "analisi stilistica",
    "bibliografia",
    "bollo",
    "contesto",
    "data",
    "dati epigrafici",
    "documentazione",
    "tradizione orale",
    "NR (recupero pregresso)",
]

# Esteso con valori usati nell'esempio reale (file allegato)
DTM_MOTIVAZIONI_TMA_EXTENDED: list[str] = [
    *DTM_MOTIVAZIONI_TMA,
    "analisi tipologica",  # presente nell'esempio 6_TMA_esempio_materiali-da-US
]


# CDGG - Condizione giuridica - Vocabolario chiuso scheda TMA 3.00
CDGG_CONDIZIONE_GIURIDICA: list[str] = [
    # Proprietà
    "proprietà Stato",
    "proprietà Ente pubblico territoriale",
    "proprietà Ente pubblico non territoriale",
    "proprietà privata",
    "proprietà Ente religioso cattolico",
    "proprietà Ente religioso non cattolico",
    "proprietà Ente straniero in Italia",
    "proprietà mista pubblica/privata",
    "proprietà mista pubblica/ecclesiastica",
    "proprietà mista privata/ecclesiastica",
    # Detenzione
    "detenzione Stato",
    "detenzione Ente pubblico territoriale",
    "detenzione Ente pubblico non territoriale",
    "detenzione privata",
    "detenzione Ente religioso cattolico",
    "detenzione Ente religioso non cattolico",
    "detenzione Ente straniero in Italia",
    "detenzione mista pubblica/privata",
    "detenzione mista pubblica/ecclesiastica",
    "detenzione mista privata/ecclesiastica",
    # Recupero pregresso
    "NR (recupero pregresso)",
]

# Valore di default per beni MiC / Soprintendenze
CDGG_DEFAULT = "proprietà Stato"

# Gruppi per <optgroup> nel select HTML
CDGG_GRUPPI: dict[str, list[str]] = {
    "Proprietà": [v for v in CDGG_CONDIZIONE_GIURIDICA if v.startswith("proprietà")],
    "Detenzione": [v for v in CDGG_CONDIZIONE_GIURIDICA if v.startswith("detenzione")],
    "Non rilevato": ["NR (recupero pregresso)"],
}

