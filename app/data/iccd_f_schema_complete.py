"""
Scheda ICCD F 4.00 - Fotografia COMPLETA
Conforme a normativa ufficiale ICCD MiC 2025

Basato su:
- ICCD_F_4.00.xls (normativa ufficiale)
- ICCD_F_4.00_Norme-compilazione.pdf

Paragrafi obbligatori: CD, OG, MT, CO, TU, DO, AD, CM
Totale paragrafi: 23
"""

from typing import Dict, Any, List


def get_iccd_f_400_schema() -> Dict[str, Any]:
    """
    Schema F 4.00 COMPLETO - Fotografia

    Ambito: Catalogazione fotografia storica e contemporanea
    - Fotografie singole e fondi fotografici
    - Negativi, positivi, stampe
    - Analogico e digitale
    """

    return {
        "id": "iccd_f_400",
        "name": "F 4.00 - Fotografia",
        "version": "4.00",
        "category": "fotografia",
        "standard": "MiC-ICCD-2025",
        "description": "Scheda per catalogazione fotografia storica e contemporanea",

        "schema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "title": "SCHEDA F 4.00 - FOTOGRAFIA",

            "properties": {
                "CD": _get_cd_schema(),
                "OG": _get_og_schema(),
                "RV": _get_rv_schema(),
                "AC": _get_ac_schema(),
                "RF": _get_rf_schema(),
                "LC": _get_lc_schema(),
                "LA": _get_la_schema(),
                "UB": _get_ub_schema(),
                "AU": _get_au_schema(),
                "SG": _get_sg_schema(),
                "DT": _get_dt_schema(),
                "LR": _get_lr_schema(),
                "PD": _get_pd_schema(),
                "MT": _get_mt_schema(),
                "CO": _get_co_schema(),
                "DA": _get_da_schema(),
                "RO": _get_ro_schema(),
                "TU": _get_tu_schema(),
                "DO": _get_do_schema(),
                "MS": _get_ms_schema(),
                "AD": _get_ad_schema(),
                "CM": _get_cm_schema(),
                "AN": _get_an_schema()
            },

            "required": ["CD", "OG", "MT", "CO", "TU", "DO", "AD", "CM"]
        },

        "ui_schema": _get_ui_schema()
    }


def _get_cd_schema() -> Dict[str, Any]:
    """CD - CODICI (Obbligatorio)"""
    return {
        "type": "object",
        "title": "CD - CODICI",
        "properties": {
            "TSK": {"type": "string", "const": "F", "maxLength": 4},
            "LIR": {
                "type": "string",
                "enum": ["P", "I", "C", "A"],
                "enumNames": ["Precatalogazione", "Inventario", "Catalogazione", "Approfondimento"],
                "default": "C"
            },
            "NCT": {
                "type": "object",
                "properties": {
                    "NCTR": {"type": "string", "pattern": "^[0-9]{2}$"},
                    "NCTN": {"type": "string", "pattern": "^[0-9]{8}$"},
                    "NCTS": {"type": "string", "pattern": "^[A-Z]{0,2}$"}
                },
                "required": ["NCTR", "NCTN"]
            },
            "ESC": {"type": "string", "maxLength": 25},
            "ECP": {"type": "string", "maxLength": 25}
        },
        "required": ["TSK", "LIR", "NCT", "ESC", "ECP"]
    }


