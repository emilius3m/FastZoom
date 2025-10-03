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


# Esporta tutti gli schema
__all__ = [
    'SCHEMA_SI_300', 'get_iccd_si_300_schema', 'validate_si_record',
    'SCHEMA_RA_300', 'get_iccd_ra_300_schema', 'validate_ra_record',
    'SCHEMA_CA_300', 'get_iccd_ca_300_schema', 'validate_ca_record',
    'SCHEMA_MA_300', 'get_iccd_ma_300_schema', 'validate_ma_record'
]
