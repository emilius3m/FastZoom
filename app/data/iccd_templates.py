"""Template JSON per schemi ICCD standard - Catalogazione Archeologica."""

from datetime import datetime
from typing import Dict, Any


def get_iccd_ra_template() -> Dict[str, Any]:
    """Template per scheda RA - Reperto Archeologico secondo standard ICCD 4.00."""
    
    return {
        "id": "iccd_ra_template",
        "name": "Scheda RA - Reperto Archeologico ICCD",
        "description": "Schema standard ICCD 4.00 per catalogazione reperti archeologici",
        "category": "artifact", 
        "icon": "🏺",
        "standard": "ICCD_4.00",
        "schema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "title": "Scheda RA - Reperto Archeologico",
            "properties": {
                "CD": {
                    "type": "object",
                    "title": "CODICI",
                    "properties": {
                        "TSK": {
                            "type": "string",
                            "title": "Tipo scheda",
                            "const": "RA",
                            "description": "Reperto Archeologico"
                        },
                        "LIR": {
                            "type": "string", 
                            "title": "Livello ricerca",
                            "enum": ["P", "C", "A"],
                            "enumNames": ["Precatalogazione", "Catalogazione", "Approfondimento"],
                            "default": "C"
                        },
                        "NCT": {
                            "type": "object",
                            "title": "CODICE UNIVOCO",
                            "properties": {
                                "NCTR": {
                                    "type": "string",
                                    "title": "Codice Regione",
                                    "pattern": "^[0-9]{2}$",
                                    "description": "Codice ISTAT regione (12 = Lazio)",
                                    "default": "12"
                                },
                                "NCTN": {
                                    "type": "string",
                                    "title": "Numero catalogo generale",
                                    "pattern": "^[0-9]{8}$",
                                    "description": "Numero progressivo nazionale"
                                },
                                "NCTS": {
                                    "type": "string",
                                    "title": "Suffisso numero catalogo",
                                    "pattern": "^[A-Z]{0,2}$",
                                    "description": "Suffisso alfanumerico opzionale"
                                }
                            },
                            "required": ["NCTR", "NCTN"]
                        },
                        "ESC": {
                            "type": "string",
                            "title": "Ente schedatore",
                            "description": "Codice dell'ente che ha realizzato la scheda",
                            "default": "SSABAP-RM"
                        }
                    },
                    "required": ["TSK", "LIR", "NCT", "ESC"]
                },

                "OG": {
                    "type": "object", 
                    "title": "OGGETTO",
                    "properties": {
                        "OGT": {
                            "type": "object",
                            "title": "OGGETTO",
                            "properties": {
                                "OGTD": {
                                    "type": "string",
                                    "title": "Definizione",
                                    "description": "Termine che indica la tipologia dell'oggetto",
                                    "examples": ["coppa", "anfora", "lucerna", "fibula", "moneta"]
                                },
                                "OGTT": {
                                    "type": "string",
                                    "title": "Tipologia",
                                    "description": "Specificazione tipologica dell'oggetto"
                                },
                                "OGTN": {
                                    "type": "string",
                                    "title": "Denominazione",
                                    "description": "Nome proprio dell'oggetto se noto"
                                }
                            },
                            "required": ["OGTD"]
                        },
                        "OGN": {
                            "type": "object",
                            "title": "NUMERO D'INVENTARIO",
                            "properties": {
                                "OGNN": {
                                    "type": "string",
                                    "title": "Numero",
                                    "description": "Numero d'inventario del reperto"
                                },
                                "OGNS": {
                                    "type": "string",
                                    "title": "Specifiche",
                                    "description": "Specificazioni sul numero d'inventario"
                                }
                            }
                        }
                    },
                    "required": ["OGT"]
                },

                "LC": {
                    "type": "object",
                    "title": "LOCALIZZAZIONE GEOGRAFICO-AMMINISTRATIVA",
                    "properties": {
                        "PVC": {
                            "type": "object",
                            "title": "LOCALIZZAZIONE GEOGRAFICO-AMMINISTRATIVA",
                            "properties": {
                                "PVCS": {
                                    "type": "string",
                                    "title": "Stato",
                                    "default": "Italia"
                                },
                                "PVCR": {
                                    "type": "string", 
                                    "title": "Regione",
                                    "default": "Lazio"
                                },
                                "PVCP": {
                                    "type": "string",
                                    "title": "Provincia",
                                    "default": "RM"
                                },
                                "PVCC": {
                                    "type": "string",
                                    "title": "Comune",
                                    "default": "Roma"
                                }
                            },
                            "required": ["PVCS", "PVCR", "PVCP", "PVCC"]
                        },
                        "PVL": {
                            "type": "object",
                            "title": "LOCALIZZAZIONE SPECIFICA",
                            "properties": {
                                "PVLN": {
                                    "type": "string",
                                    "title": "Denominazione",
                                    "description": "Nome del sito archeologico",
                                    "default": "Domus Flavia"
                                },
                                "PVLI": {
                                    "type": "string",
                                    "title": "Indirizzo",
                                    "description": "Via o località"
                                }
                            }
                        },
                        "LDC": {
                            "type": "object",
                            "title": "COLLOCAZIONE SPECIFICA",
                            "properties": {
                                "LDCN": {
                                    "type": "string",
                                    "title": "Denominazione raccolta",
                                    "description": "Nome della collezione o deposito"
                                },
                                "LDCU": {
                                    "type": "string", 
                                    "title": "Ubicazione",
                                    "description": "Ubicazione specifica del reperto"
                                }
                            }
                        }
                    },
                    "required": ["PVC"]
                },

                "DT": {
                    "type": "object",
                    "title": "CRONOLOGIA",
                    "properties": {
                        "DTS": {
                            "type": "object",
                            "title": "CRONOLOGIA GENERICA",
                            "properties": {
                                "DTSI": {
                                    "type": "string",
                                    "title": "Secolo da",
                                    "description": "Secolo iniziale (romano: I a.C., I d.C., ecc.)"
                                },
                                "DTSF": {
                                    "type": "string",
                                    "title": "Secolo a", 
                                    "description": "Secolo finale"
                                },
                                "DTSV": {
                                    "type": "string",
                                    "title": "Validità",
                                    "enum": ["ca.", "?", "ante", "post", "non ante", "non post"],
                                    "description": "Validità dell'attribuzione cronologica"
                                }
                            }
                        },
                        "DTM": {
                            "type": "object",
                            "title": "CRONOLOGIA SPECIFICA", 
                            "properties": {
                                "DTMA": {
                                    "type": "integer",
                                    "title": "Anno da",
                                    "minimum": -753,
                                    "maximum": 2100,
                                    "description": "Anno iniziale"
                                },
                                "DTMB": {
                                    "type": "integer",
                                    "title": "Anno a",
                                    "minimum": -753, 
                                    "maximum": 2100,
                                    "description": "Anno finale"
                                },
                                "DTMV": {
                                    "type": "string",
                                    "title": "Validità",
                                    "enum": ["ca.", "?", "ante", "post"],
                                    "description": "Validità dell'attribuzione cronologica specifica"
                                }
                            }
                        }
                    }
                },

                "AU": {
                    "type": "object",
                    "title": "DEFINIZIONE CULTURALE",
                    "properties": {
                        "AUT": {
                            "type": "object",
                            "title": "AMBITO CULTURALE",
                            "properties": {
                                "AUTM": {
                                    "type": "string",
                                    "title": "Denominazione",
                                    "description": "Denominazione dell'ambito culturale",
                                    "examples": ["romano", "etrusco", "greco", "italico"]
                                },
                                "AUTS": {
                                    "type": "string",
                                    "title": "Specifiche",
                                    "description": "Specificazioni dell'ambito culturale"
                                }
                            }
                        }
                    }
                },

                "MT": {
                    "type": "object",
                    "title": "DATI TECNICI", 
                    "properties": {
                        "MTC": {
                            "type": "object",
                            "title": "MATERIA E TECNICA",
                            "properties": {
                                "MTCM": {
                                    "type": "array",
                                    "title": "Materia",
                                    "description": "Materiale costitutivo principale",
                                    "items": {
                                        "type": "string",
                                        "enum": ["ceramica", "terracotta", "argilla", "bronzo", "ferro", "piombo", "oro", "argento", "marmo", "travertino", "tufo", "legno", "osso", "avorio", "vetro", "ambra", "pasta vitrea"]
                                    },
                                    "minItems": 1
                                },
                                "MTCT": {
                                    "type": "string",
                                    "title": "Tecnica",
                                    "description": "Tecnica di lavorazione",
                                    "examples": ["tornio", "modellato a mano", "matrice", "fusione", "martellato", "inciso", "dipinto"]
                                }
                            },
                            "required": ["MTCM"]
                        },
                        "MIS": {
                            "type": "object",
                            "title": "MISURE",
                            "properties": {
                                "MISA": {
                                    "type": "number",
                                    "title": "Altezza",
                                    "description": "Altezza in cm",
                                    "minimum": 0,
                                    "multipleOf": 0.1
                                },
                                "MISL": {
                                    "type": "number", 
                                    "title": "Larghezza",
                                    "description": "Larghezza in cm",
                                    "minimum": 0,
                                    "multipleOf": 0.1
                                },
                                "MISP": {
                                    "type": "number",
                                    "title": "Profondità", 
                                    "description": "Profondità in cm",
                                    "minimum": 0,
                                    "multipleOf": 0.1
                                },
                                "MISD": {
                                    "type": "number",
                                    "title": "Diametro",
                                    "description": "Diametro in cm",
                                    "minimum": 0,
                                    "multipleOf": 0.1  
                                },
                                "MISU": {
                                    "type": "string",
                                    "title": "Unità di misura",
                                    "default": "cm",
                                    "enum": ["mm", "cm", "m"]
                                }
                            }
                        }
                    },
                    "required": ["MTC"]
                },

                "DA": {
                    "type": "object",
                    "title": "DATI ANALITICI",
                    "properties": {
                        "DES": {
                            "type": "object",
                            "title": "DESCRIZIONE",
                            "properties": {
                                "DESO": {
                                    "type": "string",
                                    "title": "Descrizione oggetto",
                                    "description": "Descrizione dettagliata del reperto",
                                    "minLength": 10
                                },
                                "DESI": {
                                    "type": "string",
                                    "title": "Descrizione iconografica", 
                                    "description": "Descrizione di decorazioni e iconografia"
                                }
                            },
                            "required": ["DESO"]
                        },
                        "ISR": {
                            "type": "object",
                            "title": "ISCRIZIONI",
                            "properties": {
                                "ISRC": {
                                    "type": "string",
                                    "title": "Classe",
                                    "enum": ["votiva", "funeraria", "onoraria", "sacra", "profana", "instrumentum domesticum"],
                                    "description": "Classificazione dell'iscrizione"
                                },
                                "ISRI": {
                                    "type": "string",
                                    "title": "Iscrizione",
                                    "description": "Testo dell'iscrizione"
                                },
                                "ISRL": {
                                    "type": "string", 
                                    "title": "Lingua",
                                    "enum": ["latino", "greco", "etrusco", "osco", "umbro"],
                                    "description": "Lingua dell'iscrizione"
                                }
                            }
                        },
                        "STC": {
                            "type": "object",
                            "title": "STATO DI CONSERVAZIONE",
                            "properties": {
                                "STCC": {
                                    "type": "string",
                                    "title": "Stato di conservazione",
                                    "enum": ["ottimo", "buono", "discreto", "cattivo", "pessimo"],
                                    "enumNames": ["Ottimo", "Buono", "Discreto", "Cattivo", "Pessimo"]
                                },
                                "STCS": {
                                    "type": "string",
                                    "title": "Indicazioni specifiche",
                                    "description": "Descrizione dettagliata dello stato conservativo"
                                }
                            },
                            "required": ["STCC"]
                        }
                    },
                    "required": ["DES", "STC"]
                },

                "NS": {
                    "type": "object",
                    "title": "NOTIZIE STORICHE",
                    "properties": {
                        "NSC": {
                            "type": "object",
                            "title": "NOTIZIE STORICHE",
                            "properties": {
                                "NSCR": {
                                    "type": "string",
                                    "title": "Rinvenimento",
                                    "description": "Circostanze e modalità di rinvenimento"
                                },
                                "NSCD": {
                                    "type": "string",
                                    "title": "Data",
                                    "pattern": "^[0-9]{4}(-[0-9]{2}(-[0-9]{2})?)?$",
                                    "description": "Data di rinvenimento (YYYY-MM-DD)"
                                }
                            }
                        }
                    }
                },

                "RS": {
                    "type": "object", 
                    "title": "FONTI E DOCUMENTI DI RIFERIMENTO",
                    "properties": {
                        "RSE": {
                            "type": "object",
                            "title": "ESISTENZA",
                            "properties": {
                                "RSER": {
                                    "type": "string",
                                    "title": "Responsabile ricerca",
                                    "description": "Nome del responsabile della ricerca archeologica"
                                },
                                "RSEC": {
                                    "type": "string",
                                    "title": "Anno di realizzazione",
                                    "pattern": "^[0-9]{4}$",
                                    "description": "Anno di realizzazione della ricerca"
                                }
                            }
                        }
                    }
                }
            },
            
            "required": ["CD", "OG", "LC", "DT", "MT", "DA"]
        },
        
        "ui_schema": {
            "CD": {
                "ui:order": ["TSK", "LIR", "NCT", "ESC"],
                "NCT": {
                    "ui:order": ["NCTR", "NCTN", "NCTS"]
                }
            },
            "OG": {
                "OGT": {
                    "ui:order": ["OGTD", "OGTT", "OGTN"]
                }
            },
            "LC": {
                "ui:order": ["PVC", "PVL", "LDC"]
            },
            "MT": {
                "MTC": {
                    "MTCM": {
                        "ui:widget": "checkboxes"
                    }
                }
            },
            "DA": {
                "DES": {
                    "DESO": {
                        "ui:widget": "textarea",
                        "ui:options": {
                            "rows": 5
                        }
                    }
                }
            }
        }
    }

