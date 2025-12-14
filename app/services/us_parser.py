# app/services/us_parser.py
"""
Parser avanzato per schede US standard MiC
Estrae TUTTI i campi dalla scheda US11 e simili
"""

import re
import logging
from typing import Optional, Dict, List
from datetime import datetime, date

from app.models.stratigraphy import TipoUSEnum, ConsistenzaEnum, AffidabilitaEnum

logger = logging.getLogger(__name__)


class USParserComplete:
    """Parser completo per schede US MiC standard"""
    
    def parse_us_sheet(self, text: str, site_id: str, filename: str) -> Optional[Dict]:
        """
        Parse completo di scheda US dal testo OCR
        
        Returns:
            Dict completo mappato su UnitaStratigrafica
        """
        # ===== 1. NUMERO US (OBBLIGATORIO) =====
        us_number = self._extract_us_number(text)
        if not us_number:
            logger.warning("US number not found in text")
            return None
        
        us_code = f"US{us_number.zfill(3)}"
        logger.info(f"Parsing US {us_code}")
        
        # Inizializza struttura
        us_data = {
            'site_id': site_id,
            'us_code': us_code,
        }
        
        # ===== 2. INTESTAZIONE =====
        us_data.update(self._extract_header(text))
        
        # ===== 3. LOCALIZZAZIONE =====
        us_data.update(self._extract_location(text))
        
        # ===== 4. TIPO US =====
        us_data['tipo'] = self._extract_tipo(text)
        
        # ===== 5. DOCUMENTAZIONE (TAVOLE E FOTOGRAFIE) =====
        us_data.update(self._extract_documentation(text))
        
        # ===== 6. DEFINIZIONE E CARATTERIZZAZIONE =====
        us_data.update(self._extract_definition(text))
        
        # ===== 7. COMPONENTI =====
        us_data.update(self._extract_components(text))
        
        # ===== 8. PROPRIETÀ FISICHE =====
        us_data.update(self._extract_physical_properties(text))
        
        # ===== 9. SEQUENZA FISICA (MATRIX HARRIS) =====
        us_data['sequenza_fisica'] = self._extract_harris_matrix(text)
        
        # ===== 10. DESCRIZIONE COMPLETA =====
        us_data.update(self._extract_descriptions(text))
        
        # ===== 11. DATAZIONE E PERIODO =====
        us_data.update(self._extract_dating(text))
        
        # ===== 12. REPERTI =====
        us_data.update(self._extract_finds(text))
        
        # ===== 13. CAMPIONATURE =====
        us_data['campionature'] = self._extract_sampling(text)
        
        # ===== 14. AFFIDABILITÀ E RESPONSABILI =====
        us_data.update(self._extract_responsibility(text))
        
        # ===== 15. METADATA OCR =====
        us_data['_raw_ocr_text'] = text[:2000]
        us_data['_pdf_source'] = filename
        
        return us_data
    
    def _extract_us_number(self, text: str) -> Optional[str]:
        """Estrai numero US"""
        patterns = [
            r'^\s*(\d+)\s*$',  # Riga con solo numero
            r'US[\s:]*(\d+)',
            r'U\.S\.[\s:]*(\d+)',
            r'Unità\s+Stratigrafic[ao][\s:]*(\d+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.MULTILINE | re.IGNORECASE)
            if match:
                return match.group(1)
        return None
    
    def _extract_header(self, text: str) -> Dict:
        """Estrai intestazione (ente, anno, ufficio, identificativo)"""
        data = {}
        
        # Ente responsabile
        ente_match = re.search(
            r'ENTE\s+RESPONSABILE\s*\n\s*([^\n]+)',
            text,
            re.IGNORECASE
        )
        if ente_match:
            data['ente_responsabile'] = ente_match.group(1).strip()
        
        # Anno
        anno_match = re.search(
            r'ANNO\s*\n\s*(\d{4})',
            text,
            re.IGNORECASE
        )
        if anno_match:
            data['anno'] = int(anno_match.group(1))
        
        # Ufficio MiC
        ufficio_match = re.search(
            r'UFFICIO\s+MiC[^\n]*\n\s*([^\n]+)',
            text,
            re.IGNORECASE
        )
        if ufficio_match:
            data['ufficio_mic'] = ufficio_match.group(1).strip()
        
        # Identificativo riferimento
        rif_match = re.search(
            r'IDENTIFICATIVO[^\n]*RIFERIMENTO\s*\n\s*([^\n]+)',
            text,
            re.IGNORECASE
        )
        if rif_match:
            data['identificativo_rif'] = rif_match.group(1).strip()
        
        return data
    
    def _extract_location(self, text: str) -> Dict:
        """Estrai localizzazione completa"""
        data = {}
        
        # Località
        loc_match = re.search(
            r'LOCALITÀ\s*\n\s*([^\n]+)',
            text,
            re.IGNORECASE
        )
        if loc_match:
            data['localita'] = loc_match.group(1).strip()
        
        # Area/Edificio/Struttura
        area_match = re.search(
            r'AREA/EDIFICIO/STRUTTURA\s*\n\s*([^\n]+)',
            text,
            re.IGNORECASE
        )
        if area_match:
            data['area_struttura'] = area_match.group(1).strip()
        
        # Saggio
        saggio_match = re.search(
            r'SAGGIO\s*\n\s*([^\n]+)',
            text,
            re.IGNORECASE
        )
        if saggio_match and saggio_match.group(1).strip():
            data['saggio'] = saggio_match.group(1).strip()
        
        # Ambiente/Unità funzionale
        amb_match = re.search(
            r'AMBIENTE/UNITÀ\s+FUNZIONALE\s*\n\s*([^\n]+)',
            text,
            re.IGNORECASE
        )
        if amb_match:
            data['ambiente_unita_funzione'] = amb_match.group(1).strip()
        
        # Posizione
        pos_match = re.search(
            r'POSIZIONE\s*\n\s*([^\n]+(?:\n[^\n]+)?)',
            text,
            re.IGNORECASE
        )
        if pos_match:
            data['posizione'] = pos_match.group(1).strip()
        
        # Settori
        settori_match = re.search(
            r'SETTORE/I\s*\n\s*([^\n]+)',
            text,
            re.IGNORECASE
        )
        if settori_match and settori_match.group(1).strip():
            data['settori'] = settori_match.group(1).strip()
        
        return data
    
    def _extract_tipo(self, text: str) -> str:
        """Estrai tipo US (positiva/negativa)"""
        # Cerca checkbox POSITIVA
        positiva_match = re.search(
            r'POSITIVA\s*[xX✓✔]',
            text,
            re.IGNORECASE
        )
        
        # Cerca checkbox NEGATIVA
        negativa_match = re.search(
            r'NEGATIVA\s*[xX✓✔]',
            text,
            re.IGNORECASE
        )
        
        if negativa_match:
            return TipoUSEnum.NEGATIVA.value
        else:
            return TipoUSEnum.POSITIVA.value  # Default
    
    def _extract_documentation(self, text: str) -> Dict:
        """Estrai riferimenti documentazione (tavole, fotografie)"""
        data = {}
        
        # Piante
        piante_match = re.search(
            r'PIANTE\s*\n\s*([^\n]+)',
            text,
            re.IGNORECASE
        )
        if piante_match and piante_match.group(1).strip():
            data['piante_riferimenti'] = piante_match.group(1).strip()
        
        # Prospetti
        prospetti_match = re.search(
            r'PROSPETTI\s*\n\s*([^\n]+)',
            text,
            re.IGNORECASE
        )
        if prospetti_match and prospetti_match.group(1).strip():
            data['prospetti_riferimenti'] = prospetti_match.group(1).strip()
        
        # Sezioni
        sezioni_match = re.search(
            r'SEZIONI\s*\n\s*([^\n]+)',
            text,
            re.IGNORECASE
        )
        if sezioni_match and sezioni_match.group(1).strip():
            data['sezioni_riferimenti'] = sezioni_match.group(1).strip()
        
        # Fotografie (può essere multiriga)
        foto_section = re.search(
            r'FOTOGRAFIE\s*\n((?:[^\n]+\n?){1,10}?)(?=RIFERIMENTI|DEFINIZIONE|$)',
            text,
            re.IGNORECASE | re.DOTALL
        )
        if foto_section:
            foto_text = foto_section.group(1).strip()
            # Estrai codici foto (es. DSCF0908)
            foto_codes = re.findall(r'[A-Z]{3,6}\d{4,6}', foto_text)
            if foto_codes:
                data['_fotografie_codes'] = foto_codes  # Metadata temporaneo
        
        return data
    
    def _extract_definition(self, text: str) -> Dict:
        """Estrai definizione e caratterizzazione"""
        data = {}
        
        # Definizione
        def_match = re.search(
            r'DEFINIZIONE\s*\n\s*([^\n]+)',
            text,
            re.IGNORECASE
        )
        if def_match:
            data['definizione'] = def_match.group(1).strip()
        
        # Criteri di distinzione
        criteri_match = re.search(
            r'CRITERI\s+DI\s+DISTINZIONE\s*\n\s*([^\n]+)',
            text,
            re.IGNORECASE
        )
        if criteri_match:
            data['criteri_distinzione'] = criteri_match.group(1).strip()
        
        # Modo di formazione
        modo_match = re.search(
            r'MODO\s+DI\s+FORMAZIONE\s*\n\s*([^\n]+)',
            text,
            re.IGNORECASE
        )
        if modo_match:
            data['modo_formazione'] = modo_match.group(1).strip()
        
        return data
    
    def _extract_components(self, text: str) -> Dict:
        """Estrai componenti organici e inorganici"""
        data = {}
        
        # Componenti inorganici
        inorg_match = re.search(
            r'INORGANICI\s*\n\s*([^\n]+)',
            text,
            re.IGNORECASE
        )
        if inorg_match:
            data['componenti_inorganici'] = inorg_match.group(1).strip()
        
        # Componenti organici
        org_match = re.search(
            r'ORGANICI\s*\n\s*([^\n]+)',
            text,
            re.IGNORECASE
        )
        if org_match:
            data['componenti_organici'] = org_match.group(1).strip()
        
        return data
    
    def _extract_physical_properties(self, text: str) -> Dict:
        """Estrai proprietà fisiche (consistenza, colore, misure, stato)"""
        data = {}
        
        # Consistenza
        cons_match = re.search(
            r'CONSISTENZA\s*\n\s*([^\n]+)',
            text,
            re.IGNORECASE
        )
        if cons_match:
            cons_text = cons_match.group(1).strip().lower()
            
            # Mappa su enum
            if 'compatt' in cons_text:
                data['consistenza'] = ConsistenzaEnum.COMPATTA.value
            elif 'molto friabile' in cons_text or 'molto_friabile' in cons_text:
                data['consistenza'] = ConsistenzaEnum.MOLTO_FRIABILE.value
            elif 'friabile' in cons_text:
                data['consistenza'] = ConsistenzaEnum.FRIABILE.value
            elif 'sciolt' in cons_text:
                data['consistenza'] = ConsistenzaEnum.SCIOLTA.value
            elif 'medi' in cons_text:
                data['consistenza'] = ConsistenzaEnum.MEDIA.value
        
        # Colore
        colore_match = re.search(
            r'COLORE\s*\n\s*([^\n]+)',
            text,
            re.IGNORECASE
        )
        if colore_match:
            data['colore'] = colore_match.group(1).strip()
        
        # Misure
        misure_match = re.search(
            r'MISURE\s*\n\s*([^\n]+)',
            text,
            re.IGNORECASE
        )
        if misure_match:
            data['misure'] = misure_match.group(1).strip()
        
        # Stato di conservazione
        stato_match = re.search(
            r'STATO\s+DI\s+CONSERVAZIONE\s*\n\s*([^\n]+)',
            text,
            re.IGNORECASE
        )
        if stato_match:
            data['stato_conservazione'] = stato_match.group(1).strip()
        
        return data
    
    def _extract_harris_matrix(self, text: str) -> Dict:
        """Estrai matrice di Harris completa"""
        sequenza = {
            "uguale_a": [],
            "si_lega_a": [],
            "gli_si_appoggia": [],
            "si_appoggia_a": [],
            "coperto_da": [],
            "copre": [],
            "tagliato_da": [],
            "taglia": [],
            "riempito_da": [],
            "riempie": []
        }
        
        # Estrai sezione SEQUENZA FISICA
        harris_section = re.search(
            r'SEQUENZA\s+FISICA(.*?)(?=DESCRIZIONE|$)',
            text,
            re.IGNORECASE | re.DOTALL
        )
        
        if not harris_section:
            return sequenza
        
        harris_text = harris_section.group(1)
        
        # Pattern per ogni relazione
        relations_map = {
            "uguale_a": r'UGUALE\s+A\s*\n\s*([^\n]+)',
            "si_lega_a": r'SI\s+LEGA\s+A\s*\n\s*([^\n]+)',
            "gli_si_appoggia": r'GLI\s+SI\s+APPOGGIA\s*\n\s*([^\n]+)',
            "si_appoggia_a": r'SI\s+APPOGGIA\s+A\s*\n\s*([^\n]+)',
            "coperto_da": r'COPERTO\s+DA\s*\n\s*([^\n]+)',
            "copre": r'COPRE\s*\n\s*([^\n]+)',
            "tagliato_da": r'TAGLIATO\s+DA\s*\n\s*([^\n]+)',
            "taglia": r'TAGLIA\s*\n\s*([^\n]+)',
            "riempito_da": r'RIEMPITO\s+DA\s*\n\s*([^\n]+)',
            "riempie": r'RIEMPIE\s*\n\s*([^\n]+)'
        }
        
        for rel_key, pattern in relations_map.items():
            match = re.search(pattern, harris_text, re.IGNORECASE)
            if match and match.group(1).strip():
                values_str = match.group(1).strip()
                
                # Parse valori separati da virgola
                # Es: "228, 229, 230, 231 227(usm)" o "10^, 43^"
                values = re.split(r'[,\s]+', values_str)
                
                for val in values:
                    val = val.strip()
                    if not val:
                        continue
                    
                    # Estrai numero
                    num_match = re.search(r'(\d+)', val)
                    if num_match:
                        num = num_match.group(1)
                        
                        # Determina se è US o USM
                        if 'usm' in val.lower() or '(usm)' in val.lower():
                            us_ref = f"USM{num.zfill(3)}"
                        else:
                            us_ref = f"US{num.zfill(3)}"
                        
                        if us_ref not in sequenza[rel_key]:
                            sequenza[rel_key].append(us_ref)
        
        return sequenza
    
    def _extract_descriptions(self, text: str) -> Dict:
        """Estrai descrizione, osservazioni, interpretazione"""
        data = {}
        
        # Descrizione
        desc_match = re.search(
            r'DESCRIZIONE\s*\n((?:[^\n]+\n?){1,10}?)(?=OSSERVAZIONI|INTERPRETAZIONE|DATAZIONE|$)',
            text,
            re.IGNORECASE | re.DOTALL
        )
        if desc_match:
            data['descrizione'] = desc_match.group(1).strip()
        
        # Osservazioni
        oss_match = re.search(
            r'OSSERVAZIONI\s*\n((?:[^\n]+\n?){1,5}?)(?=INTERPRETAZIONE|DATAZIONE|$)',
            text,
            re.IGNORECASE | re.DOTALL
        )
        if oss_match:
            data['osservazioni'] = oss_match.group(1).strip()
        
        # Interpretazione
        interp_match = re.search(
            r'INTERPRETAZIONE\s*\n((?:[^\n]+\n?){1,10}?)(?=DATAZIONE|PERIODO|FASE|$)',
            text,
            re.IGNORECASE | re.DOTALL
        )
        if interp_match:
            data['interpretazione'] = interp_match.group(1).strip()
        
        return data
    
    def _extract_dating(self, text: str) -> Dict:
        """Estrai datazione, periodo, fase, elementi datanti"""
        data = {}
        
        # Datazione
        dat_match = re.search(
            r'DATAZIONE\s*\n\s*([^\n]+)',
            text,
            re.IGNORECASE
        )
        if dat_match and dat_match.group(1).strip():
            data['datazione'] = dat_match.group(1).strip()
        
        # Periodo
        periodo_match = re.search(
            r'PERIODO\s*\n\s*([^\n]+)',
            text,
            re.IGNORECASE
        )
        if periodo_match and periodo_match.group(1).strip():
            data['periodo'] = periodo_match.group(1).strip()
        
        # Fase
        fase_match = re.search(
            r'FASE\s*\n\s*([^\n]+)',
            text,
            re.IGNORECASE
        )
        if fase_match and fase_match.group(1).strip():
            data['fase'] = fase_match.group(1).strip()
        
        # Elementi datanti
        elem_match = re.search(
            r'ELEMENTI\s+DATANTI\s*\n\s*([^\n]+)',
            text,
            re.IGNORECASE
        )
        if elem_match and elem_match.group(1).strip():
            data['elementi_datanti'] = elem_match.group(1).strip()
        
        return data
    
    def _extract_finds(self, text: str) -> Dict:
        """Estrai dati quantitativi reperti"""
        data = {}
        
        # Dati quantitativi reperti
        reperti_match = re.search(
            r'DATI\s+QUANTITATIVI\s+DEI\s+REPERTI\s*\n((?:[^\n]+\n?){1,5}?)(?=CAMPIONATURE|AFFIDABILITÀ|$)',
            text,
            re.IGNORECASE | re.DOTALL
        )
        if reperti_match:
            data['dati_quantitativi_reperti'] = reperti_match.group(1).strip()
        
        return data
    
    def _extract_sampling(self, text: str) -> Dict:
        """Estrai campionature (flottazione, setacciatura)"""
        campionature = {
            "flottazione": False,
            "setacciatura": False
        }
        
        # Cerca sezione campionature
        camp_section = re.search(
            r'CAMPIONATURE(.*?)(?=AFFIDABILITÀ|RESPONSABILE|$)',
            text,
            re.IGNORECASE | re.DOTALL
        )
        
        if camp_section:
            camp_text = camp_section.group(1)
            
            # Flottazione con checkbox
            if re.search(r'FLOTTAZIONE\s*[xX✓✔]', camp_text, re.IGNORECASE):
                campionature["flottazione"] = True
            
            # Setacciatura con checkbox
            if re.search(r'SETACCIATURA\s*[xX✓✔]', camp_text, re.IGNORECASE):
                campionature["setacciatura"] = True
        
        return campionature
    
    def _extract_responsibility(self, text: str) -> Dict:
        """Estrai affidabilità e responsabili"""
        data = {}
        
        # Affidabilità stratigrafica
        aff_match = re.search(
            r'AFFIDABILITÀ\s+STRATIGRAFICA\s*\n\s*([^\n]+)',
            text,
            re.IGNORECASE
        )
        if aff_match:
            aff_text = aff_match.group(1).strip().lower()
            
            if 'ottima' in aff_text or 'alta' in aff_text:
                data['affidabilita_stratigrafica'] = AffidabilitaEnum.ALTA.value
            elif 'media' in aff_text:
                data['affidabilita_stratigrafica'] = AffidabilitaEnum.MEDIA.value
            elif 'bassa' in aff_text:
                data['affidabilita_stratigrafica'] = AffidabilitaEnum.BASSA.value
        
        # Responsabile scientifico
        resp_sci_match = re.search(
            r'RESPONSABILE\s+SCIENTIFICO\s+DELLE\s+INDAGINI\s*\n\s*([^\n]+)',
            text,
            re.IGNORECASE
        )
        if resp_sci_match:
            data['responsabile_scientifico'] = resp_sci_match.group(1).strip()
        
        # Data rilevamento
        data_ril_match = re.search(
            r'DATA\s+RILEVAMENTO\s+SUL\s+CAMPO\s*\n\s*(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})',
            text,
            re.IGNORECASE
        )
        if data_ril_match:
            try:
                date_str = data_ril_match.group(1)
                data['data_rilevamento'] = self._parse_date(date_str)
            except:
                pass
        
        # Responsabile compilazione
        resp_comp_match = re.search(
            r'RESPONSABILE\s+COMPILAZIONE\s+SUL\s+CAMPO\s*\n\s*([^\n]+)',
            text,
            re.IGNORECASE
        )
        if resp_comp_match:
            data['responsabile_compilazione'] = resp_comp_match.group(1).strip()
        
        # Data rielaborazione
        data_rielab_match = re.search(
            r'DATA\s+RIELABORAZIONE\s*\n\s*(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})',
            text,
            re.IGNORECASE
        )
        if data_rielab_match:
            try:
                date_str = data_rielab_match.group(1)
                data['data_rielaborazione'] = self._parse_date(date_str)
            except:
                pass
        
        # Responsabile rielaborazione
        resp_rielab_match = re.search(
            r'RESPONSABILE\s+RIELABORAZIONE\s*\n\s*([^\n]+)',
            text,
            re.IGNORECASE
        )
        if resp_rielab_match:
            data['responsabile_rielaborazione'] = resp_rielab_match.group(1).strip()
        
        return data
    
    def _parse_date(self, date_str: str) -> Optional[date]:
        """Parse date da formato italiano"""
        formats = ['%d/%m/%Y', '%d-%m-%Y', '%d/%m/%y', '%d-%m-%y']
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except:
                continue
        return None


# Singleton parser
_us_parser: Optional[USParserComplete] = None

def get_us_parser() -> USParserComplete:
    """Factory per parser US"""
    global _us_parser
    if _us_parser is None:
        _us_parser = USParserComplete()
    return _us_parser
