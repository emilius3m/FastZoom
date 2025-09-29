"""Servizio per validazione schede ICCD secondo standard ministeriali."""

import re
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from loguru import logger

from app.models.iccd_records import ICCDValidationRule


class ICCDValidationError(Exception):
    """Eccezione per errori di validazione ICCD."""
    def __init__(self, field_path: str, message: str, value: Any = None):
        self.field_path = field_path
        self.message = message
        self.value = value
        super().__init__(f"{field_path}: {message}")


class ICCDValidator:
    """Validatore per schede ICCD secondo standard 4.00."""
    
    def __init__(self):
        self.errors: List[ICCDValidationError] = []
        
    def reset_errors(self):
        """Reset lista errori."""
        self.errors = []
    
    def get_errors(self) -> List[Dict[str, Any]]:
        """Restituisce lista errori formattata."""
        return [
            {
                "field_path": error.field_path,
                "message": error.message,
                "value": error.value
            }
            for error in self.errors
        ]
    
    def has_errors(self) -> bool:
        """Verifica se ci sono errori di validazione."""
        return len(self.errors) > 0
    
    def add_error(self, field_path: str, message: str, value: Any = None):
        """Aggiunge un errore di validazione."""
        error = ICCDValidationError(field_path, message, value)
        self.errors.append(error)
        logger.warning(f"ICCD Validation Error: {error}")
    
    def validate_iccd_record(self, schema_type: str, level: str, iccd_data: Dict[str, Any]) -> Tuple[bool, List[Dict[str, Any]]]:
        """
        Valida una scheda ICCD completa.
        
        Args:
            schema_type: Tipo schema (RA, CA, SI, etc.)
            level: Livello catalogazione (P, C, A)
            iccd_data: Dati ICCD da validare
            
        Returns:
            Tuple[bool, List[Dict]]: (is_valid, errors_list)
        """
        self.reset_errors()
        
        # Validazioni strutturali base
        self._validate_structure(schema_type, level, iccd_data)
        
        # Validazioni sezioni specifiche
        if "CD" in iccd_data:
            self._validate_cd_section(iccd_data["CD"], schema_type, level)
        
        if "OG" in iccd_data:
            self._validate_og_section(iccd_data["OG"], schema_type, level)
        
        if "LC" in iccd_data:
            self._validate_lc_section(iccd_data["LC"], schema_type, level)
        
        if "DT" in iccd_data:
            self._validate_dt_section(iccd_data["DT"], schema_type, level)
        
        if "MT" in iccd_data:
            self._validate_mt_section(iccd_data["MT"], schema_type, level)
        
        if "DA" in iccd_data:
            self._validate_da_section(iccd_data["DA"], schema_type, level)
        
        # Validazioni per livello Approfondimento
        if level == "A":
            if "AU" in iccd_data:
                self._validate_au_section(iccd_data["AU"], schema_type, level)
            if "NS" in iccd_data:
                self._validate_ns_section(iccd_data["NS"], schema_type, level)
            if "RS" in iccd_data:
                self._validate_rs_section(iccd_data["RS"], schema_type, level)
        
        return not self.has_errors(), self.get_errors()
    
    def _validate_structure(self, schema_type: str, level: str, iccd_data: Dict[str, Any]):
        """Validazione struttura base scheda ICCD."""
        
        # Sezioni obbligatorie per livello
        required_sections = {
            'P': ['CD', 'OG', 'LC'],  # Precatalogazione
            'C': ['CD', 'OG', 'LC', 'DT', 'MT', 'DA'],  # Catalogazione
            'A': ['CD', 'OG', 'LC', 'DT', 'MT', 'DA', 'AU', 'NS', 'RS']  # Approfondimento
        }
        
        required = required_sections.get(level, [])
        
        for section in required:
            if section not in iccd_data:
                self.add_error(f"root.{section}", f"Sezione {section} obbligatoria per livello {level}")
            elif not iccd_data[section]:
                self.add_error(f"root.{section}", f"Sezione {section} non può essere vuota")
    
    def _validate_cd_section(self, cd_data: Dict[str, Any], schema_type: str, level: str):
        """Validazione sezione CD - CODICI."""
        
        # TSK - Tipo scheda
        if "TSK" not in cd_data:
            self.add_error("CD.TSK", "Tipo scheda obbligatorio")
        elif cd_data["TSK"] != schema_type:
            self.add_error("CD.TSK", f"Tipo scheda deve essere {schema_type}", cd_data["TSK"])
        
        # LIR - Livello ricerca
        if "LIR" not in cd_data:
            self.add_error("CD.LIR", "Livello ricerca obbligatorio")
        elif cd_data["LIR"] not in ["P", "C", "A"]:
            self.add_error("CD.LIR", "Livello ricerca deve essere P, C o A", cd_data["LIR"])
        elif cd_data["LIR"] != level:
            self.add_error("CD.LIR", f"Livello ricerca deve essere {level}", cd_data["LIR"])
        
        # NCT - Codice Univoco
        if "NCT" not in cd_data:
            self.add_error("CD.NCT", "Codice univoco NCT obbligatorio")
        else:
            self._validate_nct(cd_data["NCT"])
        
        # ESC - Ente schedatore
        if "ESC" not in cd_data:
            self.add_error("CD.ESC", "Ente schedatore obbligatorio")
        elif not cd_data["ESC"].strip():
            self.add_error("CD.ESC", "Ente schedatore non può essere vuoto")
    
    def _validate_nct(self, nct_data: Dict[str, Any]):
        """Validazione Codice Univoco NCT."""
        
        # NCTR - Codice regione
        if "NCTR" not in nct_data:
            self.add_error("CD.NCT.NCTR", "Codice regione NCTR obbligatorio")
        else:
            nctr = str(nct_data["NCTR"])
            if not re.match(r"^[0-9]{2}$", nctr):
                self.add_error("CD.NCT.NCTR", "Codice regione deve essere 2 cifre", nctr)
        
        # NCTN - Numero catalogo
        if "NCTN" not in nct_data:
            self.add_error("CD.NCT.NCTN", "Numero catalogo NCTN obbligatorio")
        else:
            nctn = str(nct_data["NCTN"])
            if not re.match(r"^[0-9]{8}$", nctn):
                self.add_error("CD.NCT.NCTN", "Numero catalogo deve essere 8 cifre", nctn)
        
        # NCTS - Suffisso (opzionale)
        if "NCTS" in nct_data and nct_data["NCTS"]:
            ncts = str(nct_data["NCTS"])
            if not re.match(r"^[A-Z]{1,2}$", ncts):
                self.add_error("CD.NCT.NCTS", "Suffisso deve essere 1-2 lettere maiuscole", ncts)
    
    def _validate_og_section(self, og_data: Dict[str, Any], schema_type: str, level: str):
        """Validazione sezione OG - OGGETTO."""
        
        if "OGT" not in og_data:
            self.add_error("OG.OGT", "Sottosezione oggetto OGT obbligatoria")
            return
        
        ogt = og_data["OGT"]
        
        # OGTD - Definizione
        if "OGTD" not in ogt:
            self.add_error("OG.OGT.OGTD", "Definizione oggetto obbligatoria")
        elif not ogt["OGTD"].strip():
            self.add_error("OG.OGT.OGTD", "Definizione oggetto non può essere vuota")
        
        # Validazione terminologia controllata per RA
        if schema_type == "RA" and "OGTD" in ogt:
            valid_definitions = [
                "coppa", "anfora", "lucerna", "fibula", "moneta", "anello", "braccialetto",
                "vaso", "piatto", "ciotola", "bicchiere", "brocca", "bottiglia", "ampolla",
                "statuetta", "rilievo", "stele", "ara", "cippo", "sarcofago", "urna",
                "tegola", "mattone", "tubulo", "peso", "fusaiola", "macina", "mortaio"
            ]
            if ogt["OGTD"].lower() not in valid_definitions:
                logger.warning(f"Definizione oggetto '{ogt['OGTD']}' non in terminologia controllata standard")
    
    def _validate_lc_section(self, lc_data: Dict[str, Any], schema_type: str, level: str):
        """Validazione sezione LC - LOCALIZZAZIONE."""
        
        # PVC - Localizzazione geografico-amministrativa
        if "PVC" not in lc_data:
            self.add_error("LC.PVC", "Localizzazione geografico-amministrativa PVC obbligatoria")
            return
        
        pvc = lc_data["PVC"]
        
        # Campi obbligatori
        required_fields = ["PVCS", "PVCR", "PVCP", "PVCC"]
        field_names = ["Stato", "Regione", "Provincia", "Comune"]
        
        for field, name in zip(required_fields, field_names):
            if field not in pvc:
                self.add_error(f"LC.PVC.{field}", f"{name} obbligatorio")
            elif not pvc[field].strip():
                self.add_error(f"LC.PVC.{field}", f"{name} non può essere vuoto")
        
        # Validazione valori Italia
        if "PVCS" in pvc and pvc["PVCS"] != "Italia":
            logger.warning("Stato diverso da Italia - verificare coerenza dati")
        
        if "PVCR" in pvc and pvc["PVCR"] == "Lazio" and "PVCP" in pvc:
            valid_provinces = ["RM", "FR", "LT", "RI", "VT"]
            if pvc["PVCP"] not in valid_provinces:
                self.add_error("LC.PVC.PVCP", f"Provincia non valida per Lazio: {pvc['PVCP']}")
    
    def _validate_dt_section(self, dt_data: Dict[str, Any], schema_type: str, level: str):
        """Validazione sezione DT - CRONOLOGIA."""
        
        # DTS - Cronologia generica (almeno una obbligatoria)
        has_dts = "DTS" in dt_data and dt_data["DTS"]
        has_dtm = "DTM" in dt_data and dt_data["DTM"]
        
        if not has_dts and not has_dtm:
            self.add_error("DT", "Almeno una datazione (DTS o DTM) obbligatoria")
        
        # Validazione DTS se presente
        if has_dts:
            dts = dt_data["DTS"]
            
            # Validità cronologia
            if "DTSV" in dts:
                valid_values = ["ca.", "?", "ante", "post", "non ante", "non post"]
                if dts["DTSV"] not in valid_values:
                    self.add_error("DT.DTS.DTSV", f"Validità non riconosciuta: {dts['DTSV']}")
        
        # Validazione DTM se presente
        if has_dtm:
            dtm = dt_data["DTM"]
            
            if "DTMA" in dtm and "DTMB" in dtm:
                try:
                    anno_da = int(dtm["DTMA"])
                    anno_a = int(dtm["DTMB"])
                    
                    if anno_da > anno_a:
                        self.add_error("DT.DTM", "Anno iniziale non può essere posteriore all'anno finale")
                    
                    # Range ragionevole per archeologia
                    if anno_da < -3000 or anno_da > 2100:
                        self.add_error("DT.DTM.DTMA", "Anno iniziale fuori range archeologico ragionevole")
                    
                    if anno_a < -3000 or anno_a > 2100:
                        self.add_error("DT.DTM.DTMB", "Anno finale fuori range archeologico ragionevole")
                        
                except (ValueError, TypeError):
                    self.add_error("DT.DTM", "Anni devono essere valori numerici")
    
    def _validate_mt_section(self, mt_data: Dict[str, Any], schema_type: str, level: str):
        """Validazione sezione MT - DATI TECNICI."""
        
        if "MTC" not in mt_data:
            self.add_error("MT.MTC", "Sottosezione materia e tecnica MTC obbligatoria")
            return
        
        mtc = mt_data["MTC"]
        
        # MTCM - Materia (obbligatorio)
        if "MTCM" not in mtc:
            self.add_error("MT.MTC.MTCM", "Materia obbligatoria")
        else:
            materials = mtc["MTCM"]
            valid_materials = [
                "ceramica", "terracotta", "argilla", "bronzo", "ferro", "piombo", 
                "oro", "argento", "marmo", "travertino", "tufo", "legno", "osso", 
                "avorio", "vetro", "ambra", "pasta vitrea", "pietra", "calcare"
            ]
            
            if isinstance(materials, list):
                for material in materials:
                    if material.lower() not in valid_materials:
                        logger.warning(f"Materiale '{material}' non in terminologia controllata standard")
            elif isinstance(materials, str):
                if materials.lower() not in valid_materials:
                    logger.warning(f"Materiale '{materials}' non in terminologia controllata standard")
        
        # Validazione misure se presenti
        if "MIS" in mt_data:
            mis = mt_data["MIS"]
            numeric_fields = ["MISA", "MISL", "MISP", "MISD"]  # Altezza, Larghezza, Profondità, Diametro
            
            for field in numeric_fields:
                if field in mis and mis[field] is not None:
                    try:
                        value = float(mis[field])
                        if value < 0:
                            self.add_error(f"MT.MIS.{field}", "Misura non può essere negativa")
                        elif value > 10000:  # 100 metri sembra un limite ragionevole per reperti archeologici
                            self.add_error(f"MT.MIS.{field}", "Misura eccessivamente grande per un reperto")
                    except (ValueError, TypeError):
                        self.add_error(f"MT.MIS.{field}", "Misura deve essere un valore numerico")
    
    def _validate_da_section(self, da_data: Dict[str, Any], schema_type: str, level: str):
        """Validazione sezione DA - DATI ANALITICI."""
        
        # DES - Descrizione (obbligatoria)
        if "DES" not in da_data:
            self.add_error("DA.DES", "Descrizione DES obbligatoria")
        else:
            des = da_data["DES"]
            
            # DESO - Descrizione oggetto
            if "DESO" not in des:
                self.add_error("DA.DES.DESO", "Descrizione oggetto obbligatoria")
            elif len(des["DESO"].strip()) < 10:
                self.add_error("DA.DES.DESO", "Descrizione oggetto troppo breve (minimo 10 caratteri)")
        
        # STC - Stato di conservazione (obbligatorio)
        if "STC" not in da_data:
            self.add_error("DA.STC", "Stato di conservazione STC obbligatorio")
        else:
            stc = da_data["STC"]
            
            # STCC - Stato di conservazione
            if "STCC" not in stc:
                self.add_error("DA.STC.STCC", "Stato di conservazione obbligatorio")
            else:
                valid_states = ["ottimo", "buono", "discreto", "cattivo", "pessimo"]
                if stc["STCC"] not in valid_states:
                    self.add_error("DA.STC.STCC", f"Stato di conservazione non valido: {stc['STCC']}")
        
        # Validazione iscrizioni se presenti
        if "ISR" in da_data:
            isr = da_data["ISR"]
            
            if "ISRC" in isr:
                valid_classes = ["votiva", "funeraria", "onoraria", "sacra", "profana", "instrumentum domesticum"]
                if isr["ISRC"] not in valid_classes:
                    self.add_error("DA.ISR.ISRC", f"Classe iscrizione non valida: {isr['ISRC']}")
            
            if "ISRL" in isr:
                valid_languages = ["latino", "greco", "etrusco", "osco", "umbro"]
                if isr["ISRL"] not in valid_languages:
                    logger.warning(f"Lingua iscrizione '{isr['ISRL']}' non in elenco standard")
    
    def _validate_au_section(self, au_data: Dict[str, Any], schema_type: str, level: str):
        """Validazione sezione AU - DEFINIZIONE CULTURALE."""
        
        if "AUT" not in au_data:
            self.add_error("AU.AUT", "Ambito culturale AUT obbligatorio per livello A")
        else:
            aut = au_data["AUT"]
            
            if "AUTM" not in aut:
                self.add_error("AU.AUT.AUTM", "Denominazione ambito culturale obbligatoria")
            elif not aut["AUTM"].strip():
                self.add_error("AU.AUT.AUTM", "Denominazione ambito culturale non può essere vuota")
    
    def _validate_ns_section(self, ns_data: Dict[str, Any], schema_type: str, level: str):
        """Validazione sezione NS - NOTIZIE STORICHE."""
        
        if "NSC" in ns_data:
            nsc = ns_data["NSC"]
            
            # Validazione data rinvenimento se presente
            if "NSCD" in nsc and nsc["NSCD"]:
                date_pattern = r"^\d{4}(-\d{2}(-\d{2})?)?$"
                if not re.match(date_pattern, nsc["NSCD"]):
                    self.add_error("NS.NSC.NSCD", "Data rinvenimento formato non valido (YYYY-MM-DD)")
    
    def _validate_rs_section(self, rs_data: Dict[str, Any], schema_type: str, level: str):
        """Validazione sezione RS - FONTI E DOCUMENTI."""
        
        if "RSE" in rs_data:
            rse = rs_data["RSE"]
            
            # Validazione anno realizzazione se presente
            if "RSEC" in rse and rse["RSEC"]:
                try:
                    year = int(rse["RSEC"])
                    current_year = datetime.now().year
                    if year < 1800 or year > current_year:
                        self.add_error("RS.RSE.RSEC", f"Anno realizzazione non plausibile: {year}")
                except (ValueError, TypeError):
                    self.add_error("RS.RSE.RSEC", "Anno realizzazione deve essere un numero di 4 cifre")