def get_iccd_ca_template() -> Dict[str, Any]:
    """Template per scheda CA - Complesso Archeologico secondo standard ICCD 4.00."""
    
    return {
        "id": "iccd_ca_template",
        "name": "Scheda CA - Complesso Archeologico ICCD",
        "description": "Schema standard ICCD 4.00 per catalogazione complessi archeologici",
        "category": "architecture",
        "icon": "🏛️",
        "standard": "ICCD_4.00",
        "schema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "title": "Scheda CA - Complesso Archeologico",
            "properties": {
                "CD": {
                    "type": "object",
                    "title": "CODICI",
                    "properties": {
                        "TSK": {
                            "type": "string",
                            "title": "Tipo scheda",
                            "const": "CA",
                            "description": "Complesso Archeologico"
                        },
                        "LIR": {
                            "type": "string",
                            "title": "Livello ricerca",
                            "enum": ["P", "C", "A"],
                            "enumNames": ["Precatalogazione", "Catalogazione", "Approfondimento"],
                            "default": "C"
                        },
                        "NCT": {
                            "type": "object",
                            "title": "CODICE UNIVOCO",
                            "properties": {
                                "NCTR": {
                                    "type": "string",
                                    "title": "Codice Regione",
                                    "pattern": "^[0-9]{2}$",
                                    "default": "12"
                                },
                                "NCTN": {
                                    "type": "string",
                                    "title": "Numero catalogo generale",
                                    "pattern": "^[0-9]{8}$"
                                },
                                "NCTS": {
                                    "type": "string",
                                    "title": "Suffisso numero catalogo",
                                    "pattern": "^[A-Z]{0,2}$"
                                }
                            },
                            "required": ["NCTR", "NCTN"]
                        },
                        "ESC": {
                            "type": "string",
                            "title": "Ente schedatore",
                            "default": "SSABAP-RM"
                        }
                    },
                    "required": ["TSK", "LIR", "NCT", "ESC"]
                },
                "OG": {
                    "type": "object",
                    "title": "OGGETTO",
                    "properties": {
                        "OGT": {
                            "type": "object",
                            "title": "OGGETTO",
                            "properties": {
                                "OGTD": {
                                    "type": "string",
                                    "title": "Definizione",
                                    "examples": ["domus", "villa", "tempio", "terme", "teatro", "anfiteatro", "foro"]
                                },
                                "OGTT": {
                                    "type": "string",
                                    "title": "Tipologia"
                                }
                            },
                            "required": ["OGTD"]
                        }
                    },
                    "required": ["OGT"]
                }
                # ... altre sezioni simili alla RA ma adattate per complessi architettonici
            },
            "required": ["CD", "OG", "LC"]
        },
        "ui_schema": {}
    }