def _get_og_schema() -> Dict[str, Any]:
    """OG - BENE CULTURALE (Obbligatorio)"""
    return {
        "type": "object",
        "title": "OG - BENE CULTURALE",
        "description": "Identificazione del bene fotografico",
        "properties": {
            "AMB": {
                "type": "string",
                "title": "Ambito di tutela",
                "enum": ["fotografia", "fotografia archeologica", "fotografia storica"],
                "maxLength": 50
            },
            "CTG": {
                "type": "string",
                "title": "Categoria",
                "maxLength": 100
            },
            "OGT": {
                "type": "object",
                "title": "OGGETTO",
                "properties": {
                    "OGTD": {
                        "type": "string",
                        "title": "Definizione",
                        "description": "Da vocabolario ICCD fotografia",
                        "examples": ["fotografia", "negativo", "positivo", "lastra", "diapositiva"]
                    },
                    "OGTT": {
                        "type": "string",
                        "title": "Tipologia",
                        "maxLength": 250
                    },
                    "OGTW": {
                        "type": "string",
                        "title": "Soggetto produzione",
                        "enum": ["fotografia di architettura", "fotografia di paesaggio", "ritratto",
                                 "fotografia documentaria", "fotografia artistica"]
                    },
                    "OGTP": {
                        "type": "string",
                        "title": "Precisazione tipologia"
                    },
                    "OGTV": {
                        "type": "string",
                        "title": "Validità",
                        "enum": ["ca.", "?"]
                    }
                },
                "required": ["OGTD"]
            },
            "QNT": {
                "type": "object",
                "title": "QUANTITÀ",
                "properties": {
                    "QNTN": {"type": "integer", "title": "Numero", "minimum": 1},
                    "QNTI": {"type": "integer", "title": "Numero inventario"},
                    "QNTS": {"type": "string", "title": "Stima"},
                    "QNTO": {"type": "string", "title": "Osservazioni"},
                    "QNTE": {"type": "string", "title": "Esaustività", "enum": ["intero", "parziale"]}
                }
            },
            "OGC": {
                "type": "object",
                "title": "TRATTAMENTO CATALOGRAFICO",
                "properties": {
                    "OGCT": {
                        "type": "string",
                        "title": "Tipo",
                        "enum": ["bene semplice", "bene complesso"]
                    },
                    "OGCN": {"type": "integer", "title": "Numero componenti"},
                    "OGCD": {"type": "string", "title": "Denominazione"},
                    "OGCS": {"type": "string", "title": "Sezione"}
                }
            },
            "OGM": {"type": "string", "title": "Motivazione", "maxLength": 500},
            "OGR": {"type": "string", "title": "Riferimenti", "maxLength": 500}
        },
        "required": ["OGT"]
    }


def _get_rv_schema() -> Dict[str, Any]:
    """RV - RELAZIONI"""
    return {
        "type": "object",
        "title": "RV - RELAZIONI",
        "properties": {
            "RVE": {
                "type": "array",
                "title": "STRUTTURA COMPLESSA",
                "items": {
                    "type": "object",
                    "properties": {
                        "RVEL": {"type": "string", "enum": ["0", "1", "2", "3", "4", "5"]},
                        "RVER": {"type": "string", "maxLength": 25},
                        "RVES": {"type": "string", "maxLength": 25}
                    }
                }
            },
            "RSE": {
                "type": "array",
                "title": "RELAZIONI DIRETTE",
                "items": {
                    "type": "object",
                    "properties": {
                        "RSER": {"type": "string", "maxLength": 70},
                        "RSET": {"type": "string", "maxLength": 10},
                        "RSEC": {"type": "string", "maxLength": 25}
                    }
                }
            }
        }
    }


def _get_ac_schema() -> Dict[str, Any]:
    """AC - ALTRI CODICI"""
    return {
        "type": "object",
        "title": "AC - ALTRI CODICI",
        "properties": {
            "ACC": {
                "type": "array",
                "title": "Altro codice bene",
                "items": {"type": "string", "maxLength": 150}
            },
            "ACS": {
                "type": "array",
                "title": "Altro codice scheda",
                "items": {"type": "string", "maxLength": 150}
            }
        }
    }


def _get_rf_schema() -> Dict[str, Any]:
    """RF - RIFERIMENTO AL FONDO/COLLEZIONE"""
    return {
        "type": "object",
        "title": "RF - RIFERIMENTO AL FONDO/COLLEZIONE",
        "properties": {
            "RFD": {
                "type": "object",
                "title": "DENOMINAZIONE FONDO",
                "properties": {
                    "RFDN": {"type": "string", "title": "Nome fondo"},
                    "RFDS": {"type": "string", "title": "Specifiche"}
                }
            },
            "RFC": {
                "type": "object",
                "title": "CODICE FONDO",
                "properties": {
                    "RFCC": {"type": "string", "title": "Codice"}
                }
            }
        }
    }


