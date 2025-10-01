"""
Scheda ICCD SI 3.00 - Siti Archeologici COMPLETA
Conforme a normativa ufficiale ICCD MiC 2025

Basato su:
- ICCD_SI_3.00-2.xls (normativa ufficiale)
- ICCD_La-scheda-SI-Siti-archeologici_versione-3.00-1.pdf

Tutti i 24 paragrafi implementati
Paragrafi obbligatori: CD, OG, LC, DT, TU, DO, AD, CM
"""

from app.data.iccd_si_schema_complete import SCHEMA_SI_300, get_iccd_si_300_schema, validate_si_record

# Esporta lo schema aggiornato
__all__ = ['SCHEMA_SI_300', 'get_iccd_si_300_schema', 'validate_si_record']