def get_iccd_si_template() -> Dict[str, Any]:
    """Template per scheda SI - Sito Archeologico secondo standard ICCD 4.00."""
    
    return {
        "id": "iccd_si_template", 
        "name": "Scheda SI - Sito Archeologico ICCD",
        "description": "Schema standard ICCD 4.00 per catalogazione siti archeologici",
        "category": "site",
        "icon": "🏛️",
        "standard": "ICCD_4.00",
        "schema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "title": "Scheda SI - Sito Archeologico",
            "properties": {
                "CD": {
                    "type": "object",
                    "title": "CODICI",
                    "properties": {
                        "TSK": {
                            "type": "string",
                            "title": "Tipo scheda",
                            "const": "SI",
                            "description": "Sito Archeologico"
                        },
                        "LIR": {
                            "type": "string",
                            "title": "Livello ricerca",
                            "enum": ["P", "C", "A"],
                            "enumNames": ["Precatalogazione", "Catalogazione", "Approfondimento"],
                            "default": "C"
                        },
                        "NCT": {
                            "type": "object",
                            "title": "CODICE UNIVOCO",
                            "properties": {
                                "NCTR": {
                                    "type": "string",
                                    "title": "Codice Regione",
                                    "pattern": "^[0-9]{2}$",
                                    "default": "12"
                                },
                                "NCTN": {
                                    "type": "string",
                                    "title": "Numero catalogo generale",
                                    "pattern": "^[0-9]{8}$"
                                }
                            },
                            "required": ["NCTR", "NCTN"]
                        },
                        "ESC": {
                            "type": "string",
                            "title": "Ente schedatore",
                            "default": "SSABAP-RM"
                        }
                    },
                    "required": ["TSK", "LIR", "NCT", "ESC"]
                }
                # ... altre sezioni per siti archeologici
            },
            "required": ["CD", "OG", "LC"]
        },
        "ui_schema": {}
    }

