# Add import for listing objects in bucket for debugging
from app.services.archaeological_minio_service import archaeological_minio_service
import asyncio
# app/routes/api/archaeological_plans.py - API per gestione piante archeologiche e griglie

from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Form
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import joinedload, selectinload
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime
import json
from loguru import logger

from app.database.session import get_async_session
from app.core.security import get_current_user_id
from app.models.sites import ArchaeologicalSite
from app.models.user_sites import UserSitePermission
from app.models.archaeological_plans import ArchaeologicalPlan, ExcavationUnit, ArchaeologicalData
from app.models.form_schemas import FormSchema
from app.models.users import User
from app.services.storage_service import storage_service

plans_router = APIRouter(prefix="/api/archaeological-plans", tags=["archaeological_plans"])


async def get_site_access_for_plans(
    site_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_async_session)
) -> tuple[ArchaeologicalSite, UserSitePermission]:
    """Verifica accesso utente al sito per operazioni su piante"""
    
    # Verifica esistenza sito
    site_query = select(ArchaeologicalSite).where(ArchaeologicalSite.id == site_id)
    site = await db.execute(site_query)
    site = site.scalar_one_or_none()
    
    if not site:
        raise HTTPException(status_code=404, detail="Sito archeologico non trovato")
    
    # Verifica permessi utente
    permission_query = select(UserSitePermission).where(
        and_(
            UserSitePermission.user_id == current_user_id,
            UserSitePermission.site_id == site_id,
            UserSitePermission.is_active == True,
            or_(
                UserSitePermission.expires_at.is_(None),
                UserSitePermission.expires_at > func.now()
            )
        )
    )
    
    permission = await db.execute(permission_query)
    permission = permission.scalar_one_or_none()
    
    if not permission:
        raise HTTPException(
            status_code=403,
            detail="Non hai i permessi per accedere a questo sito archeologico"
        )
    
    return site, permission


# === PIANTE ARCHEOLOGICHE ===

@plans_router.get("/sites/{site_id}/plans")
async def get_site_plans(
    site_id: UUID,
    site_access: tuple = Depends(get_site_access_for_plans),
    db: AsyncSession = Depends(get_async_session)
):
    """Ottieni tutte le piante archeologiche di un sito"""
    site, permission = site_access
    
    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi di lettura richiesti")
    
    # Query piante del sito
    plans_query = select(ArchaeologicalPlan).where(
        and_(
            ArchaeologicalPlan.site_id == site_id,
            ArchaeologicalPlan.is_active == True
        )
    ).order_by(ArchaeologicalPlan.is_primary.desc(), ArchaeologicalPlan.created_at.desc())
    
    plans = await db.execute(plans_query)
    plans = plans.scalars().all()
    
    plans_data = [plan.to_dict() for plan in plans]
    
    return JSONResponse({
        "site_id": str(site_id),
        "plans": plans_data,
        "total": len(plans_data)
    })