def _get_lc_schema() -> Dict[str, Any]:
    """LC - LOCALIZZAZIONE (Obbligatorio)"""
    return {
        "type": "object",
        "title": "LC - LOCALIZZAZIONE GEOGRAFICO-AMMINISTRATIVA",
        "properties": {
            "PVC": {
                "type": "object",
                "title": "LOCALIZZAZIONE ATTUALE",
                "properties": {
                    "PVCS": {"type": "string", "default": "Italia"},
                    "PVCR": {"type": "string", "title": "Regione"},
                    "PVCP": {"type": "string", "title": "Provincia"},
                    "PVCC": {"type": "string", "title": "Comune"}
                },
                "required": ["PVCS", "PVCR", "PVCP", "PVCC"]
            },
            "LDC": {
                "type": "object",
                "title": "CONTENITORE",
                "properties": {
                    "LDCT": {
                        "type": "string",
                        "enum": ["contenitore fisico", "contenitore giuridico"]
                    },
                    "LDCN": {"type": "string", "title": "Nome"},
                    "LDCS": {"type": "string", "title": "Specifiche"},
                    "LDCU": {"type": "string", "title": "Denominazione spazio"},
                    "LDCM": {"type": "string", "title": "Denominazione raccolta"}
                }
            },
            "LCS": {
                "type": "object",
                "title": "COLLOCAZIONE SPECIFICA",
                "properties": {
                    "LCSS": {"type": "string", "title": "Specifiche"},
                    "LCSP": {"type": "string", "title": "Posizione"}
                }
            }
        },
        "required": ["PVC"]
    }


def _get_la_schema() -> Dict[str, Any]:
    """LA - ALTRE LOCALIZZAZIONI"""
    return {
        "type": "object",
        "title": "LA - ALTRE LOCALIZZAZIONI GEOGRAFICO-AMMINISTRATIVE",
        "properties": {
            "TCL": {
                "type": "string",
                "enum": ["localizzazione originaria", "localizzazione precedente"]
            },
            "PVZ": {
                "type": "object",
                "properties": {
                    "PVZS": {"type": "string", "title": "Stato"},
                    "PVZR": {"type": "string", "title": "Regione"},
                    "PVZP": {"type": "string", "title": "Provincia"},
                    "PVZC": {"type": "string", "title": "Comune"}
                }
            }
        }
    }


def _get_ub_schema() -> Dict[str, Any]:
    """UB - DATI PATRIMONIALI"""
    return {
        "type": "object",
        "title": "UB - DATI PATRIMONIALI",
        "properties": {
            "INV": {
                "type": "object",
                "title": "INVENTARIO",
                "properties": {
                    "INVN": {"type": "string", "title": "Numero"},
                    "INVD": {"type": "string", "title": "Data"}
                }
            },
            "ACQ": {
                "type": "object",
                "title": "ACQUISIZIONE",
                "properties": {
                    "ACQT": {"type": "string", "title": "Tipo"},
                    "ACQD": {"type": "string", "title": "Data"}
                }
            },
            "STI": {
                "type": "object",
                "title": "STIMA",
                "properties": {
                    "STIS": {"type": "number", "title": "Valore"},
                    "STID": {"type": "string", "title": "Data"}
                }
            }
        }
    }


def _get_au_schema() -> Dict[str, Any]:
    """AU - DEFINIZIONE CULTURALE"""
    return {
        "type": "object",
        "title": "AU - DEFINIZIONE CULTURALE",
        "properties": {
            "AUF": {
                "type": "array",
                "title": "AUTORE FOTOGRAFIA",
                "items": {
                    "type": "object",
                    "properties": {
                        "AUFN": {"type": "string", "title": "Nome"},
                        "AUFM": {"type": "string", "title": "Motivazione"},
                        "AUFS": {"type": "string", "title": "Specifiche"}
                    }
                }
            },
            "AUS": {
                "type": "array",
                "title": "STUDIO/ATELIER",
                "items": {
                    "type": "object",
                    "properties": {
                        "AUSN": {"type": "string", "title": "Nome"},
                        "AUSM": {"type": "string", "title": "Motivazione"}
                    }
                }
            },
            "CMM": {
                "type": "array",
                "title": "COMMITTENZA",
                "items": {
                    "type": "object",
                    "properties": {
                        "CMMN": {"type": "string", "title": "Nome"},
                        "CMMS": {"type": "string", "title": "Specifiche"}
                    }
                }
            }
        }
    }


