"""Servizio per integrazione schemi ICCD con sistema form schemas FastZoom."""

import json
from datetime import datetime
from typing import Dict, Any, List, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from loguru import logger

from app.models.form_schemas import FormSchema
from app.data.iccd_templates import SCHEMA_SI_300, SCHEMA_RA_300, SCHEMA_CA_300
from app.data.iccd_ma_schema_complete import get_iccd_ma_300_schema


# Template mapping based on complete schemas
# Get MA schema
SCHEMA_MA_300 = get_iccd_ma_300_schema()

ICCD_TEMPLATES = {
    "SI": {
        "name": "ICCD SI 3.00 - Siti Archeologici",
        "description": "Schema standard ICCD per catalogazione siti archeologici (v. 3.00) - COMPLETO 15 paragrafi",
        "category": "siti_archeologici",
        "icon": "🗺️",
        "schema": SCHEMA_SI_300["schema"],
        "ui_schema": SCHEMA_SI_300["ui_schema"]
    },
    "RA": {
        "name": "ICCD RA 3.00 - Reperti Archeologici",
        "description": "Schema standard ICCD per catalogazione reperti archeologici (v. 3.00) - COMPLETO 21 paragrafi",
        "category": "reperti_archeologici",
        "icon": "🏺",
        "schema": SCHEMA_RA_300["schema"],
        "ui_schema": SCHEMA_RA_300["ui_schema"]
    },
    "CA": {
        "name": "ICCD CA 3.00 - Complessi Archeologici",
        "description": "Schema standard ICCD per catalogazione complessi archeologici (v. 3.00) - COMPLETO 23 paragrafi",
        "category": "complessi_archeologici",
        "icon": "🏛️",
        "schema": SCHEMA_CA_300["schema"],
        "ui_schema": SCHEMA_CA_300["ui_schema"]
    },
    "MA": {
        "name": "ICCD MA 3.00 - Monumenti Archeologici",
        "description": "Schema standard ICCD per catalogazione monumenti archeologici (v. 3.00) - COMPLETO 23 paragrafi",
        "category": "monumenti_archeologici",
        "icon": "🏛️",
        "schema": SCHEMA_MA_300["schema"],
        "ui_schema": SCHEMA_MA_300["ui_schema"]
    }
}

def get_template_by_type(schema_type: str):
    """Recupera template ICCD per tipo schema."""
    return ICCD_TEMPLATES.get(schema_type.upper())


