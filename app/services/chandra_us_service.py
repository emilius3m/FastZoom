# app/services/chandra_us_service.py
"""
Servizio OCR con Chandra per importazione PDF schede US
Integrazione con modello UnitaStratigrafica esistente (MiC 2021)
"""

import asyncio
import logging
import re
from pathlib import Path
from typing import Optional, Dict, List, Any
from PIL import Image
import io
import json
from datetime import datetime, date

from loguru import logger

# Import condizionali per Chandra (opzionale)
try:
    from chandra.model import InferenceManager
    from chandra.model.schema import BatchInputItem
    CHANDRA_AVAILABLE = True
except ImportError:
    CHANDRA_AVAILABLE = False
    logger.warning("Chandra OCR non disponibile. Installa con: pip install chandra-ocr")

# Import condizionale per pdf2image
try:
    from pdf2image import convert_from_bytes
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False
    logger.warning("pdf2image non disponibile. Installa con: pip install pdf2image")

from app.models.stratigraphy import TipoUSEnum, ConsistenzaEnum, AffidabilitaEnum


class ChandraUSService:
    """Servizio OCR per schede US con Chandra - integrato con FastZoom"""
    
    def __init__(self, use_gpu: bool = True):
        self.use_gpu = use_gpu
        self.manager = None
        self._model_loaded = False
        logger.info(f"ChandraUSService initialized (GPU: {use_gpu})")
    
    @property
    def is_available(self) -> bool:
        """Verifica se il servizio è disponibile"""
        return CHANDRA_AVAILABLE and PDF2IMAGE_AVAILABLE
    
    def _ensure_model_loaded(self):
        """Lazy loading del modello Chandra"""
        if not CHANDRA_AVAILABLE:
            raise RuntimeError(
                "Chandra OCR non installato. "
                "Installa con: pip install chandra-ocr"
            )
        
        if self.manager is None:
            logger.info("Loading Chandra OCR model...")
            try:
                # Try without device parameter first (newer API)
                self.manager = InferenceManager(method="hf")
            except TypeError as e:
                if "device" in str(e):
                    # Fallback for older API
                    self.manager = InferenceManager(method="hf")
                else:
                    raise
            self._model_loaded = True
            logger.info("Chandra OCR model loaded successfully")
    
    async def extract_from_pdf(
        self, 
        pdf_bytes: bytes, 
        filename: str,
        site_id: str
    ) -> List[Dict]:
        """
        Estrae schede US da PDF con Chandra OCR
        Ritorna dict pronti per il modello UnitaStratigrafica
        
        Args:
            pdf_bytes: Contenuto PDF
            filename: Nome file
            site_id: ID del cantiere archeologico
            
        Returns:
            Lista di dict mappati su UnitaStratigrafica
        """
        if not PDF2IMAGE_AVAILABLE:
            raise RuntimeError(
                "pdf2image non installato. "
                "Installa con: pip install pdf2image. "
                "Inoltre installa Poppler: https://poppler.freedesktop.org/"
            )
        
        self._ensure_model_loaded()
        
        try:
            logger.info(f"Converting PDF {filename} to images...")
            images = convert_from_bytes(pdf_bytes, dpi=300)
            logger.info(f"Found {len(images)} pages in PDF")
            
            sheets = []
            
            for page_num, image in enumerate(images, 1):
                logger.info(f"Processing page {page_num}/{len(images)}...")
                
                try:
                    # Prepara batch per Chandra
                    batch = [BatchInputItem(
                        image=image,
                        prompt_type="ocr_layout"
                    )]
                    
                    # Esegui OCR in thread separato per non bloccare l'event loop
                    loop = asyncio.get_event_loop()
                    results = await loop.run_in_executor(
                        None,
                        self.manager.generate,
                        batch
                    )
                    
                    result = results[0]
                    
                    # Estrai dati strutturati
                    chandra_data = {
                        'page_number': page_num,
                        'markdown': getattr(result, 'markdown', ''),
                        'html': getattr(result, 'html', ''),
                        'text': getattr(result, 'text', ''),
                        'confidence': getattr(result, 'confidence', 0.95)
                    }
                    
                    # Mappa su modello UnitaStratigrafica
                    us_data = self._map_to_unita_stratigrafica(
                        chandra_data, 
                        site_id,
                        filename
                    )
                    
                    if us_data:
                        sheets.append(us_data)
                        logger.info(f"✓ Extracted US {us_data.get('us_code')} from page {page_num}")
                    else:
                        logger.warning(f"No valid US data on page {page_num}")
                
                except Exception as e:
                    logger.error(f"Error processing page {page_num}: {e}")
                    continue
            
            return sheets
        
        except Exception as e:
            logger.error(f"Error in extract_from_pdf: {e}")
            raise
    
    async def extract_from_image(
        self,
        image_bytes: bytes,
        filename: str,
        site_id: str
    ) -> Optional[Dict]:
        """
        Estrae scheda US da singola immagine
        
        Args:
            image_bytes: Contenuto immagine
            filename: Nome file
            site_id: ID del cantiere
            
        Returns:
            Dict mappato su UnitaStratigrafica o None
        """
        self._ensure_model_loaded()
        
        try:
            # Carica immagine
            image = Image.open(io.BytesIO(image_bytes))
            
            # Prepara batch per Chandra
            batch = [BatchInputItem(
                image=image,
                prompt_type="ocr_layout"
            )]
            
            # Esegui OCR
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None,
                self.manager.generate,
                batch
            )
            
            result = results[0]
            
            chandra_data = {
                'page_number': 1,
                'markdown': getattr(result, 'markdown', ''),
                'html': getattr(result, 'html', ''),
                'text': getattr(result, 'text', ''),
                'confidence': getattr(result, 'confidence', 0.95)
            }
            
            return self._map_to_unita_stratigrafica(chandra_data, site_id, filename)
            
        except Exception as e:
            logger.error(f"Error extracting from image: {e}")
            raise
    
    def _map_to_unita_stratigrafica(
        self, 
        chandra_data: Dict,
        site_id: str,
        filename: str
    ) -> Optional[Dict]:
        """
        Mappa output Chandra al modello UnitaStratigrafica
        Rispetta struttura scheda US-3.doc standard MiC 2021
        
        Returns:
            Dict pronto per creare UnitaStratigrafica o None
        """
        text = chandra_data.get('text', '')
        markdown = chandra_data.get('markdown', '')
        
        # ===== IDENTIFICAZIONE US (OBBLIGATORIO) =====
        us_match = re.search(
            r'(?:US|U\.S\.|Unità\s+Stratigrafic[oa])[\s:]*(\d+)',
            text,
            re.IGNORECASE
        )
        if not us_match:
            return None
        
        us_code = f"US{us_match.group(1).zfill(3)}"  # US003
        
        # Inizializza dict mappato
        us_data: Dict[str, Any] = {
            'site_id': site_id,
            'us_code': us_code,
        }
        
        # ===== TIPOLOGIA US =====
        tipo = TipoUSEnum.POSITIVA.value  # Default
        tipo_patterns = {
            TipoUSEnum.NEGATIVA.value: r'\b(?:negativa|taglio|asporto|fossa)\b',
            TipoUSEnum.POSITIVA.value: r'\b(?:positiva|accumulo|deposito|strato)\b'
        }
        for tipo_val, pattern in tipo_patterns.items():
            if re.search(pattern, text, re.IGNORECASE):
                tipo = tipo_val
                break
        us_data['tipo'] = tipo
        
        # ===== INTESTAZIONE =====
        # Ente responsabile
        ente_match = re.search(
            r'(?:ente|responsabile|soprintendenza)[\s:]*([^\n]{10,200})',
            text,
            re.IGNORECASE
        )
        if ente_match:
            us_data['ente_responsabile'] = ente_match.group(1).strip()
        
        # Anno
        anno_match = re.search(r'(?:anno|year)[\s:]*(\d{4})', text, re.IGNORECASE)
        if anno_match:
            us_data['anno'] = int(anno_match.group(1))
        
        # Ufficio MiC
        ufficio_match = re.search(
            r'(?:ufficio\s+mic|ufficio)[\s:]*([^\n]{5,200})',
            text,
            re.IGNORECASE
        )
        if ufficio_match:
            us_data['ufficio_mic'] = ufficio_match.group(1).strip()
        
        # Identificativo riferimento
        rif_match = re.search(
            r'(?:identificativo|riferimento|id)[\s:]*([^\n]{5,200})',
            text,
            re.IGNORECASE
        )
        if rif_match:
            us_data['identificativo_rif'] = rif_match.group(1).strip()
        
        # ===== LOCALIZZAZIONE =====
        # Località
        loc_patterns = [
            r'(?:località|localita|location)[\s:]*([^\n]{5,200})',
            r'(?:comune|municipality)[\s:]*([^\n]{5,200})'
        ]
        for pattern in loc_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                us_data['localita'] = match.group(1).strip()
                break
        
        # Area/Struttura
        area_match = re.search(
            r'(?:area|struttura|settore)[\s:]*([^\n]{5,200})',
            text,
            re.IGNORECASE
        )
        if area_match:
            us_data['area_struttura'] = area_match.group(1).strip()
        
        # Saggio
        saggio_match = re.search(r'(?:saggio|trench)[\s:]*([^\n]{3,100})', text, re.IGNORECASE)
        if saggio_match:
            us_data['saggio'] = saggio_match.group(1).strip()
        
        # Ambiente/Unità/Funzione
        amb_match = re.search(
            r'(?:ambiente|unità|funzione)[\s:]*([^\n]{5,200})',
            text,
            re.IGNORECASE
        )
        if amb_match:
            us_data['ambiente_unita_funzione'] = amb_match.group(1).strip()
        
        # Posizione
        pos_match = re.search(r'(?:posizione|position)[\s:]*([^\n]{5,200})', text, re.IGNORECASE)
        if pos_match:
            us_data['posizione'] = pos_match.group(1).strip()
        
        # Settori
        settori_match = re.search(
            r'(?:settori?|grid)[\s:]*([A-Z0-9, -]+)',
            text,
            re.IGNORECASE
        )
        if settori_match:
            us_data['settori'] = settori_match.group(1).strip()
        
        # ===== DOCUMENTAZIONE (riferimenti testuali) =====
        # Piante
        piante_match = re.search(
            r'(?:piante?|plan)[\s:]*(?:TAV\.?\s*)?([0-9, -]+)',
            text,
            re.IGNORECASE
        )
        if piante_match:
            us_data['piante_riferimenti'] = f"TAV. {piante_match.group(1)}"
        
        # Sezioni
        sezioni_match = re.search(
            r'(?:sezioni?|section)[\s:]*(?:TAV\.?\s*)?([0-9, -]+)',
            text,
            re.IGNORECASE
        )
        if sezioni_match:
            us_data['sezioni_riferimenti'] = f"TAV. {sezioni_match.group(1)}"
        
        # Prospetti
        prospetti_match = re.search(
            r'(?:prospetti?|elevation)[\s:]*(?:TAV\.?\s*)?([0-9, -]+)',
            text,
            re.IGNORECASE
        )
        if prospetti_match:
            us_data['prospetti_riferimenti'] = f"TAV. {prospetti_match.group(1)}"
        
        # ===== DEFINIZIONE E CARATTERIZZAZIONE =====
        # Definizione
        def_patterns = [
            r'(?:definizione|definition)[\s:]*([^\n]{20,500})',
            r'(?:tipo\s+di\s+us|us\s+type)[\s:]*([^\n]{20,500})'
        ]
        for pattern in def_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                us_data['definizione'] = match.group(1).strip()
                break
        
        # Criteri di distinzione
        criteri_match = re.search(
            r'(?:criteri?\s+di\s+distinzione|criteria)[\s:]*([^\n]{20,500})',
            text,
            re.IGNORECASE
        )
        if criteri_match:
            us_data['criteri_distinzione'] = criteri_match.group(1).strip()
        
        # Modo di formazione
        formazione_match = re.search(
            r'(?:modo\s+di\s+formazione|formation)[\s:]*([^\n]{20,500})',
            text,
            re.IGNORECASE
        )
        if formazione_match:
            us_data['modo_formazione'] = formazione_match.group(1).strip()
        
        # ===== COMPONENTI =====
        # Componenti inorganici
        inorg_patterns = [
            r'(?:componenti?\s+inorganic[oi]|elementi?\s+fittil[oi]|elementi?\s+lapide[oi])[\s:]*([^\n]{20,500})',
            r'(?:materiale?\s+ceramic[oa]|framment[oi]\s+ceramic[oi])[\s:]*([^\n]{20,500})'
        ]
        for pattern in inorg_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                us_data['componenti_inorganici'] = match.group(1).strip()
                break
        
        # Componenti organici
        org_match = re.search(
            r'(?:componenti?\s+organic[oi]|ossa|ossei)[\s:]*([^\n]{20,500})',
            text,
            re.IGNORECASE
        )
        if org_match:
            us_data['componenti_organici'] = org_match.group(1).strip()
        
        # ===== PROPRIETÀ FISICHE =====
        # Consistenza (Enum)
        consistenza_map = {
            ConsistenzaEnum.COMPATTA.value: r'\bcompatt[oa]\b',
            ConsistenzaEnum.MEDIA.value: r'\bmedi[oa]\b',
            ConsistenzaEnum.FRIABILE.value: r'\bfriabile\b',
            ConsistenzaEnum.MOLTO_FRIABILE.value: r'\bmolto\s+friabile\b',
            ConsistenzaEnum.SCIOLTA.value: r'\bscioltt?[oa]\b'
        }
        for cons_val, pattern in consistenza_map.items():
            if re.search(pattern, text, re.IGNORECASE):
                us_data['consistenza'] = cons_val
                break
        
        # Colore
        colori = [
            'grigio', 'marrone', 'bruno', 'rosso', 'nero', 'giallo',
            'arancione', 'bianco', 'beige', 'rossastro', 'grigiastro',
            'scuro', 'chiaro'
        ]
        colore_text = []
        for colore in colori:
            if re.search(rf'\b{colore}\b', text, re.IGNORECASE):
                colore_text.append(colore)
        if colore_text:
            us_data['colore'] = ' '.join(colore_text[:3])  # Max 3 colori
        
        # Misure
        misure_patterns = [
            r'(?:misure|dimensioni|dimensions)[\s:]*([0-9x,. m]+)',
            r'(\d+(?:\.\d+)?\s*x\s*\d+(?:\.\d+)?(?:\s*x\s*\d+(?:\.\d+)?)?\s*m)'
        ]
        for pattern in misure_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                us_data['misure'] = match.group(1).strip()
                break
        
        # Stato di conservazione
        cons_patterns = [
            r'(?:stato\s+di\s+conservazione|conservation)[\s:]*([^\n]{10,200})',
            r'(?:conservazione)[\s:]*([^\n]{10,200})'
        ]
        for pattern in cons_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                us_data['stato_conservazione'] = match.group(1).strip()
                break
        
        # ===== SEQUENZA FISICA (MATRIX HARRIS) =====
        sequenza_fisica: Dict[str, List[str]] = {
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
        
        # Estrai relazioni
        relations_map = {
            "copre": [
                r'(?:copre|covers|sta\s+sopra\s+a)[\s:]*(?:US\s*)?([0-9, ]+)',
                r'(?:above)[\s:]*(?:US\s*)?([0-9, ]+)'
            ],
            "coperto_da": [
                r'(?:coperto\s+da|covered\s+by|è\s+sotto\s+a)[\s:]*(?:US\s*)?([0-9, ]+)',
                r'(?:below)[\s:]*(?:US\s*)?([0-9, ]+)'
            ],
            "taglia": [
                r'(?:taglia|cuts)[\s:]*(?:US\s*)?([0-9, ]+)'
            ],
            "tagliato_da": [
                r'(?:tagliato\s+da|cut\s+by)[\s:]*(?:US\s*)?([0-9, ]+)'
            ],
            "riempie": [
                r'(?:riempie|fills)[\s:]*(?:US\s*)?([0-9, ]+)'
            ],
            "riempito_da": [
                r'(?:riempito\s+da|filled\s+by)[\s:]*(?:US\s*)?([0-9, ]+)'
            ],
            "uguale_a": [
                r'(?:uguale\s+a|equals|same\s+as)[\s:]*(?:US\s*)?([0-9, ]+)'
            ],
            "si_lega_a": [
                r'(?:si\s+lega\s+a|bonds\s+to)[\s:]*(?:US\s*)?([0-9, ]+)'
            ],
            "si_appoggia_a": [
                r'(?:si\s+appoggia\s+a|leans\s+on)[\s:]*(?:US\s*)?([0-9, ]+)'
            ],
            "gli_si_appoggia": [
                r'(?:gli\s+si\s+appoggia|is\s+leaned\s+on\s+by)[\s:]*(?:US\s*)?([0-9, ]+)'
            ]
        }
        
        for rel_type, patterns in relations_map.items():
            for pattern in patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                for match in matches:
                    # Estrai numeri US
                    us_numbers = re.findall(r'\d+', match)
                    for num in us_numbers:
                        us_ref = f"US{num.zfill(3)}"
                        if us_ref not in sequenza_fisica[rel_type]:
                            sequenza_fisica[rel_type].append(us_ref)
        
        us_data['sequenza_fisica'] = sequenza_fisica
        
        # ===== DESCRIZIONE E INTERPRETAZIONE =====
        # Descrizione completa
        desc_patterns = [
            r'(?:descrizione|description)[\s:]*([^\n]{50,2000})',
            r'(?:caratteristiche)[\s:]*([^\n]{50,2000})'
        ]
        for pattern in desc_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                us_data['descrizione'] = match.group(1).strip()
                break
        
        # Osservazioni
        oss_match = re.search(
            r'(?:osservazioni|observations|note)[\s:]*([^\n]{20,1000})',
            text,
            re.IGNORECASE
        )
        if oss_match:
            us_data['osservazioni'] = oss_match.group(1).strip()
        
        # Interpretazione
        interp_match = re.search(
            r'(?:interpretazione|interpretation)[\s:]*([^\n]{20,1000})',
            text,
            re.IGNORECASE
        )
        if interp_match:
            us_data['interpretazione'] = interp_match.group(1).strip()
        
        # ===== DATAZIONE E REPERTI =====
        # Datazione
        dat_patterns = [
            r'(?:datazione|dating|cronologia)[\s:]*([^\n]{10,200})',
            r'(?:secolo|century)\s+([IVX]+(?:\s*[-–]\s*[IVX]+)?)',
            r'(\d{1,4}\s*[aA]\.?[cC]\.?\s*[-–]\s*\d{1,4}\s*[dD]\.?[cC]\.?)',
            r'(\d{1,4}\s*[aA]\.?[cC]\.?|\d{1,4}\s*[dD]\.?[cC]\.?)'
        ]
        for pattern in dat_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                us_data['datazione'] = match.group(1).strip()
                break
        
        # Periodo
        periodo_match = re.search(
            r'(?:periodo|period)[\s:]*([^\n]{5,100})',
            text,
            re.IGNORECASE
        )
        if periodo_match:
            us_data['periodo'] = periodo_match.group(1).strip()
        
        # Fase
        fase_match = re.search(r'(?:fase|phase)[\s:]*([^\n]{3,50})', text, re.IGNORECASE)
        if fase_match:
            us_data['fase'] = fase_match.group(1).strip()
        
        # Elementi datanti
        elem_match = re.search(
            r'(?:elementi?\s+datant[ei]|dating\s+elements?)[\s:]*([^\n]{10,500})',
            text,
            re.IGNORECASE
        )
        if elem_match:
            us_data['elementi_datanti'] = elem_match.group(1).strip()
        
        # Dati quantitativi reperti
        reperti_patterns = [
            r'(?:reperti|finds)[\s:]*([^\n]{10,500})',
            r'(\d+\s+(?:frammenti?|fragments?).*?(?:ceramic[ao]|pottery))',
            r'(\d+\s+(?:ossa|bones?))'
        ]
        reperti_text = []
        for pattern in reperti_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            reperti_text.extend(matches)
        if reperti_text:
            us_data['dati_quantitativi_reperti'] = '; '.join(reperti_text[:5])
        
        # ===== CAMPIONATURE =====
        campionature = {
            "flottazione": bool(re.search(r'\bflottazione\b', text, re.IGNORECASE)),
            "setacciatura": bool(re.search(r'\bsetacciatur[ao]\b', text, re.IGNORECASE))
        }
        us_data['campionature'] = campionature
        
        # ===== AFFIDABILITÀ E RESPONSABILITÀ =====
        # Affidabilità
        aff_map = {
            AffidabilitaEnum.ALTA.value: r'\balta\b',
            AffidabilitaEnum.MEDIA.value: r'\bmedi[ao]\b',
            AffidabilitaEnum.BASSA.value: r'\bbassa\b'
        }
        for aff_val, pattern in aff_map.items():
            if re.search(pattern, text, re.IGNORECASE):
                us_data['affidabilita_stratigrafica'] = aff_val
                break
        
        # Responsabile scientifico
        resp_sci_match = re.search(
            r'(?:responsabile\s+scientifico|director)[\s:]*([^\n]{5,200})',
            text,
            re.IGNORECASE
        )
        if resp_sci_match:
            us_data['responsabile_scientifico'] = resp_sci_match.group(1).strip()
        
        # Data rilevamento
        data_ril_match = re.search(
            r'(?:data\s+rilevamento)[\s:]*(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})',
            text,
            re.IGNORECASE
        )
        if data_ril_match:
            try:
                date_str = data_ril_match.group(1)
                parsed = self._parse_date(date_str)
                if parsed:
                    us_data['data_rilevamento'] = parsed.isoformat()
            except Exception:
                pass
        
        # Responsabile compilazione
        resp_comp_match = re.search(
            r'(?:responsabile\s+compilazione|compiled\s+by)[\s:]*([^\n]{5,200})',
            text,
            re.IGNORECASE
        )
        if resp_comp_match:
            us_data['responsabile_compilazione'] = resp_comp_match.group(1).strip()
        
        # Store raw OCR text for reference
        us_data['_raw_ocr_text'] = text[:2000]  # First 2000 chars
        us_data['_extraction_confidence'] = chandra_data.get('confidence', 0.0)
        us_data['_pdf_source'] = filename
        us_data['_page_number'] = chandra_data.get('page_number', 1)
        
        return us_data
    
    def _parse_date(self, date_str: str) -> Optional[date]:
        """Parse date from various formats"""
        formats = ['%d/%m/%Y', '%d-%m-%Y', '%d/%m/%y', '%d-%m-%y']
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except Exception:
                continue
        return None
    
    def validate_extraction_result(self, us_data: Dict) -> Dict[str, Any]:
        """
        Valida il risultato dell'estrazione OCR
        
        Returns:
            Dict con info di validazione
        """
        issues = []
        warnings = []
        
        # Campo obbligatorio
        if not us_data.get('us_code'):
            issues.append("Codice US mancante")
        
        # Campi raccomandati
        recommended_fields = [
            'definizione', 'descrizione', 'datazione', 
            'responsabile_scientifico', 'data_rilevamento'
        ]
        for field in recommended_fields:
            if not us_data.get(field):
                warnings.append(f"Campo raccomandato mancante: {field}")
        
        # Sequenza fisica
        sequenza = us_data.get('sequenza_fisica', {})
        has_relations = any(v for v in sequenza.values() if v)
        if not has_relations:
            warnings.append("Nessuna relazione stratigrafica rilevata")
        
        # Confidence
        confidence = us_data.get('_extraction_confidence', 0)
        if confidence < 0.7:
            warnings.append(f"Confidence OCR bassa: {confidence:.1%}")
        
        return {
            'is_valid': len(issues) == 0,
            'issues': issues,
            'warnings': warnings,
            'confidence': confidence,
            'us_code': us_data.get('us_code'),
            'extracted_fields_count': len([k for k, v in us_data.items() if v and not k.startswith('_')])
        }


# Singleton
_chandra_service: Optional[ChandraUSService] = None


def get_chandra_us_service(use_gpu: bool = True) -> ChandraUSService:
    """Factory per servizio Chandra US"""
    global _chandra_service
    if _chandra_service is None:
        _chandra_service = ChandraUSService(use_gpu=use_gpu)
    return _chandra_service


# Funzione helper per verificare disponibilità
def is_chandra_available() -> bool:
    """Verifica se Chandra OCR è disponibile"""
    return CHANDRA_AVAILABLE and PDF2IMAGE_AVAILABLE