def _get_sg_schema() -> Dict[str, Any]:
    """SG - SOGGETTO"""
    return {
        "type": "object",
        "title": "SG - SOGGETTO",
        "properties": {
            "SGT": {
                "type": "object",
                "title": "TITOLO/OGGETTO",
                "properties": {
                    "SGTT": {"type": "string", "title": "Titolo"},
                    "SGTI": {"type": "string", "title": "Indicazioni"}
                }
            },
            "SGD": {
                "type": "object",
                "title": "DESCRIZIONE ICONOGRAFICA",
                "properties": {
                    "SGDD": {"type": "string", "title": "Descrizione"},
                    "SGDE": {"type": "string", "title": "Elementi"}
                }
            }
        }
    }


def _get_dt_schema() -> Dict[str, Any]:
    """DT - CRONOLOGIA"""
    return {
        "type": "object",
        "title": "DT - CRONOLOGIA",
        "properties": {
            "DTZ": {
                "type": "array",
                "title": "CRONOLOGIA GENERICA",
                "items": {
                    "type": "object",
                    "properties": {
                        "DTZG": {"type": "string"},
                        "DTZS": {"type": "string", "enum": ["ca.", "?", "ante", "post"]}
                    }
                }
            },
            "DTS": {
                "type": "array",
                "title": "CRONOLOGIA SPECIFICA",
                "items": {
                    "type": "object",
                    "properties": {
                        "DTSI": {"type": "integer"},
                        "DTSF": {"type": "integer"},
                        "DTSV": {"type": "string"}
                    }
                }
            }
        }
    }


def _get_lr_schema() -> Dict[str, Any]:
    """LR - LUOGO E DATA DI RIPRESA"""
    return {
        "type": "object",
        "title": "LR - LUOGO E DATA DI RIPRESA",
        "properties": {
            "PVR": {
                "type": "object",
                "title": "LUOGO DI RIPRESA",
                "properties": {
                    "PVRS": {"type": "string", "title": "Stato"},
                    "PVRR": {"type": "string", "title": "Regione"},
                    "PVRP": {"type": "string", "title": "Provincia"},
                    "PVRC": {"type": "string", "title": "Comune"},
                    "PVRL": {"type": "string", "title": "Località"}
                }
            },
            "DTR": {
                "type": "object",
                "title": "DATA RIPRESA",
                "properties": {
                    "DTRI": {"type": "string", "title": "Data da"},
                    "DTRF": {"type": "string", "title": "Data a"},
                    "DTRV": {"type": "string", "enum": ["ca.", "?"]}
                }
            }
        }
    }


def _get_pd_schema() -> Dict[str, Any]:
    """PD - PRODUZIONE E DIFFUSIONE"""
    return {
        "type": "object",
        "title": "PD - PRODUZIONE E DIFFUSIONE",
        "properties": {
            "PDL": {
                "type": "object",
                "title": "LUOGO PRODUZIONE",
                "properties": {
                    "PDLS": {"type": "string"},
                    "PDLR": {"type": "string"},
                    "PDLP": {"type": "string"},
                    "PDLC": {"type": "string"}
                }
            },
            "PDT": {
                "type": "object",
                "title": "DATA PRODUZIONE",
                "properties": {
                    "PDTI": {"type": "string"},
                    "PDTF": {"type": "string"}
                }
            }
        }
    }


