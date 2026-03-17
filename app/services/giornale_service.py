from typing import List, Dict, Any, Optional
from uuid import UUID
from datetime import date, time, datetime
import hashlib
import json
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.repositories.giornale_repository import GiornaleRepository
from app.models.giornale_cantiere import GiornaleCantiere
from app.models.users import User

class GiornaleService:
    def __init__(self, db_session: AsyncSession):
        self.repository = GiornaleRepository(db_session)
        self.db = db_session

    @staticmethod
    def _normalize_allegati_paths_for_db(value: Any) -> Optional[str]:
        """Normalizza allegati_paths in JSON string per persistenza su colonna TEXT."""
        if value is None:
            return None

        def _clean(items: List[Any]) -> List[str]:
            return [str(item).strip() for item in items if item is not None and str(item).strip()]

        if isinstance(value, list):
            return json.dumps(_clean(value), ensure_ascii=False)

        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return json.dumps([], ensure_ascii=False)

            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return json.dumps(_clean(parsed), ensure_ascii=False)
                if isinstance(parsed, str) and parsed.strip():
                    return json.dumps([parsed.strip()], ensure_ascii=False)
            except Exception:
                pass

            return json.dumps([raw], ensure_ascii=False)

        return json.dumps([str(value)], ensure_ascii=False)

    @staticmethod
    def _parse_allegati_paths_from_db(value: Any) -> List[str]:
        """Converte il valore persistito in lista per il frontend."""
        if value is None:
            return []

        if isinstance(value, list):
            return [str(v).strip() for v in value if v is not None and str(v).strip()]

        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return []

            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [str(v).strip() for v in parsed if v is not None and str(v).strip()]
                if isinstance(parsed, str) and parsed.strip():
                    return [parsed.strip()]
            except Exception:
                return [raw]

        return [str(value)]

    async def _is_superuser(self, user_id: UUID) -> bool:
        user = await self.db.get(User, str(user_id))
        return bool(user and user.is_superuser)

    async def _ensure_responsabile_or_superuser(self, giornale: GiornaleCantiere, user_id: UUID) -> None:
        if str(giornale.responsabile_id) == str(user_id):
            return
        if await self._is_superuser(user_id):
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operazione consentita solo al responsabile del giornale o a un superuser",
        )

    @staticmethod
    def _compute_content_hash(giornale: GiornaleCantiere) -> str:
        payload = {
            "id": str(giornale.id),
            "site_id": str(giornale.site_id),
            "cantiere_id": str(giornale.cantiere_id) if giornale.cantiere_id else None,
            "data": giornale.data.isoformat() if giornale.data else None,
            "ora_inizio": giornale.ora_inizio.isoformat() if giornale.ora_inizio else None,
            "ora_fine": giornale.ora_fine.isoformat() if giornale.ora_fine else None,
            "descrizione_lavori": giornale.descrizione_lavori,
            "condizioni_meteo": giornale.condizioni_meteo,
            "responsabile_id": str(giornale.responsabile_id) if giornale.responsabile_id else None,
            "us_elaborate": giornale.us_elaborate,
            "usm_elaborate": giornale.usm_elaborate,
            "usr_elaborate": giornale.usr_elaborate,
            "materiali_rinvenuti": giornale.materiali_rinvenuti,
            "documentazione_prodotta": giornale.documentazione_prodotta,
            "note_generali": giornale.note_generali,
            "problematiche": giornale.problematiche,
        }
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _append_audit_event(giornale: GiornaleCantiere, event_type: str, actor_id: UUID, data: Dict[str, Any]) -> None:
        try:
            audit = json.loads(giornale.validation_audit) if giornale.validation_audit else []
            if not isinstance(audit, list):
                audit = []
        except Exception:
            audit = []

        audit.append(
            {
                "event_type": event_type,
                "actor_id": str(actor_id),
                "timestamp": datetime.utcnow().isoformat(),
                "data": data,
            }
        )
        giornale.validation_audit = json.dumps(audit, ensure_ascii=False)

    async def _resolve_mezzi_associations(
        self,
        site_id: UUID,
        payload: Dict[str, Any],
        strict: bool = True,
    ) -> Dict[str, Any]:
        """
        Risolve i mezzi in un formato persistibile su tabella associativa.

        Returns:
            {
                "associations": [{"mezzo_id": "...", "ore_utilizzo": float|None, "note_utilizzo": str}],
                "display_value": "stringa leggibile per compatibilitÃ  storica"
            }
        """
        mezzi_payload = payload.get("mezzi")
        normalized_items: List[Dict[str, Any]] = []

        if isinstance(mezzi_payload, list):
            for mezzo_info in mezzi_payload:
                mezzo_id_raw = (mezzo_info or {}).get("id")
                if not mezzo_id_raw:
                    if strict:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Ogni mezzo selezionato deve avere un ID valido"
                        )
                    continue

                try:
                    mezzo_id = str(UUID(str(mezzo_id_raw)))
                except Exception:
                    if strict:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"ID mezzo non valido: {mezzo_id_raw}"
                        )
                    continue

                ore_raw = (mezzo_info or {}).get("ore_utilizzo")
                if ore_raw in ("", None):
                    ore_utilizzo = None
                else:
                    try:
                        ore_utilizzo = float(ore_raw)
                    except (TypeError, ValueError):
                        if strict:
                            raise HTTPException(
                                status_code=status.HTTP_400_BAD_REQUEST,
                                detail=f"Ore utilizzo non valide per mezzo {mezzo_id}"
                            )
                        ore_utilizzo = None

                    if ore_utilizzo is not None and ore_utilizzo < 0:
                        if strict:
                            raise HTTPException(
                                status_code=status.HTTP_400_BAD_REQUEST,
                                detail=f"Ore utilizzo non valide per mezzo {mezzo_id}"
                            )
                        ore_utilizzo = None

                note_utilizzo = (mezzo_info or {}).get("note_utilizzo") or ""

                normalized_items.append({
                    "mezzo_id": mezzo_id,
                    "ore_utilizzo": ore_utilizzo,
                    "note_utilizzo": note_utilizzo,
                })

        elif payload.get("mezzi_ids"):
            for mezzo_id_raw in payload.get("mezzi_ids", []) or []:
                try:
                    mezzo_id = str(UUID(str(mezzo_id_raw)))
                except Exception:
                    if strict:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"ID mezzo non valido: {mezzo_id_raw}"
                        )
                    continue

                normalized_items.append({
                    "mezzo_id": mezzo_id,
                    "ore_utilizzo": None,
                    "note_utilizzo": "",
                })
        else:
            return {
                "associations": [],
                "display_value": "",
            }

        if not normalized_items:
            return {"associations": [], "display_value": ""}

        seen = set()
        ordered_ids: List[UUID] = []
        by_mezzo_id: Dict[str, Dict[str, Any]] = {}
        for item in normalized_items:
            mezzo_id = item["mezzo_id"]
            if mezzo_id not in seen:
                seen.add(mezzo_id)
                ordered_ids.append(UUID(mezzo_id))
            by_mezzo_id[mezzo_id] = item

        mezzi_records = await self.repository.get_mezzi_by_ids(site_id, ordered_ids)
        mezzi_map = {str(m.id): m for m in mezzi_records}
        mezzi_map_compact = {str(m.id).replace("-", "").lower(): m for m in mezzi_records}

        associations: List[Dict[str, Any]] = []
        labels: List[str] = []

        for mezzo_uuid in ordered_ids:
            mezzo_id = str(mezzo_uuid)
            mezzo = mezzi_map.get(mezzo_id) or mezzi_map_compact.get(mezzo_id.replace("-", "").lower())

            if not mezzo:
                if strict:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Uno o piÃ¹ mezzi selezionati non sono assegnati al sito"
                    )
                continue

            item = by_mezzo_id.get(mezzo_id, {})
            ore_utilizzo = item.get("ore_utilizzo")
            note_utilizzo = item.get("note_utilizzo") or ""

            associations.append({
                "mezzo_id": str(mezzo.id),
                "ore_utilizzo": ore_utilizzo,
                "note_utilizzo": note_utilizzo,
            })

            label = mezzo.nome
            if mezzo.targa:
                label = f"{label} ({mezzo.targa})"
            if ore_utilizzo is not None:
                label = f"{label} [{ore_utilizzo:g}h]"
            labels.append(label)

        return {
            "associations": associations,
            "display_value": ", ".join(labels),
        }

    async def _format_giornale(self, g: GiornaleCantiere) -> Dict[str, Any]:
        """Helper to format giornale for API response"""
        # Recupera info cantiere
        cantiere_info = None
        if g.cantiere_id:
            cantiere = await self.repository.get_cantiere_info(g.cantiere_id)
            if cantiere:
                cantiere_info = {
                    "id": str(cantiere.id),
                    "nome": cantiere.nome,
                    "codice": cantiere.codice,
                    "committente": cantiere.committente,
                    "impresa_esecutrice": cantiere.impresa_esecutrice,
                    "direttore_lavori": cantiere.direttore_lavori,
                    "responsabile_procedimento": cantiere.responsabile_procedimento,
                    "oggetto_appalto": cantiere.oggetto_appalto,
                    "codice_cup": cantiere.codice_cup,
                    "codice_cig": cantiere.codice_cig,
                    "importo_lavori": float(cantiere.importo_lavori) if cantiere.importo_lavori else None
                }

        # Recupera operatori con ore
        enhanced_operators = await self.repository.get_enhanced_operators(g.id, g.operatori or [])

        # Recupera mezzi con ore/note dalla tabella associativa.
        enhanced_mezzi = await self.repository.get_enhanced_mezzi(g.id, g.mezzi or [])
        mezzi_labels: List[str] = []
        for mezzo in enhanced_mezzi:
            label = mezzo.get("nome") or "Mezzo"
            if mezzo.get("targa"):
                label = f"{label} ({mezzo['targa']})"
            details: List[str] = []
            if mezzo.get("ore_utilizzo") is not None:
                details.append(f"{mezzo['ore_utilizzo']:g}h")
            if mezzo.get("note_utilizzo"):
                details.append(mezzo["note_utilizzo"])
            if details:
                label = f"{label} [{' - '.join(details)}]"
            mezzi_labels.append(label)

        mezzi_data = {
            "mezzi_presenti": enhanced_mezzi,
            "display_value": ", ".join(mezzi_labels)
        }

        # Format response dict
        return {
            "id": str(g.id),
            "data": g.data.isoformat() if g.data else None,
            "ora_inizio": g.ora_inizio.strftime("%H:%M") if g.ora_inizio else None,
            "ora_fine": g.ora_fine.strftime("%H:%M") if g.ora_fine else None,
            "responsabile_scavo": g.responsabile_nome or (g.responsabile.email if g.responsabile else None),
            "descrizione_lavori": g.descrizione_lavori,
            "condizioni_meteo": g.condizioni_meteo,
            "validato": bool(g.validato),
            "stato": "validato" if g.validato else "in_attesa",
            "us_elaborate": g.get_us_list() if hasattr(g, "get_us_list") else [],
            "us_elaborate_input": g.us_elaborate if g.us_elaborate else "",
            "usm_elaborate": g.get_usm_list() if hasattr(g, "get_usm_list") else [],
            "usr_elaborate": g.usr_elaborate.split(",") if g.usr_elaborate else [],
            "cantiere_id": str(g.cantiere_id) if g.cantiere_id else None,
            "cantiere": cantiere_info,
            "operatori_presenti": enhanced_operators,
            "note_generali": g.note_generali,
            "problematiche": g.problematiche,
            "compilatore": g.compilatore or g.responsabile_nome,
            "area_intervento": g.area_intervento,
            "saggio": g.saggio,
            "obiettivi": g.obiettivi,
            "interpretazione": g.interpretazione,
            "campioni_prelevati": g.campioni_prelevati,
            "strutture": g.strutture,
            "temperatura": g.temperatura,
            "temperatura_min": g.temperatura_min,
            "temperatura_max": g.temperatura_max,
            "note_meteo": g.note_meteo,
            "modalita_lavorazioni": g.modalita_lavorazioni,
            "attrezzatura_utilizzata": g.attrezzatura_utilizzata,
            "apparecchiature_input": g.attrezzatura_utilizzata,
            "mezzi_utilizzati": mezzi_data["display_value"],
            "mezzi_presenti": mezzi_data["mezzi_presenti"],
            "materiali_rinvenuti": g.materiali_rinvenuti,
            "documentazione_prodotta": g.documentazione_prodotta,
            "sopralluoghi": g.sopralluoghi,
            "disposizioni_rup": g.disposizioni_rup,
            "disposizioni_direttore": g.disposizioni_direttore,
            "contestazioni": g.contestazioni,
            "sospensioni": g.sospensioni,
            "incidenti": g.incidenti,
            "forniture": g.forniture,
            "data_validazione": g.data_validazione.isoformat() if g.data_validazione else None,
            "firma_digitale_hash": g.firma_digitale_hash,
            "validated_by_id": str(g.validated_by_id) if g.validated_by_id else None,
            "content_hash": g.content_hash,
            "legal_freeze_at": g.legal_freeze_at.isoformat() if g.legal_freeze_at else None,
            "signature_type": g.signature_type,
            "signed_file_path": g.signed_file_path,
            "signature_reference": g.signature_reference,
            "signature_timestamp": g.signature_timestamp.isoformat() if g.signature_timestamp else None,
            "protocol_number": g.protocol_number,
            "protocol_date": g.protocol_date.isoformat() if g.protocol_date else None,
            "legal_status": g.legal_status,
            "allegati_paths": self._parse_allegati_paths_from_db(g.allegati_paths),
            "created_at": g.created_at.isoformat() if g.created_at else None,
            "updated_at": g.updated_at.isoformat() if g.updated_at else None,
            "version": g.version or 1,
            "foto": [
                {
                    "id": str(f.id),
                    "filename": f.filename,
                    "original_filename": f.original_filename,
                    "thumbnail_url": f"/api/v1/photos/{f.id}/thumbnail",
                    "full_url": f"/api/v1/photos/{f.id}/full",
                    "title": f.title,
                    "description": f.description,
                }
                for f in (g.foto or [])
            ],
        }

    async def list_giornali(
        self,
        site_id: UUID,
        skip: int = 0,
        limit: int = 20,
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Lista giornali formattati per il frontend
        """
        giornali = await self.repository.get_site_giornali(site_id, skip, limit, filters)
        
        giornali_data = []
        for g in giornali:
            data = await self._format_giornale(g)
            giornali_data.append(data)
            
        return {
            "data": giornali_data,
            "count": len(giornali_data)
        }

    async def get_giornale(self, site_id: UUID, giornale_id: UUID) -> Dict[str, Any]:
        """Recupera singolo giornale formato"""
        # Use get_with_relations to eager load all relationships for PDF/sync contexts
        giornale = await self.repository.get_with_relations(giornale_id)
        if not giornale or str(giornale.site_id) != str(site_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Giornale non trovato"
            )
        return await self._format_giornale(giornale)

    async def create_giornale(
        self,
        site_id: UUID,
        giornale_data: Dict[str, Any],
        user_id: UUID
    ) -> GiornaleCantiere:
        """
        Crea nuovo giornale con validazioni business
        """
        # Validate cantiere ownership
        cantiere_id = giornale_data.get("cantiere_id")
        if cantiere_id:
            is_valid = await self.repository.verify_cantiere_site_access(cantiere_id, site_id)
            if not is_valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Il cantiere {cantiere_id} non appartiene al sito {site_id}"
                )

        # Validate and normalize selected mezzi (nuova tabella associativa)
        mezzi_resolution = await self._resolve_mezzi_associations(site_id, giornale_data, strict=True)
        mezzi_associations = mezzi_resolution["associations"]

        # Create giornale object
        nuovo_giornale = GiornaleCantiere(
            site_id=str(site_id),
            cantiere_id=str(UUID(cantiere_id)) if cantiere_id else None,
            data=date.fromisoformat(giornale_data.get("data")) if giornale_data.get("data") else date.today(),
            ora_inizio=time.fromisoformat(giornale_data["ora_inizio"]) if giornale_data.get("ora_inizio") else None,
            ora_fine=time.fromisoformat(giornale_data["ora_fine"]) if giornale_data.get("ora_fine") else None,
            descrizione_lavori=giornale_data.get("descrizione_lavori", ""),
            condizioni_meteo=giornale_data.get("condizioni_meteo"),
            note_generali=giornale_data.get("note_generali", ""),
            problematiche=giornale_data.get("problematiche", ""),
            responsabile_id=str(user_id),
            responsabile_nome=giornale_data.get("responsabile_nome", ""),
            compilatore=giornale_data.get("compilatore", ""),
            temperatura_min=giornale_data.get("temperatura_min"),
            temperatura_max=giornale_data.get("temperatura_max"),
            area_intervento=giornale_data.get("area_intervento"),
            saggio=giornale_data.get("saggio"),
            obiettivi=giornale_data.get("obiettivi"),
            interpretazione=giornale_data.get("interpretazione"),
            campioni_prelevati=giornale_data.get("campioni_prelevati"),
            strutture=giornale_data.get("strutture"),
            us_elaborate=giornale_data.get("us_elaborate_input", ""),
            attrezzatura_utilizzata=giornale_data.get("apparecchiature_input", ""),
            allegati_paths=self._normalize_allegati_paths_for_db(giornale_data.get("allegati_paths")),
            validato=False
        )
        
        self.db.add(nuovo_giornale)
        await self.db.flush() # Get ID

        # Validate and add operators
        operatori_data = giornale_data.get("operatori", [])
        if operatori_data:
            for operatore_info in operatori_data:
                op_id = operatore_info.get("id")
                ore_lavorate = operatore_info.get("ore_lavorate")
                note_presenza = operatore_info.get("note_presenza")
                
                if ore_lavorate is not None and (not isinstance(ore_lavorate, (int, float)) or ore_lavorate < 0):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Ore lavorate non valide per operatore {op_id}"
                    )
                
                is_valid_op = await self.repository.verify_operatore_site_access(op_id, site_id)
                if not is_valid_op:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"L'operatore {op_id} non Ã¨ assegnato al sito {site_id}"
                    )
                
                await self.repository.add_operatore_association(
                    nuovo_giornale.id,
                    op_id,
                    float(ore_lavorate) if ore_lavorate is not None else None,
                    note_presenza
                )

        # Add mezzi associations
        for mezzo_info in mezzi_associations:
            await self.repository.add_mezzo_association(
                nuovo_giornale.id,
                mezzo_info["mezzo_id"],
                mezzo_info.get("ore_utilizzo"),
                mezzo_info.get("note_utilizzo"),
            )
        
        await self.db.commit()
        await self.db.refresh(nuovo_giornale)
        return nuovo_giornale

    async def update_giornale(
        self,
        site_id: UUID,
        giornale_id: UUID,
        giornale_data: Dict[str, Any],
        user_id: UUID
    ) -> GiornaleCantiere:
        """
        Aggiorna giornale esistente
        """
        giornale = await self.repository.get(giornale_id)
        if not giornale or str(giornale.site_id) != str(site_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Giornale non trovato"
            )
        await self._ensure_responsabile_or_superuser(giornale, user_id)
        if giornale.validato:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Giornale validato: modifica non consentita (record congelato legalmente)",
            )

        # Validate cantiere ownership if changed
        if "cantiere_id" in giornale_data and giornale_data["cantiere_id"]:
             is_valid = await self.repository.verify_cantiere_site_access(giornale_data["cantiere_id"], site_id)
             if not is_valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Il cantiere {giornale_data['cantiere_id']} non appartiene al sito {site_id}"
                )

        # Handle operators
        if "operatori" in giornale_data:
            operatori_data = giornale_data["operatori"]
            await self.repository.clear_operatore_associations(giornale.id)
            
            if operatori_data:
                for operatore_info in operatori_data:
                    op_id = operatore_info.get("id")
                    ore_lavorate = operatore_info.get("ore_lavorate")
                    note_presenza = operatore_info.get("note_presenza")
                    
                    if ore_lavorate is not None and (not isinstance(ore_lavorate, (int, float)) or ore_lavorate < 0):
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Ore lavorate non valide per operatore {op_id}"
                        )
                    
                    is_valid_op = await self.repository.verify_operatore_site_access(op_id, site_id)
                    if not is_valid_op:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"L'operatore {op_id} non Ã¨ assegnato al sito {site_id}"
                        )
                        
                    await self.repository.add_operatore_association(
                        giornale.id,
                        op_id,
                        float(ore_lavorate) if ore_lavorate is not None else None,
                        note_presenza
                    )

        # Handle mezzi (nuova tabella associativa)
        if "mezzi" in giornale_data or "mezzi_ids" in giornale_data:
            mezzi_resolution = await self._resolve_mezzi_associations(site_id, giornale_data, strict=False)
            mezzi_associations = mezzi_resolution["associations"]

            await self.repository.clear_mezzo_associations(giornale.id)
            for mezzo_info in mezzi_associations:
                await self.repository.add_mezzo_association(
                    giornale.id,
                    mezzo_info["mezzo_id"],
                    mezzo_info.get("ore_utilizzo"),
                    mezzo_info.get("note_utilizzo"),
                )

        # Update base fields
        update_dict = giornale_data.copy()

        # Helper per i campi data/time
        if "data" in update_dict:
             update_dict["data"] = date.fromisoformat(update_dict["data"])
        if "ora_inizio" in update_dict and update_dict["ora_inizio"]:
             update_dict["ora_inizio"] = time.fromisoformat(update_dict["ora_inizio"])
        if "ora_fine" in update_dict and update_dict["ora_fine"]:
             update_dict["ora_fine"] = time.fromisoformat(update_dict["ora_fine"])
             
        # Mapping input alias per attrezzatura
        if "apparecchiature_input" in update_dict:
            update_dict["attrezzatura_utilizzata"] = update_dict.pop("apparecchiature_input")
        if "us_elaborate_input" in update_dict:
            update_dict["us_elaborate"] = update_dict.pop("us_elaborate_input")

        # Convert list fields to comma-separated strings for SQLite
        for list_field in ["us_elaborate", "usm_elaborate", "usr_elaborate"]:
            if list_field in update_dict and isinstance(update_dict[list_field], list):
                update_dict[list_field] = ", ".join(update_dict[list_field]) if update_dict[list_field] else ""

        # Persist allegati_paths come JSON string su colonna TEXT
        if "allegati_paths" in update_dict:
            update_dict["allegati_paths"] = self._normalize_allegati_paths_for_db(update_dict.get("allegati_paths"))

        # Cleanup fields we processed manually
        for field in ["operatori", "mezzi", "mezzi_ids", "mezzi_utilizzati", "id", "site_id"]:
            update_dict.pop(field, None)

        await self.repository.update(giornale, update_dict)
        await self.db.commit()
        await self.db.refresh(giornale)
        return giornale

    async def validate_giornale(
        self,
        site_id: UUID,
        giornale_id: UUID,
        user_id: UUID,
        legal_data: Optional[Dict[str, Any]] = None
    ) -> GiornaleCantiere:
        """Valida il giornale e ne congela il contenuto per workflow legale."""
        giornale = await self.repository.get(giornale_id)
        if not giornale or str(giornale.site_id) != str(site_id):
            raise HTTPException(status_code=404, detail="Giornale non trovato")
        await self._ensure_responsabile_or_superuser(giornale, user_id)

        if giornale.validato:
            raise HTTPException(status_code=400, detail="Giornale giÃ  validato")

        legal_data = legal_data or {}
        giornale.validato = True
        giornale.data_validazione = datetime.utcnow()
        giornale.validated_by_id = str(user_id)
        giornale.content_hash = self._compute_content_hash(giornale)
        giornale.legal_freeze_at = datetime.utcnow()
        giornale.firma_digitale_hash = legal_data.get("firma_digitale_hash") or giornale.firma_digitale_hash
        giornale.signature_type = legal_data.get("signature_type")
        giornale.signed_file_path = legal_data.get("signed_file_path")
        giornale.signature_reference = legal_data.get("signature_reference")
        if legal_data.get("signature_timestamp"):
            giornale.signature_timestamp = datetime.fromisoformat(legal_data["signature_timestamp"])
        if legal_data.get("protocol_date"):
            giornale.protocol_date = date.fromisoformat(legal_data["protocol_date"])
        giornale.protocol_number = legal_data.get("protocol_number")

        if giornale.protocol_number and giornale.signature_type:
            giornale.legal_status = "protocolled"
        elif giornale.signature_type:
            giornale.legal_status = "signed"
        else:
            giornale.legal_status = "validated"

        self._append_audit_event(
            giornale,
            "validated",
            user_id,
            {
                "legal_status": giornale.legal_status,
                "protocol_number": giornale.protocol_number,
                "signature_type": giornale.signature_type,
            },
        )
        await self.db.commit()
        await self.db.refresh(giornale)
        return giornale

    async def update_legal_metadata(
        self,
        site_id: UUID,
        giornale_id: UUID,
        user_id: UUID,
        legal_data: Dict[str, Any]
    ) -> GiornaleCantiere:
        """Aggiorna metadati legali post-validazione senza sbloccare il record."""
        giornale = await self.repository.get(giornale_id)
        if not giornale or str(giornale.site_id) != str(site_id):
            raise HTTPException(status_code=404, detail="Giornale non trovato")
        await self._ensure_responsabile_or_superuser(giornale, user_id)
        if not giornale.validato:
            raise HTTPException(status_code=409, detail="Il giornale deve essere prima validato")

        if "firma_digitale_hash" in legal_data:
            giornale.firma_digitale_hash = legal_data.get("firma_digitale_hash")
        if "signature_type" in legal_data:
            giornale.signature_type = legal_data.get("signature_type")
        if "signed_file_path" in legal_data:
            giornale.signed_file_path = legal_data.get("signed_file_path")
        if "signature_reference" in legal_data:
            giornale.signature_reference = legal_data.get("signature_reference")
        if legal_data.get("signature_timestamp"):
            giornale.signature_timestamp = datetime.fromisoformat(legal_data["signature_timestamp"])
        if "protocol_number" in legal_data:
            giornale.protocol_number = legal_data.get("protocol_number")
        if legal_data.get("protocol_date"):
            giornale.protocol_date = date.fromisoformat(legal_data["protocol_date"])

        if giornale.protocol_number and giornale.signature_type:
            giornale.legal_status = "protocolled"
        elif giornale.signature_type:
            giornale.legal_status = "signed"
        else:
            giornale.legal_status = "validated"

        self._append_audit_event(
            giornale,
            "legal_metadata_updated",
            user_id,
            {
                "legal_status": giornale.legal_status,
                "protocol_number": giornale.protocol_number,
                "signature_type": giornale.signature_type,
            },
        )
        await self.db.commit()
        await self.db.refresh(giornale)
        return giornale

    async def delete_giornale(self, site_id: UUID, giornale_id: UUID, user_id: UUID):
        """Elimina il giornale"""
        giornale = await self.repository.get(giornale_id)
        if not giornale or str(giornale.site_id) != str(site_id):
            raise HTTPException(status_code=404, detail="Giornale non trovato")
        await self._ensure_responsabile_or_superuser(giornale, user_id)
        if giornale.validato:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Giornale validato: eliminazione non consentita (record congelato legalmente)",
            )

        await self.repository.clear_operatore_associations(giornale.id)
        await self.repository.clear_mezzo_associations(giornale.id)
        await self.repository.remove(giornale.id)
        return True

    async def link_photo(
        self,
        site_id: UUID,
        giornale_id: UUID,
        foto_id: UUID,
        user_id: UUID,
        didascalia: str = None,
        ordine: int = 0
    ):
        """Link photo"""
        # Verify access
        giornale = await self.repository.get(giornale_id)
        if not giornale or str(giornale.site_id) != str(site_id):
            raise HTTPException(status_code=404, detail="Giornale non trovato")
        await self._ensure_responsabile_or_superuser(giornale, user_id)
        if giornale.validato:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Giornale validato: modifica allegati non consentita",
            )

        # Verify photo (generic repo check or direct query)
        # Using direct query for simplicity as we don't have PhotoService injected yet
        from app.models.documentation_and_field import Photo
        photo_res = await self.db.execute(select(Photo).where(and_(Photo.id == str(foto_id), Photo.site_id == str(site_id))))
        if not photo_res.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Foto non trovata")

        if await self.repository.check_photo_linked(giornale_id, foto_id):
             raise HTTPException(status_code=400, detail="Foto giÃ  collegata")

        await self.repository.link_photo(giornale_id, foto_id, didascalia, ordine)
        await self.db.commit()

    async def unlink_photo(self, site_id: UUID, giornale_id: UUID, foto_id: UUID, user_id: UUID):
        """Unlink photo"""
        giornale = await self.repository.get(giornale_id)
        if not giornale or str(giornale.site_id) != str(site_id):
            raise HTTPException(status_code=404, detail="Giornale non trovato")
        await self._ensure_responsabile_or_superuser(giornale, user_id)
        if giornale.validato:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Giornale validato: modifica allegati non consentita",
            )

        success = await self.repository.unlink_photo(giornale_id, foto_id)
        if not success:
            raise HTTPException(status_code=404, detail="Associazione non trovata")
        await self.db.commit()

    async def list_photo_archive_for_giornale(
        self,
        site_id: UUID,
        giornale_id: UUID,
        user_id: UUID,
        skip: int = 0,
        limit: int = 40,
        search: Optional[str] = None,
        link_state: str = "all",
        sort_by: str = "created_desc",
    ) -> Dict[str, Any]:
        """Elenco paginato foto per pagina dedicata gestione giornale."""
        giornale = await self.repository.get(giornale_id)
        if not giornale or str(giornale.site_id) != str(site_id):
            raise HTTPException(status_code=404, detail="Giornale non trovato")

        archive = await self.repository.list_photo_archive_for_giornale(
            site_id=site_id,
            giornale_id=giornale_id,
            skip=skip,
            limit=limit,
            search=search,
            link_state=link_state,
            sort_by=sort_by,
        )

        return {
            "giornale_id": str(giornale_id),
            "site_id": str(site_id),
            "items": archive["items"],
            "total": archive["total"],
            "skip": skip,
            "limit": limit,
            "linked_count": archive["linked_count"],
        }

    async def bulk_link_photos(
        self,
        site_id: UUID,
        giornale_id: UUID,
        photo_ids: List[UUID],
        user_id: UUID,
    ) -> Dict[str, Any]:
        """Collega in blocco foto esistenti al giornale."""
        giornale = await self.repository.get(giornale_id)
        if not giornale or str(giornale.site_id) != str(site_id):
            raise HTTPException(status_code=404, detail="Giornale non trovato")
        await self._ensure_responsabile_or_superuser(giornale, user_id)
        if giornale.validato:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Giornale validato: modifica allegati non consentita",
            )

        valid_site_photo_ids = await self.repository.get_site_photo_ids(site_id, photo_ids)
        if not valid_site_photo_ids:
            raise HTTPException(status_code=400, detail="Nessuna foto valida selezionata per questo sito")

        normalized_ids = [UUID(photo_id) for photo_id in valid_site_photo_ids]
        result = await self.repository.bulk_link_photos(giornale_id, normalized_ids)
        await self.db.commit()

        return {
            "giornale_id": str(giornale_id),
            "linked_count": result["linked_count"],
            "already_linked": result["already_linked"],
            "requested": len(photo_ids or []),
            "valid_site_photos": len(valid_site_photo_ids),
        }

    async def bulk_unlink_photos(
        self,
        site_id: UUID,
        giornale_id: UUID,
        photo_ids: List[UUID],
        user_id: UUID,
    ) -> Dict[str, Any]:
        """Scollega in blocco foto dal giornale."""
        giornale = await self.repository.get(giornale_id)
        if not giornale or str(giornale.site_id) != str(site_id):
            raise HTTPException(status_code=404, detail="Giornale non trovato")
        await self._ensure_responsabile_or_superuser(giornale, user_id)
        if giornale.validato:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Giornale validato: modifica allegati non consentita",
            )

        unlinked_count = await self.repository.bulk_unlink_photos(giornale_id, photo_ids)
        await self.db.commit()

        return {
            "giornale_id": str(giornale_id),
            "unlinked_count": unlinked_count,
            "requested": len(photo_ids or []),
        }

    async def list_site_operators(self, site_id: UUID, skip: int = 0, limit: int = 20, filters: Dict[str, Any] = None) -> Dict[str, Any]:
        """List operators with stats"""
        operators_with_stats, total = await self.repository.get_operators_with_stats(site_id, skip, limit, filters)
        
        operators_data = []
        for op, hours in operators_with_stats:
            giornali_count = await self.repository.count_operator_giornali(site_id, op.id)
            
            operators_data.append({
                "id": str(op.id),
                "nome": op.nome,
                "cognome": op.cognome,
                "codice_fiscale": op.codice_fiscale,
                "email": op.email,
                "telefono": op.telefono,
                "ruolo": op.ruolo,
                "specializzazione": op.specializzazione,
                "qualifica": op.qualifica,
                "qualifiche": op.qualifica.split(",") if op.qualifica else [],
                "stato": "attivo" if op.is_active else "inattivo",
                "ore_totali": float(hours) if hours else 0,
                "giornali_count": giornali_count,
                "site_id": str(op.site_id),
                "note": op.note,
                "assigned_to_site": True,
                "can_work_on_site": str(op.site_id) == str(site_id),
            })
            
        return {
            "data": operators_data,
            "count": total
        }