class ICCDIntegrationService:
    """Servizio per integrazione standard ICCD con FastZoom."""
    
    def __init__(self, db_session: AsyncSession):
        self.db = db_session
    
    async def initialize_iccd_templates(self, site_id: UUID, user_id: UUID) -> Dict[str, Any]:
        """
        Inizializza template ICCD standard nel sistema FastZoom (ora solo FormSchema).
        Gli schemi ICCD sono definiti direttamente nel codice Python.
        
        Args:
            site_id: ID del sito archeologico
            user_id: ID dell'utente che esegue l'inizializzazione
            
        Returns:
            Dict con risultati dell'inizializzazione
        """
        
        try:
            created_templates = []
            errors = []
            
            # Itera sui template ICCD disponibili
            for schema_type, template_data in ICCD_TEMPLATES.items():
                try:
                    # Crea FormSchema per compatibilità con sistema esistente
                    await self._create_form_schema_from_iccd(
                        template_data, schema_type, site_id, user_id
                    )
                    created_templates.append(schema_type)
                    logger.info(f"Created ICCD FormSchema: {schema_type}")
                    
                except Exception as e:
                    error_msg = f"Error processing template {schema_type}: {str(e)}"
                    errors.append(error_msg)
                    logger.error(error_msg)
                    continue
            
            # Commit delle modifiche
            await self.db.commit()
            
            result = {
                "success": True,
                "created_templates": created_templates,
                "updated_templates": [],  # Non più necessario
                "total_processed": len(created_templates),
                "errors": errors
            }
            
            logger.info(f"ICCD templates initialization completed: {result}")
            return result
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error initializing ICCD templates: {e}")
            return {
                "success": False,
                "created_templates": [],
                "updated_templates": [],
                "total_processed": 0,
                "errors": [str(e)]
            }
    
    async def _create_form_schema_from_iccd(
        self, 
        template_data: Dict[str, Any], 
        schema_type: str, 
        site_id: UUID, 
        user_id: UUID
    ):
        """Crea FormSchema dal template ICCD per compatibilità."""
        
        try:
            # Verifica se FormSchema ICCD esiste già per questo sito
            existing_form = await self.db.execute(
                select(FormSchema).where(
                    and_(
                        FormSchema.site_id == site_id,
                        FormSchema.name == template_data['name']
                    )
                )
            )
            existing_form = existing_form.scalar_one_or_none()
            
            if not existing_form:
                # Crea FormSchema compatibile
                form_schema = FormSchema(
                    name=template_data['name'],
                    description=template_data['description'],
                    category=template_data['category'],
                    schema_json=json.dumps(template_data['schema']),
                    site_id=site_id,
                    created_by=user_id,
                    is_active=True
                )
                
                self.db.add(form_schema)
                logger.info(f"Created FormSchema for ICCD {schema_type} in site {site_id}")
            
        except Exception as e:
            logger.error(f"Error creating FormSchema for ICCD {schema_type}: {e}")
    
    async def get_iccd_schema_for_site(self, site_id: UUID, schema_type: str) -> Optional[Dict[str, Any]]:
        """
        Ottieni schema ICCD configurato per un sito specifico direttamente dal codice Python.
        
        Args:
            site_id: ID del sito archeologico
            schema_type: Tipo schema ICCD (RA, CA, SI, etc.)
            
        Returns:
            Dict con schema configurato o None se non trovato
        """
        
        try:
            # Ottieni template direttamente dal codice Python
            template_data = get_template_by_type(schema_type)
            
            if not template_data:
                logger.warning(f"ICCD template {schema_type} not found in code")
                return None
            
            # Personalizza template per il sito (es. valori di default)
            customized_schema = template_data["schema"].copy()
            
            # Aggiorna valori di default per il sito
            if "properties" in customized_schema and "LC" in customized_schema["properties"]:
                lc_props = customized_schema["properties"]["LC"]["properties"]
                if "PVL" in lc_props and "properties" in lc_props["PVL"]:
                    # Qui potresti aggiungere logica per recuperare il nome del sito dal database
                    # Per ora usiamo un valore generico
                    lc_props["PVL"]["properties"]["PVLN"]["default"] = "Sito Archeologico"
            
            return {
                "id": f"iccd_{schema_type.lower()}",
                "schema_type": schema_type,
                "name": template_data["name"],
                "description": template_data["description"],
                "version": "3.00",
                "category": template_data["category"],
                "icon": template_data["icon"],
                "json_schema": customized_schema,
                "ui_schema": template_data["ui_schema"],
                "standard_compliant": True
            }
            
        except Exception as e:
            logger.error(f"Error getting ICCD schema for site {site_id}, type {schema_type}: {e}")
            return None
    
    async def convert_iccd_to_form_data(self, iccd_data: Dict[str, Any], schema_type: str) -> Dict[str, Any]:
        """
        Converte dati ICCD in formato compatibile con FormSchema standard.
        
        Args:
            iccd_data: Dati ICCD strutturati
            schema_type: Tipo schema ICCD
            
        Returns:
            Dict con dati convertiti per form builder
        """
        
        try:
            # Struttura di base per form builder
            form_data = {
                "schema_type": "iccd_" + schema_type.lower(),
                "metadata": {
                    "iccd_compliant": True,
                    "iccd_schema_type": schema_type,
                    "iccd_level": iccd_data.get("CD", {}).get("LIR", "C"),
                    "nct": self._extract_nct(iccd_data),
                    "object_name": self._extract_object_name(iccd_data),
                    "material": self._extract_material(iccd_data),
                    "chronology": self._extract_chronology(iccd_data),
                    "conservation_status": self._extract_conservation_status(iccd_data)
                },
                "sections": {}
            }
            
            # Converte sezioni ICCD
            for section_code, section_data in iccd_data.items():
                if isinstance(section_data, dict):
                    form_data["sections"][section_code] = self._convert_section_to_form(
                        section_code, section_data, schema_type
                    )
            
            return form_data
            
        except Exception as e:
            logger.error(f"Error converting ICCD data to form data: {e}")
            return {
                "schema_type": "iccd_" + schema_type.lower(),
                "metadata": {"iccd_compliant": True, "conversion_error": str(e)},
                "sections": {}
            }
    
    def _extract_nct(self, iccd_data: Dict[str, Any]) -> str:
        """Estrae codice NCT dai dati ICCD."""
        try:
            nct = iccd_data.get("CD", {}).get("NCT", {})
            region = nct.get("NCTR", "")
            number = nct.get("NCTN", "")
            suffix = nct.get("NCTS", "")
            return f"{region}{number}{suffix}"
        except:
            return ""
    
    def _extract_object_name(self, iccd_data: Dict[str, Any]) -> str:
        """Estrae nome oggetto dai dati ICCD."""
        try:
            return iccd_data.get("OG", {}).get("OGT", {}).get("OGTD", "")
        except:
            return ""
    
    def _extract_material(self, iccd_data: Dict[str, Any]) -> str:
        """Estrae materiale dai dati ICCD."""
        try:
            materials = iccd_data.get("MT", {}).get("MTC", {}).get("MTCM", [])
            if isinstance(materials, list):
                return ", ".join(materials)
            return str(materials) if materials else ""
        except:
            return ""
    
    def _extract_chronology(self, iccd_data: Dict[str, Any]) -> str:
        """Estrae cronologia dai dati ICCD."""
        try:
            dts = iccd_data.get("DT", {}).get("DTS", {})
            start = dts.get("DTSI", "")
            end = dts.get("DTSF", "")
            if start == end:
                return start
            return f"{start} - {end}" if start and end else start or end
        except:
            return ""
    
    def _extract_conservation_status(self, iccd_data: Dict[str, Any]) -> str:
        """Estrae stato di conservazione dai dati ICCD."""
        try:
            return iccd_data.get("DA", {}).get("STC", {}).get("STCC", "")
        except:
            return ""
    
    def _convert_section_to_form(self, section_code: str, section_data: Dict[str, Any], schema_type: str) -> Dict[str, Any]:
        """Converte una sezione ICCD in formato form builder."""
        
        section_names = {
            "CD": "Codici",
            "OG": "Oggetto", 
            "LC": "Localizzazione",
            "DT": "Cronologia",
            "MT": "Dati Tecnici",
            "DA": "Dati Analitici",
            "AU": "Definizione Culturale",
            "NS": "Notizie Storiche",
            "RS": "Fonti e Documenti"
        }
        
        return {
            "code": section_code,
            "name": section_names.get(section_code, section_code),
            "data": section_data,
            "required": section_code in ["CD", "OG", "LC"],  # Sezioni sempre obbligatorie
            "iccd_compliant": True
        }
    
    async def create_default_iccd_schemas_for_site(self, site_id: UUID, user_id: UUID) -> Dict[str, Any]:
        """
        Crea gli schemi ICCD di default per un nuovo sito archeologico.
        
        Args:
            site_id: ID del sito archeologico
            user_id: ID dell'utente che crea gli schemi
            
        Returns:
            Dict con risultati della creazione
        """
        
        try:
            created_schemas = []
            errors = []
            
            # Schemi ICCD da creare per default
            default_schemas = ["RA", "CA", "SI", "MA"]
            
            for schema_type in default_schemas:
                try:
                    template_data = get_template_by_type(schema_type)
                    if not template_data:
                        errors.append(f"Template {schema_type} non trovato")
                        continue
                    
                    # Verifica se FormSchema esiste già
                    existing = await self.db.execute(
                        select(FormSchema).where(
                            and_(
                                FormSchema.site_id == site_id,
                                FormSchema.name == template_data['name']
                            )
                        )
                    )
                    
                    if existing.scalar_one_or_none():
                        logger.info(f"ICCD FormSchema {schema_type} already exists for site {site_id}")
                        continue
                    
                    # Crea nuovo FormSchema ICCD
                    form_schema = FormSchema(
                        name=template_data['name'],
                        description=template_data['description'],
                        category=template_data['category'],
                        schema_json=json.dumps({
                            **template_data['schema'],
                            "iccd_metadata": {
                                "schema_type": schema_type,
                                "standard_version": "4.00",
                                "ministerial_compliant": True,
                                "created_for_site": str(site_id)
                            }
                        }),
                        site_id=site_id,
                        created_by=user_id,
                        is_active=True
                    )
                    
                    self.db.add(form_schema)
                    created_schemas.append(schema_type)
                    
                    logger.info(f"Created ICCD FormSchema {schema_type} for site {site_id}")
                    
                except Exception as e:
                    error_msg = f"Error creating {schema_type} schema: {str(e)}"
                    errors.append(error_msg)
                    logger.error(error_msg)
                    continue
            
            await self.db.commit()
            
            return {
                "success": True,
                "created_schemas": created_schemas,
                "total_created": len(created_schemas),
                "errors": errors,
                "message": f"Creati {len(created_schemas)} schemi ICCD per il sito"
            }
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error creating default ICCD schemas: {e}")
            return {
                "success": False,
                "created_schemas": [],
                "total_created": 0,
                "errors": [str(e)],
                "message": "Errore durante la creazione degli schemi ICCD"
            }
    
    async def get_iccd_compatible_schemas(self, site_id: UUID) -> List[Dict[str, Any]]:
        """
        Ottieni tutti gli schemi compatibili ICCD per un sito.
        
        Args:
            site_id: ID del sito archeologico
            
        Returns:
            Lista di schemi compatibili ICCD
        """
        
        try:
            # Query FormSchema con metadati ICCD
            schemas_query = select(FormSchema).where(
                and_(
                    FormSchema.site_id == site_id,
                    FormSchema.is_active == True
                )
            ).order_by(FormSchema.category, FormSchema.name)
            
            schemas = await self.db.execute(schemas_query)
            schemas = schemas.scalars().all()
            
            iccd_schemas = []
            
            for schema in schemas:
                try:
                    schema_json = json.loads(schema.schema_json)
                    
                    # Verifica se è schema ICCD
                    iccd_metadata = schema_json.get("iccd_metadata")
                    if iccd_metadata and iccd_metadata.get("ministerial_compliant"):
                        iccd_schemas.append({
                            "id": str(schema.id),
                            "name": schema.name,
                            "description": schema.description,
                            "category": schema.category,
                            "schema_type": iccd_metadata.get("schema_type"),
                            "standard_version": iccd_metadata.get("standard_version"),
                            "json_schema": schema_json,
                            "created_at": schema.created_at.isoformat(),
                            "updated_at": schema.updated_at.isoformat(),
                            "is_iccd_compliant": True
                        })
                        
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON in FormSchema {schema.id}")
                    continue
            
            return iccd_schemas
            
        except Exception as e:
            logger.error(f"Error getting ICCD compatible schemas: {e}")
            return []
    
    async def validate_iccd_integration(self, site_id: UUID) -> Dict[str, Any]:
        """
        Valida l'integrazione ICCD per un sito.
        
        Args:
            site_id: ID del sito archeologico
            
        Returns:
            Dict con risultati della validazione
        """
        
        try:
            validation_results = {
                "site_id": str(site_id),
                "iccd_templates_available": len(ICCD_TEMPLATES),  # Sempre disponibili dal codice
                "form_schemas_available": 0,
                "iccd_records_count": 0,
                "integration_status": "unknown",
                "issues": [],
                "recommendations": []
            }
            
            # Verifica FormSchema ICCD per il sito
            iccd_schemas = await self.get_iccd_compatible_schemas(site_id)
            validation_results["form_schemas_available"] = len(iccd_schemas)
            
            # Verifica record ICCD esistenti
            from app.models.iccd_records import ICCDRecord
            records_count = await self.db.execute(
                select(ICCDRecord).where(ICCDRecord.site_id == site_id)
            )
            validation_results["iccd_records_count"] = len(records_count.scalars().all())
            
            # Determina status integrazione (template sempre disponibili dal codice)
            if validation_results["form_schemas_available"] == 0:
                validation_results["integration_status"] = "missing_form_schemas"
                validation_results["issues"].append("FormSchema ICCD non creati per questo sito")
                validation_results["recommendations"].append("Creare FormSchema ICCD per il sito")
                
            elif validation_results["iccd_records_count"] == 0:
                validation_results["integration_status"] = "ready_for_cataloging"
                validation_results["recommendations"].append("Sistema pronto per catalogazione ICCD")
                
            else:
                validation_results["integration_status"] = "active"
                validation_results["recommendations"].append("Sistema ICCD attivo e funzionante")
            
            return validation_results
            
        except Exception as e:
            logger.error(f"Error validating ICCD integration: {e}")
            return {
                "site_id": str(site_id),
                "integration_status": "error",
                "issues": [str(e)],
                "recommendations": ["Contattare l'amministratore di sistema"]
            }
    
    async def sync_iccd_with_archaeological_data(self, site_id: UUID) -> Dict[str, Any]:
        """
        Sincronizza dati ICCD con ArchaeologicalData esistenti.
        
        Args:
            site_id: ID del sito archeologico
            
        Returns:
            Dict con risultati della sincronizzazione
        """
        
        try:
            from app.models.archaeological_plans import ArchaeologicalData
            from app.models.iccd_records import ICCDRecord
            
            sync_results = {
                "success": True,
                "processed_records": 0,
                "created_archaeological_data": 0,
                "errors": []
            }
            
            # Ottieni record ICCD del sito
            iccd_records = await self.db.execute(
                select(ICCDRecord).where(ICCDRecord.site_id == site_id)
            )
            iccd_records = iccd_records.scalars().all()
            
            for record in iccd_records:
                try:
                    # Verifica se esiste già ArchaeologicalData corrispondente
                    existing_data = await self.db.execute(
                        select(ArchaeologicalData).where(
                            and_(
                                ArchaeologicalData.site_id == site_id,
                                ArchaeologicalData.data.contains({"iccd_record_id": str(record.id)})
                            )
                        )
                    )
                    
                    if existing_data.scalar_one_or_none():
                        continue  # Già sincronizzato
                    
                    # Trova FormSchema ICCD appropriato
                    iccd_form_schema = await self.db.execute(
                        select(FormSchema).where(
                            and_(
                                FormSchema.site_id == site_id,
                                FormSchema.name.contains(record.schema_type)
                            )
                        )
                    )
                    iccd_form_schema = iccd_form_schema.scalar_one_or_none()
                    
                    if iccd_form_schema:
                        # Crea ArchaeologicalData dal record ICCD
                        archaeological_data = ArchaeologicalData(
                            site_id=site_id,
                            plan_id=None,  # Da associare manualmente se necessario
                            module_id=iccd_form_schema.id,
                            coordinates_x=0.0,  # Da georeferenziare manualmente
                            coordinates_y=0.0,
                            data={
                                "iccd_record_id": str(record.id),
                                "iccd_nct": record.get_nct(),
                                "iccd_schema_type": record.schema_type,
                                "iccd_level": record.level,
                                "object_name": record.get_object_name(),
                                "material": record.get_material(),
                                "chronology": record.get_chronology(),
                                "conservation_status": record.get_conservation_status(),
                                "full_iccd_data": record.iccd_data,
                                "sync_timestamp": datetime.utcnow().isoformat()
                            },
                            collector_id=record.created_by,
                            collection_method="iccd_import",
                            is_validated=record.is_validated
                        )
                        
                        self.db.add(archaeological_data)
                        sync_results["created_archaeological_data"] += 1
                    
                    sync_results["processed_records"] += 1
                    
                except Exception as e:
                    error_msg = f"Error syncing record {record.get_nct()}: {str(e)}"
                    sync_results["errors"].append(error_msg)
                    logger.error(error_msg)
                    continue
            
            await self.db.commit()
            
            logger.info(f"ICCD sync completed for site {site_id}: {sync_results}")
            return sync_results
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error syncing ICCD with archaeological data: {e}")
            return {
                "success": False,
                "processed_records": 0,
                "created_archaeological_data": 0,
                "errors": [str(e)]
            }