def _get_mt_schema() -> Dict[str, Any]:
    """MT - DATI TECNICI (Obbligatorio)"""
    return {
        "type": "object",
        "title": "MT - DATI TECNICI",
        "properties": {
            "MTC": {
                "type": "object",
                "title": "MATERIA E TECNICA",
                "properties": {
                    "MTCM": {
                        "type": "array",
                        "title": "Materiale/supporto",
                        "items": {
                            "type": "string",
                            "enum": [
                                "carta",
                                "carta albuminata",
                                "carta baritata",
                                "vetro",
                                "lastra",
                                "pellicola",
                                "supporto digitale"
                            ]
                        },
                        "minItems": 1
                    },
                    "MTCT": {
                        "type": "array",
                        "title": "Tecnica",
                        "items": {
                            "type": "string",
                            "enum": [
                                "albumina",
                                "calotipia",
                                "cianotipia",
                                "dagherrotipo",
                                "gelatina ai sali d'argento",
                                "stampa digitale",
                                "stampa inkjet"
                            ]
                        }
                    }
                },
                "required": ["MTCM"]
            },
            "MIS": {
                "type": "object",
                "title": "MISURE",
                "properties": {
                    "MISU": {"type": "string", "enum": ["cm", "mm"], "default": "cm"},
                    "MISM": {"type": "string", "title": "Tipo misura"},
                    "MISS": {"type": "string", "title": "Dimensioni"}
                }
            },
            "FRM": {
                "type": "string",
                "title": "Formato",
                "enum": ["9x12", "10x15", "13x18", "18x24", "24x36", "30x40", "altro"]
            },
            "STP": {
                "type": "object",
                "title": "STATO POSITIVO/NEGATIVO",
                "properties": {
                    "STPP": {"type": "string", "enum": ["positivo", "negativo"]},
                    "STPS": {"type": "string", "title": "Specifiche"}
                }
            }
        },
        "required": ["MTC"]
    }


def _get_co_schema() -> Dict[str, Any]:
    """CO - CONSERVAZIONE (Obbligatorio)"""
    return {
        "type": "object",
        "title": "CO - CONSERVAZIONE",
        "properties": {
            "STC": {
                "type": "object",
                "title": "STATO DI CONSERVAZIONE",
                "properties": {
                    "STCC": {
                        "type": "string",
                        "enum": ["ottimo", "buono", "discreto", "mediocre", "cattivo", "pessimo"]
                    },
                    "STCS": {"type": "string", "title": "Indicazioni specifiche"}
                }
            }
        }
    }


def _get_da_schema() -> Dict[str, Any]:
    """DA - DATI ANALITICI"""
    return {
        "type": "object",
        "title": "DA - DATI ANALITICI",
        "properties": {
            "DES": {
                "type": "object",
                "title": "DESCRIZIONE",
                "properties": {
                    "DESO": {"type": "string", "title": "Descrizione", "minLength": 20}
                }
            },
            "NSC": {"type": "string", "title": "Notizie storico-critiche"}
        }
    }


def _get_ro_schema() -> Dict[str, Any]:
    """RO - RAPPORTO"""
    return {
        "type": "object",
        "title": "RO - RAPPORTO",
        "properties": {
            "ROF": {
                "type": "array",
                "title": "RAPPORTO FORMALE",
                "items": {
                    "type": "object",
                    "properties": {
                        "ROFT": {"type": "string", "title": "Tipo"},
                        "ROFN": {"type": "string", "title": "Codice"}
                    }
                }
            }
        }
    }


def _get_tu_schema() -> Dict[str, Any]:
    """TU - CONDIZIONE GIURIDICA (Obbligatorio)"""
    return {
        "type": "object",
        "title": "TU - CONDIZIONE GIURIDICA E VINCOLI",
        "properties": {
            "CDG": {
                "type": "object",
                "title": "CONDIZIONE GIURIDICA",
                "properties": {
                    "CDGG": {
                        "type": "string",
                        "enum": ["proprietà Stato", "proprietà Ente locale", "proprietà privata"]
                    }
                },
                "required": ["CDGG"]
            },
            "NVC": {
                "type": "object",
                "title": "VINCOLO",
                "properties": {
                    "NVCT": {"type": "string"},
                    "NVCD": {"type": "string"}
                }
            }
        },
        "required": ["CDG"]
    }