# Dizionario con tutti i template disponibili
ICCD_TEMPLATES = {
    "RA": get_iccd_ra_template(),
    "CA": get_iccd_ca_template(), 
    "SI": get_iccd_si_template()
}

def get_template_by_type(schema_type: str) -> Dict[str, Any]:
    """Ottieni template ICCD per tipo schema."""
    return ICCD_TEMPLATES.get(schema_type, {})

def get_all_templates() -> Dict[str, Dict[str, Any]]:
    """Ottieni tutti i template ICCD disponibili."""
    return ICCD_TEMPLATES

def generate_default_iccd_data(schema_type: str, site_name: str = "Domus Flavia") -> Dict[str, Any]:
    """Genera dati ICCD di default con valori precompilati per Domus Flavia."""
    
    now = datetime.now()
    year = now.year % 100
    sequence = now.microsecond % 1000000
    nct_number = f"{year:02d}{sequence:06d}"
    
    base_data = {
        "CD": {
            "TSK": schema_type,
            "LIR": "C",
            "NCT": {
                "NCTR": "12",  # Lazio
                "NCTN": nct_number
            },
            "ESC": "SSABAP-RM"
        },
        "LC": {
            "PVC": {
                "PVCS": "Italia",
                "PVCR": "Lazio",
                "PVCP": "RM", 
                "PVCC": "Roma"
            },
            "PVL": {
                "PVLN": site_name,
                "PVLI": "Palatino"
            }
        }
    }
    
    if schema_type == "RA":
        base_data.update({
            "OG": {
                "OGT": {
                    "OGTD": ""  # Da compilare
                }
            },
            "DT": {
                "DTS": {
                    "DTSI": "I d.C.",
                    "DTSF": "III d.C."
                }
            },
            "MT": {
                "MTC": {
                    "MTCM": []  # Da selezionare
                }
            },
            "DA": {
                "DES": {
                    "DESO": ""  # Da compilare
                },
                "STC": {
                    "STCC": "buono"  # Valore di default
                }
            }
        })
    
    return base_data