# Funzioni di utilità globali
async def ensure_iccd_templates_exist(db: AsyncSession) -> bool:
    """Assicura che i template ICCD siano disponibili (ora dal codice Python)."""
    
    try:
        # I template sono sempre disponibili dal codice Python
        return len(ICCD_TEMPLATES) > 0
        
    except Exception as e:
        logger.error(f"Error ensuring ICCD templates exist: {e}")
        return False

async def auto_setup_iccd_for_new_site(site_id: UUID, user_id: UUID, db: AsyncSession) -> Dict[str, Any]:
    """
    Configurazione automatica ICCD per nuovo sito archeologico.
    
    Args:
        site_id: ID del nuovo sito
        user_id: ID dell'utente che crea il sito
        db: Sessione database
        
    Returns:
        Dict con risultati della configurazione
    """
    
    try:
        service = ICCDIntegrationService(db)
        
        # 1. Template ICCD sempre disponibili dal codice Python
        templates_available = await ensure_iccd_templates_exist(db)
        
        # 2. Crea FormSchema ICCD per il sito
        setup_result = await service.create_default_iccd_schemas_for_site(site_id, user_id)
        
        # 3. Valida integrazione
        validation_result = await service.validate_iccd_integration(site_id)
        
        return {
            "success": setup_result["success"] and templates_available,
            "setup_result": setup_result,
            "validation_result": validation_result,
            "iccd_enabled": validation_result["integration_status"] in ["ready_for_cataloging", "active"]
        }
        
    except Exception as e:
        logger.error(f"Error in auto-setup ICCD for site {site_id}: {e}")
        return {
            "success": False,
            "setup_result": {"errors": [str(e)]},
            "validation_result": {"integration_status": "error"},
            "iccd_enabled": False
        }