@plans_router.post("/sites/{site_id}/plans/upload")
async def upload_archaeological_plan(
    site_id: UUID,
    plan_file: UploadFile = File(...),
    name: str = Form(...),
    description: Optional[str] = Form(None),
    plan_type: str = Form("general"),
    coordinate_system: str = Form("archaeological_grid"),
    origin_x: float = Form(0.0),
    origin_y: float = Form(0.0),
    scale_factor: float = Form(1.0),
    bounds_north: Optional[float] = Form(None),
    bounds_south: Optional[float] = Form(None),
    bounds_east: Optional[float] = Form(None),
    bounds_west: Optional[float] = Form(None),
    drawing_scale: Optional[str] = Form(None),
    surveyor: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    is_primary: bool = Form(False),
    site_access: tuple = Depends(get_site_access_for_plans),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_async_session)
):
    """Carica una nuova pianta archeologica"""
    site, permission = site_access
    
    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")
    
    try:
        # Verifica tipo file
        if not plan_file.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="Solo file immagine sono supportati")
        
        # Salva file su storage
        filename, file_path, file_size = await storage_service.save_upload_file(
            plan_file, f"plans/{site_id}", str(current_user_id)
        )
        
        # Ottieni dimensioni immagine
        from PIL import Image
        import io
        
        await plan_file.seek(0)
        image_content = await plan_file.read()
        with Image.open(io.BytesIO(image_content)) as img:
            image_width, image_height = img.size
        
        # Se è pianta primaria, rimuovi flag da altre piante
        if is_primary:
            await db.execute(
                select(ArchaeologicalPlan).where(
                    and_(
                        ArchaeologicalPlan.site_id == site_id,
                        ArchaeologicalPlan.is_primary == True
                    )
                ).update({ArchaeologicalPlan.is_primary: False})
            )
        
        # Crea record pianta
        plan = ArchaeologicalPlan(
            site_id=site_id,
            name=name,
            description=description,
            plan_type=plan_type,
            image_path=file_path,
            image_filename=filename,
            file_size=file_size,
            coordinate_system=coordinate_system,
            origin_x=origin_x,
            origin_y=origin_y,
            scale_factor=scale_factor,
            bounds_north=bounds_north,
            bounds_south=bounds_south,
            bounds_east=bounds_east,
            bounds_west=bounds_west,
            image_width=image_width,
            image_height=image_height,
            drawing_scale=drawing_scale,
            surveyor=surveyor,
            notes=notes,
            is_primary=is_primary,
            created_by=current_user_id
        )
        
        db.add(plan)
        await db.commit()
        await db.refresh(plan)
        
        logger.info(f"Archaeological plan uploaded: {plan.id} for site {site_id}")
        
        return JSONResponse({
            "message": "Pianta archeologica caricata con successo",
            "plan_id": str(plan.id),
            "plan_data": plan.to_dict()
        })
        
    except Exception as e:
        logger.error(f"Error uploading archaeological plan: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Errore caricamento pianta: {str(e)}")


@plans_router.get("/sites/{site_id}/plans/{plan_id}")
async def get_plan_details(
    site_id: UUID,
    plan_id: UUID,
    site_access: tuple = Depends(get_site_access_for_plans),
    db: AsyncSession = Depends(get_async_session)
):
    """Ottieni dettagli di una pianta specifica"""
    site, permission = site_access
    
    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi di lettura richiesti")
    
    # Query pianta con unità di scavo e dati
    plan_query = select(ArchaeologicalPlan).options(
        selectinload(ArchaeologicalPlan.excavation_units),
        selectinload(ArchaeologicalPlan.archaeological_data)
    ).where(
        and_(
            ArchaeologicalPlan.id == plan_id,
            ArchaeologicalPlan.site_id == site_id
        )
    )
    
    plan = await db.execute(plan_query)
    plan = plan.scalar_one_or_none()
    
    if not plan:
        raise HTTPException(status_code=404, detail="Pianta non trovata")
    
    # Conta unità per stato
    units_by_status = {}
    for unit in plan.excavation_units:
        status = unit.status
        if status not in units_by_status:
            units_by_status[status] = 0
        units_by_status[status] += 1
    
    plan_data = plan.to_dict()
    plan_data.update({
        "excavation_units_count": len(plan.excavation_units),
        "archaeological_data_count": len(plan.archaeological_data),
        "units_by_status": units_by_status
    })
    
    return JSONResponse(plan_data)


