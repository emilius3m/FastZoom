"""
Template ICCD Completi - Schema 3.00
Conforme a normativa ufficiale ICCD MiC 2025

Tutti gli schema ICCD supportati con validazione completa
"""

# Import di tutti gli schema completi
from app.data.iccd_si_schema_complete import SCHEMA_SI_300, get_iccd_si_300_schema, validate_si_record
from app.data.iccd_ra_schema_complete import SCHEMA_RA_300, get_iccd_ra_300_schema, validate_ra_record
from app.data.iccd_ca_schema_complete import SCHEMA_CA_300, get_iccd_ca_300_schema, validate_ca_record
from app.data.iccd_ma_schema_complete import SCHEMA_MA_300, get_iccd_ma_300_schema, validate_ma_record
from app.data.iccd_f_schema_complete import SCHEMA_F_300, get_iccd_f_400_schema, validate_f_record


# Esporta tutti gli schema
__all__ = [
    'SCHEMA_SI_300', 'get_iccd_si_300_schema', 'validate_si_record',
    'SCHEMA_RA_300', 'get_iccd_ra_300_schema', 'validate_ra_record',
    'SCHEMA_CA_300', 'get_iccd_ca_300_schema', 'validate_ca_record',
    'SCHEMA_F_400', 'get_iccd_f_400_schema', 'validate_f_record',
    'SCHEMA_MA_300', 'get_iccd_ma_300_schema', 'validate_ma_record'
]


#Ho implementato la scheda F 4.00 completa con:

#✅ 23 paragrafi totali
#✅ 8 paragrafi obbligatori: CD, OG, MT, CO, TU, DO, AD, CM
#✅ Materiali fotografici: carta, vetro, pellicola, digitale
#✅ Tecniche: albumina, dagherrotipo, gelatina, stampa digitale
#✅ Autore fotografia e studio/atelier
#✅ Luogo e data di ripresa
#✅ Soggetto e descrizione iconografica
#✅ Gestione fondi fotografici
#✅ Mostre ed eventi