class ICCDValidationService:
    """Servizio per gestione validazioni ICCD con regole personalizzabili."""
    
    def __init__(self, db_session: AsyncSession):
        self.db = db_session
        self.validator = ICCDValidator()
    
    async def validate_record(self, schema_type: str, level: str, iccd_data: Dict[str, Any]) -> Tuple[bool, List[Dict[str, Any]]]:
        """
        Valida un record ICCD applicando validazioni standard + regole personalizzate.
        
        Args:
            schema_type: Tipo schema ICCD
            level: Livello catalogazione
            iccd_data: Dati da validare
            
        Returns:
            Tuple[bool, List[Dict]]: (is_valid, errors_list)
        """
        
        # Validazioni standard
        is_valid, errors = self.validator.validate_iccd_record(schema_type, level, iccd_data)
        
        # Applica regole personalizzate dal database
        custom_errors = await self._apply_custom_rules(schema_type, level, iccd_data)
        errors.extend(custom_errors)
        
        return len(errors) == 0, errors
    
    async def _apply_custom_rules(self, schema_type: str, level: str, iccd_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Applica regole di validazione personalizzate dal database."""
        
        try:
            # Recupera regole attive per schema e livello
            rules_query = select(ICCDValidationRule).where(
                ICCDValidationRule.schema_type == schema_type,
                ICCDValidationRule.level == level,
                ICCDValidationRule.is_active == True
            ).order_by(ICCDValidationRule.priority)
            
            result = await self.db.execute(rules_query)
            rules = result.scalars().all()
            
            custom_errors = []
            
            for rule in rules:
                try:
                    error = await self._apply_single_rule(rule, iccd_data)
                    if error:
                        custom_errors.append(error)
                except Exception as e:
                    logger.error(f"Error applying validation rule {rule.id}: {e}")
                    continue
            
            return custom_errors
            
        except Exception as e:
            logger.error(f"Error applying custom validation rules: {e}")
            return []
    
    async def _apply_single_rule(self, rule: ICCDValidationRule, iccd_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Applica una singola regola di validazione personalizzata."""
        
        try:
            # Estrai valore dal path
            value = self._get_value_by_path(iccd_data, rule.field_path)
            
            # Applica regola in base al tipo
            if rule.rule_type == "required":
                if value is None or (isinstance(value, str) and not value.strip()):
                    return {
                        "field_path": rule.field_path,
                        "message": rule.error_message,
                        "value": value
                    }
            
            elif rule.rule_type == "pattern":
                if value and isinstance(value, str):
                    pattern = rule.rule_config.get("pattern", "")
                    if pattern and not re.match(pattern, value):
                        return {
                            "field_path": rule.field_path,
                            "message": rule.error_message,
                            "value": value
                        }
            
            elif rule.rule_type == "enum":
                if value is not None:
                    allowed_values = rule.rule_config.get("values", [])
                    if allowed_values and value not in allowed_values:
                        return {
                            "field_path": rule.field_path,
                            "message": rule.error_message,
                            "value": value
                        }
            
            elif rule.rule_type == "range":
                if value is not None:
                    try:
                        num_value = float(value)
                        min_val = rule.rule_config.get("min")
                        max_val = rule.rule_config.get("max")
                        
                        if min_val is not None and num_value < min_val:
                            return {
                                "field_path": rule.field_path,
                                "message": rule.error_message,
                                "value": value
                            }
                        
                        if max_val is not None and num_value > max_val:
                            return {
                                "field_path": rule.field_path,
                                "message": rule.error_message,
                                "value": value
                            }
                    except (ValueError, TypeError):
                        return {
                            "field_path": rule.field_path,
                            "message": "Valore deve essere numerico",
                            "value": value
                        }
            
            return None
            
        except Exception as e:
            logger.error(f"Error in rule {rule.id} validation: {e}")
            return None
    
    def _get_value_by_path(self, data: Dict[str, Any], path: str) -> Any:
        """Estrae un valore dai dati usando un path (es: 'CD.NCT.NCTR')."""
        
        try:
            keys = path.split('.')
            current = data
            
            for key in keys:
                if isinstance(current, dict) and key in current:
                    current = current[key]
                else:
                    return None
            
            return current
            
        except Exception:
            return None
    
    async def get_validation_summary(self, schema_type: str, level: str) -> Dict[str, Any]:
        """Ottieni riassunto regole di validazione per schema e livello."""
        
        try:
            rules_query = select(ICCDValidationRule).where(
                ICCDValidationRule.schema_type == schema_type,
                ICCDValidationRule.level == level,
                ICCDValidationRule.is_active == True
            ).order_by(ICCDValidationRule.priority)
            
            result = await self.db.execute(rules_query)
            rules = result.scalars().all()
            
            summary = {
                "schema_type": schema_type,
                "level": level,
                "total_rules": len(rules),
                "rules_by_type": {},
                "required_fields": [],
                "rules": []
            }
            
            for rule in rules:
                # Conta per tipo
                rule_type = rule.rule_type
                if rule_type not in summary["rules_by_type"]:
                    summary["rules_by_type"][rule_type] = 0
                summary["rules_by_type"][rule_type] += 1
                
                # Campi obbligatori
                if rule_type == "required":
                    summary["required_fields"].append(rule.field_path)
                
                # Info regola
                summary["rules"].append({
                    "field_path": rule.field_path,
                    "rule_type": rule.rule_type,
                    "name": rule.name,
                    "description": rule.description,
                    "priority": rule.priority
                })
            
            return summary
            
        except Exception as e:
            logger.error(f"Error getting validation summary: {e}")
            return {
                "schema_type": schema_type,
                "level": level,
                "total_rules": 0,
                "rules_by_type": {},
                "required_fields": [],
                "rules": []
            }


# Istanza globale del validatore per uso rapido
iccd_validator = ICCDValidator()

# Funzioni di utilità per validazione rapida
def validate_nct_format(nct_region: str, nct_number: str, nct_suffix: Optional[str] = None) -> Tuple[bool, List[str]]:
    """Validazione rapida formato NCT."""
    errors = []
    
    if not re.match(r"^[0-9]{2}$", nct_region):
        errors.append("Codice regione deve essere 2 cifre")
    
    if not re.match(r"^[0-9]{8}$", nct_number):
        errors.append("Numero catalogo deve essere 8 cifre")
    
    if nct_suffix and not re.match(r"^[A-Z]{1,2}$", nct_suffix):
        errors.append("Suffisso deve essere 1-2 lettere maiuscole")
    
    return len(errors) == 0, errors

def validate_chronology_coherence(start_century: str, end_century: str) -> Tuple[bool, List[str]]:
    """Validazione coerenza cronologica."""
    errors = []
    
    # Mapping secoli a numeri per confronto
    century_mapping = {
        "VIII a.C.": -8, "VII a.C.": -7, "VI a.C.": -6, "V a.C.": -5, "IV a.C.": -4,
        "III a.C.": -3, "II a.C.": -2, "I a.C.": -1, "I d.C.": 1, "II d.C.": 2,
        "III d.C.": 3, "IV d.C.": 4, "V d.C.": 5, "VI d.C.": 6
    }
    
    start_num = century_mapping.get(start_century)
    end_num = century_mapping.get(end_century)
    
    if start_num and end_num and start_num > end_num:
        errors.append("Secolo iniziale non può essere posteriore al secolo finale")
    
    return len(errors) == 0, errors