@plans_router.get("/sites/{site_id}/plans/{plan_id}/image")
async def get_plan_image(
    site_id: UUID,
    plan_id: UUID,
    site_access: tuple = Depends(get_site_access_for_plans),
    db: AsyncSession = Depends(get_async_session)
):
    """Ottieni immagine della pianta"""
    site, permission = site_access
    
    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi di lettura richiesti")
    
    plan = await db.execute(
        select(ArchaeologicalPlan).where(
            and_(
                ArchaeologicalPlan.id == plan_id,
                ArchaeologicalPlan.site_id == site_id
            )
        )
    )
    plan = plan.scalar_one_or_none()
    
    if not plan:
        raise HTTPException(status_code=404, detail="Pianta non trovata")
    
    # Serve l'immagine direttamente
    try:
        # Determina se l'immagine è su MinIO o locale
        if plan.image_path.startswith("plans/") or not plan.image_path.startswith("storage/"):
            # Immagine su MinIO - gestisci i piani archeologici
            from app.services.archaeological_minio_service import archaeological_minio_service
            import io
            from fastapi.responses import StreamingResponse
            
            # Per i piani archeologici, usa direttamente il path come oggetto nel bucket archaeological-photos
            # Il path è già nel formato corretto: site_id/filename.ext
            try:
                # Debug: List objects in bucket to see what's actually there
                try:
                    objects = await asyncio.to_thread(
                        archaeological_minio_service.client.list_objects,
                        bucket_name=archaeological_minio_service.buckets['photos'],
                        prefix=f"{plan.site_id}/",
                        recursive=True
                    )
                    logger.info(f"Objects in bucket for site {plan.site_id}:")
                    for obj in objects:
                        logger.info(f"  - {obj.object_name} ({obj.size} bytes)")
                except Exception as list_error:
                    logger.error(f"Error listing objects: {list_error}")
                
                image_data = await archaeological_minio_service.get_file(plan.image_path)
                
                if image_data and isinstance(image_data, bytes):
                    # Determina il tipo di contenuto dall'estensione del file
                    import os
                    ext = os.path.splitext(plan.image_filename)[1].lower()
                    content_type = "image/jpeg"  # default
                    if ext in [".jpg", ".jpeg"]:
                        content_type = "image/jpeg"
                    elif ext == ".png":
                        content_type = "image/png"
                    elif ext in [".tif", ".tiff"]:
                        content_type = "image/tiff"
                    
                    return StreamingResponse(
                        io.BytesIO(image_data),
                        media_type=content_type,
                        headers={"Cache-Control": "public, max-age=3600"}
                    )
                else:
                    raise HTTPException(status_code=404, detail="Immagine non trovata su MinIO")
            except Exception as minio_error:
                logger.error(f"MinIO error for path {plan.image_path}: {minio_error}")
                raise HTTPException(status_code=404, detail="Immagine non trovata su MinIO")
        
        else:
            # Immagine su filesystem locale
            from fastapi.responses import FileResponse
            from pathlib import Path
            
            # Costruisci il path completo del file
            file_path = Path("app/static/uploads") / plan.image_path
            
            if file_path.exists():
                # Determina il tipo di contenuto dall'estensione del file
                import os
                ext = os.path.splitext(plan.image_filename)[1].lower()
                content_type = "image/jpeg"  # default
                if ext in [".jpg", ".jpeg"]:
                    content_type = "image/jpeg"
                elif ext == ".png":
                    content_type = "image/png"
                elif ext in [".tif", ".tiff"]:
                    content_type = "image/tiff"
                
                return FileResponse(
                    file_path,
                    media_type=content_type,
                    headers={"Cache-Control": "public, max-age=3600"}
                )
            else:
                raise HTTPException(status_code=404, detail="Immagine non trovata localmente")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error serving plan image: {e}")
        raise HTTPException(status_code=500, detail="Errore nel servire l'immagine")


# === UNITÀ DI SCAVO ===

@plans_router.get("/sites/{site_id}/plans/{plan_id}/excavation-units")
async def get_plan_excavation_units(
    site_id: UUID,
    plan_id: UUID,
    site_access: tuple = Depends(get_site_access_for_plans),
    db: AsyncSession = Depends(get_async_session)
):
    """Ottieni tutte le unità di scavo di una pianta"""
    site, permission = site_access
    
    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi di lettura richiesti")
    
    units_query = select(ExcavationUnit).where(
        and_(
            ExcavationUnit.plan_id == plan_id,
            ExcavationUnit.site_id == site_id
        )
    ).order_by(ExcavationUnit.id)
    
    units = await db.execute(units_query)
    units = units.scalars().all()
    
    units_data = [unit.to_dict() for unit in units]
    
    return JSONResponse({
        "plan_id": str(plan_id),
        "excavation_units": units_data,
        "total": len(units_data)
    })