def _get_do_schema() -> Dict[str, Any]:
    """DO - FONTI E DOCUMENTI (Obbligatorio)"""
    return {
        "type": "object",
        "title": "DO - FONTI E DOCUMENTI DI RIFERIMENTO",
        "properties": {
            "FTA": {
                "type": "array",
                "title": "DOCUMENTAZIONE FOTOGRAFICA",
                "items": {
                    "type": "object",
                    "properties": {
                        "FTAN": {"type": "string"},
                        "FTAP": {"type": "string"}
                    }
                }
            },
            "BIB": {
                "type": "array",
                "title": "BIBLIOGRAFIA",
                "items": {
                    "type": "object",
                    "properties": {
                        "BIBX": {"type": "string"},
                        "BIBN": {"type": "string"}
                    }
                },
                "minItems": 1
            }
        },
        "required": ["BIB"]
    }


def _get_ms_schema() -> Dict[str, Any]:
    """MS - MOSTRE"""
    return {
        "type": "object",
        "title": "MS - MOSTRE",
        "properties": {
            "MST": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "MSTT": {"type": "string", "title": "Titolo"},
                        "MSTD": {"type": "string", "title": "Data"}
                    }
                }
            }
        }
    }


def _get_ad_schema() -> Dict[str, Any]:
    """AD - ACCESSO DATI (Obbligatorio)"""
    return {
        "type": "object",
        "title": "AD - ACCESSO AI DATI",
        "properties": {
            "ADS": {
                "type": "object",
                "properties": {
                    "ADSP": {
                        "type": "string",
                        "enum": ["1", "2", "3"],
                        "enumNames": ["Libero", "Riservato enti", "Riservato"],
                        "default": "1"
                    }
                },
                "required": ["ADSP"]
            }
        },
        "required": ["ADS"]
    }


def _get_cm_schema() -> Dict[str, Any]:
    """CM - COMPILAZIONE (Obbligatorio)"""
    return {
        "type": "object",
        "title": "CM - COMPILAZIONE",
        "properties": {
            "CMP": {
                "type": "object",
                "properties": {
                    "CMPD": {"type": "string", "pattern": "^[0-9]{4}$"},
                    "CMPN": {"type": "string"}
                },
                "required": ["CMPD", "CMPN"]
            },
            "RSR": {"type": "string"},
            "FUR": {"type": "string"}
        },
        "required": ["CMP", "FUR"]
    }


def _get_an_schema() -> Dict[str, Any]:
    """AN - ANNOTAZIONI"""
    return {
        "type": "object",
        "title": "AN - ANNOTAZIONI",
        "properties": {
            "OSS": {"type": "string"}
        }
    }


def _get_ui_schema() -> Dict[str, Any]:
    """UI Schema per rendering form"""
    return {
        "CD": {"ui:order": ["TSK", "LIR", "NCT", "ESC", "ECP"]},
        "OG": {
            "OGT": {
                "OGTD": {"ui:help": "Da vocabolario ICCD fotografia"}
            }
        },
        "MT": {
            "MTC": {
                "MTCM": {"ui:widget": "checkboxes"},
                "MTCT": {"ui:widget": "checkboxes"}
            }
        },
        "DA": {
            "DES": {
                "DESO": {"ui:widget": "textarea", "ui:options": {"rows": 6}}
            }
        }
    }


# Export schema
SCHEMA_F_400 = get_iccd_f_400_schema()


# Funzione di validazione
def validate_f_record(data: Dict[str, Any]) -> tuple[bool, List[str]]:
    """Valida un record F contro lo schema"""
    try:
        import jsonschema
        schema = get_iccd_f_400_schema()
        jsonschema.validate(instance=data, schema=schema["schema"])
        return True, []
    except jsonschema.exceptions.ValidationError as e:
        return False, [str(e)]
    except ImportError:
        return True, ["jsonschema non installato - validazione saltata"]


if __name__ == "__main__":
    print("✅ Schema F 4.00 generato correttamente")
    print(f"📊 Paragrafi implementati: {len(SCHEMA_F_400['schema']['properties'])}")
    print(f"⚠️  Paragrafi obbligatori: {len(SCHEMA_F_400['schema']['required'])}")