@plans_router.post("/sites/{site_id}/plans/{plan_id}/excavation-units")
async def create_excavation_unit(
    site_id: UUID,
    plan_id: UUID,
    unit_data: dict,
    site_access: tuple = Depends(get_site_access_for_plans),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_async_session)
):
    """Crea una nuova unità di scavo"""
    site, permission = site_access
    
    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")
    
    try:
        # Verifica che la pianta esista
        plan = await db.execute(
            select(ArchaeologicalPlan).where(
                and_(
                    ArchaeologicalPlan.id == plan_id,
                    ArchaeologicalPlan.site_id == site_id
                )
            )
        )
        plan = plan.scalar_one_or_none()
        
        if not plan:
            raise HTTPException(status_code=404, detail="Pianta non trovata")
        
        # Verifica che l'ID unità non esista già
        unit_id = unit_data.get("id")
        existing_unit = await db.execute(
            select(ExcavationUnit).where(ExcavationUnit.id == unit_id)
        )
        if existing_unit.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="ID unità già esistente")
        
        # Crea unità di scavo
        unit = ExcavationUnit(
            id=unit_id,
            site_id=site_id,
            plan_id=plan_id,
            coordinates_x=unit_data.get("coordinates_x"),
            coordinates_y=unit_data.get("coordinates_y"),
            size_x=unit_data.get("size_x", 5.0),
            size_y=unit_data.get("size_y", 5.0),
            status=unit_data.get("status", "planned"),
            supervisor=unit_data.get("supervisor"),
            notes=unit_data.get("notes"),
            priority=unit_data.get("priority", 1),
            excavation_method=unit_data.get("excavation_method"),
            documentation_level=unit_data.get("documentation_level", "standard"),
            created_by=current_user_id
        )
        
        db.add(unit)
        await db.commit()
        await db.refresh(unit)
        
        logger.info(f"Excavation unit created: {unit.id} for plan {plan_id}")
        
        return JSONResponse({
            "message": "Unità di scavo creata con successo",
            "unit_id": unit.id,
            "unit_data": unit.to_dict()
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating excavation unit: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Errore creazione unità: {str(e)}")


@plans_router.put("/sites/{site_id}/plans/{plan_id}/excavation-units/{unit_id}")
async def update_excavation_unit(
    site_id: UUID,
    plan_id: UUID,
    unit_id: str,
    unit_data: dict,
    site_access: tuple = Depends(get_site_access_for_plans),
    db: AsyncSession = Depends(get_async_session)
):
    """Aggiorna una unità di scavo"""
    site, permission = site_access
    
    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")
    
    # Trova unità
    unit = await db.execute(
        select(ExcavationUnit).where(
            and_(
                ExcavationUnit.id == unit_id,
                ExcavationUnit.plan_id == plan_id,
                ExcavationUnit.site_id == site_id
            )
        )
    )
    unit = unit.scalar_one_or_none()
    
    if not unit:
        raise HTTPException(status_code=404, detail="Unità di scavo non trovata")
    
    try:
        # Aggiorna campi modificabili
        updatable_fields = [
            'status', 'current_depth', 'max_depth', 'supervisor', 'notes',
            'soil_description', 'preservation_conditions', 'priority',
            'excavation_method', 'documentation_level', 'start_date',
            'completion_date', 'last_excavation_date'
        ]
        
        for field in updatable_fields:
            if field in unit_data:
                value = unit_data[field]
                
                # Gestione date
                if field in ['start_date', 'completion_date', 'last_excavation_date'] and value:
                    if isinstance(value, str):
                        try:
                            value = datetime.fromisoformat(value)
                        except ValueError:
                            value = datetime.strptime(value, '%Y-%m-%d')
                
                setattr(unit, field, value)
        
        # Aggiorna JSON fields
        if 'team_members' in unit_data:
            unit.team_members = unit_data['team_members']
        
        if 'stratigraphic_sequence' in unit_data:
            unit.stratigraphic_sequence = unit_data['stratigraphic_sequence']
        
        if 'finds_summary' in unit_data:
            unit.finds_summary = unit_data['finds_summary']
        
        unit.updated_at = datetime.utcnow()
        
        await db.commit()
        await db.refresh(unit)
        
        return JSONResponse({
            "message": "Unità di scavo aggiornata con successo",
            "unit_data": unit.to_dict()
        })
        
    except Exception as e:
        logger.error(f"Error updating excavation unit: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Errore aggiornamento unità: {str(e)}")


# === DATI ARCHEOLOGICI ===

@plans_router.get("/sites/{site_id}/plans/{plan_id}/archaeological-data")
async def get_plan_archaeological_data(
    site_id: UUID,
    plan_id: UUID,
    site_access: tuple = Depends(get_site_access_for_plans),
    db: AsyncSession = Depends(get_async_session)
):
    """Ottieni tutti i dati archeologici georeferenziati di una pianta"""
    site, permission = site_access
    
    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi di lettura richiesti")
    
    data_query = select(ArchaeologicalData).options(
        joinedload(ArchaeologicalData.module),
        joinedload(ArchaeologicalData.collector)
    ).where(
        and_(
            ArchaeologicalData.plan_id == plan_id,
            ArchaeologicalData.site_id == site_id
        )
    ).order_by(ArchaeologicalData.created_at.desc())
    
    data_records = await db.execute(data_query)
    data_records = data_records.scalars().all()
    
    data_list = []
    for record in data_records:
        data_dict = record.to_dict()
        data_dict.update({
            "module_name": record.module.name if record.module else None,
            "module_category": record.module.category if record.module else None,
            "collector_name": f"{record.collector.first_name} {record.collector.last_name}" if record.collector else None
        })
        data_list.append(data_dict)
    
    return JSONResponse({
        "plan_id": str(plan_id),
        "archaeological_data": data_list,
        "total": len(data_list)
    })


@plans_router.post("/sites/{site_id}/plans/{plan_id}/archaeological-data")
async def create_archaeological_data(
    site_id: UUID,
    plan_id: UUID,
    data_payload: dict,
    site_access: tuple = Depends(get_site_access_for_plans),
    current_user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_async_session)
):
    """Crea un nuovo punto dati archeologico georeferenziato"""
    site, permission = site_access
    
    if not permission.can_write():
        raise HTTPException(status_code=403, detail="Permessi di scrittura richiesti")
    
    try:
        # Verifica che la pianta esista
        plan = await db.execute(
            select(ArchaeologicalPlan).where(
                and_(
                    ArchaeologicalPlan.id == plan_id,
                    ArchaeologicalPlan.site_id == site_id
                )
            )
        )
        plan = plan.scalar_one_or_none()
        
        if not plan:
            raise HTTPException(status_code=404, detail="Pianta non trovata")
        
        # Verifica che il modulo esista
        module_id = data_payload.get("module_id")
        module = await db.execute(
            select(FormSchema).where(FormSchema.id == UUID(module_id))
        )
        module = module.scalar_one_or_none()
        
        if not module:
            raise HTTPException(status_code=404, detail="Modulo raccolta dati non trovato")
        
        # Crea record dati archeologici
        coordinates = data_payload.get("coordinates", {})
        
        data_record = ArchaeologicalData(
            site_id=site_id,
            plan_id=plan_id,
            excavation_unit_id=data_payload.get("excavation_unit_id"),
            module_id=UUID(module_id),
            coordinates_x=coordinates.get("x"),
            coordinates_y=coordinates.get("y"),
            elevation=coordinates.get("elevation"),
            data=data_payload.get("data", {}),
            collection_method=data_payload.get("collection_method", "digital"),
            accuracy=data_payload.get("accuracy"),
            collector_id=current_user_id
        )
        
        db.add(data_record)
        await db.commit()
        await db.refresh(data_record)
        
        logger.info(f"Archaeological data created: {data_record.id} for plan {plan_id}")
        
        return JSONResponse({
            "message": "Dato archeologico creato con successo",
            "data_id": str(data_record.id),
            "data": data_record.to_dict()
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating archaeological data: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Errore creazione dato: {str(e)}")


@plans_router.get("/sites/{site_id}/data-collection-modules")
async def get_data_collection_modules(
    site_id: UUID,
    site_access: tuple = Depends(get_site_access_for_plans),
    db: AsyncSession = Depends(get_async_session)
):
    """Ottieni moduli di raccolta dati disponibili per il sito"""
    site, permission = site_access
    
    if not permission.can_read():
        raise HTTPException(status_code=403, detail="Permessi di lettura richiesti")
    
    modules_query = select(FormSchema).where(
        and_(
            FormSchema.site_id == site_id,
            FormSchema.is_active == True
        )
    ).order_by(FormSchema.category, FormSchema.name)
    
    modules = await db.execute(modules_query)
    modules = modules.scalars().all()
    
    modules_data = []
    for module in modules:
        try:
            schema_data = json.loads(module.schema_json)
            modules_data.append({
                "id": str(module.id),
                "name": module.name,
                "description": module.description,
                "category": module.category,
                "icon": schema_data.get("icon", "📍"),
                "form_schema": schema_data
            })
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON in form schema {module.id}")
            continue
    
    return JSONResponse(modules_data)