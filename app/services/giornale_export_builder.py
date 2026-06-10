"""
Shared export model for Giornale di Cantiere PDF and Word documents.

Both renderers consume this structure so PDF and DOCX keep the same sections,
labels, ordering, and source data.
"""

from datetime import datetime
from typing import Any, Dict, List


def build_giornale_export_model(
    giornali: List[Dict[str, Any]],
    cantiere_info: Dict[str, Any],
    site_info: Dict[str, Any],
) -> Dict[str, Any]:
    generated_at = datetime.now()
    giornali = sorted(giornali or [], key=lambda g: str(g.get("data") or ""))

    cover_rows = compact_rows([
        ("Sito archeologico", optional_value(site_info.get("name"))),
        ("Cantiere", optional_value(cantiere_info.get("nome_completo") or cantiere_info.get("nome"))),
        ("Codice cantiere", optional_value(cantiere_info.get("codice"))),
        ("Oggetto", optional_value(cantiere_info.get("oggetto_appalto") or cantiere_info.get("nome"))),
        ("Committente", optional_value(cantiere_info.get("committente"))),
        ("Impresa esecutrice", optional_value(cantiere_info.get("impresa_esecutrice"))),
        ("Direttore dei lavori", optional_value(cantiere_info.get("direttore_lavori"))),
        ("Responsabile procedimento", optional_value(cantiere_info.get("responsabile_procedimento"))),
        ("Responsabile cantiere", optional_value(cantiere_info.get("responsabile_cantiere"))),
    ]) + [
        ("Giornali inclusi", str(len(giornali))),
        ("Documento generato", generated_at.strftime("%d/%m/%Y %H:%M")),
    ]

    summary_sections = numbered_table_sections([
        ("Quadro sintetico del cantiere", [
            ("Stato", optional_value(cantiere_info.get("stato_formattato"))),
            ("Priorita", optional_priority_label(cantiere_info.get("priorita"))),
            ("Cantiere in corso", optional_bool(cantiere_info.get("e_in_corso"))),
            ("Durata", f"{cantiere_info.get('durata_giorni')} giorni" if has_value(cantiere_info.get("durata_giorni")) else ""),
            ("Tipologia intervento", optional_value(cantiere_info.get("tipologia_intervento"))),
            ("Area", optional_value(cantiere_info.get("area_descrizione"))),
            ("Quota", optional_value(cantiere_info.get("quota"))),
            ("Coordinate", optional_coordinates(cantiere_info.get("coordinate_lat"), cantiere_info.get("coordinate_lon"))),
        ]),
        ("Cronologia", [
            ("Inizio previsto", optional_date_value(cantiere_info.get("data_inizio_prevista"))),
            ("Inizio effettivo", optional_date_value(cantiere_info.get("data_inizio_effettiva"))),
            ("Fine prevista", optional_date_value(cantiere_info.get("data_fine_prevista"))),
            ("Fine effettiva", optional_date_value(cantiere_info.get("data_fine_effettiva"))),
        ]),
        ("Dati amministrativi", [
            ("Codice CUP", optional_value(cantiere_info.get("codice_cup"))),
            ("Codice CIG", optional_value(cantiere_info.get("codice_cig"))),
            ("Importo lavori", optional_money(cantiere_info.get("importo_lavori"))),
        ]),
    ])

    model = {
        "title": "GIORNALE DEI LAVORI DI CANTIERE",
        "subtitle": "Registro operativo del cantiere archeologico",
        "generated_at": generated_at,
        "site_name": value(site_info.get("name")),
        "cantiere_name": value(cantiere_info.get("nome_completo") or cantiere_info.get("nome")),
        "cover_rows": cover_rows,
        "summary_sections": summary_sections,
        "giornali": [
            build_giornale_entry(giornale, index + 1, len(giornali))
            for index, giornale in enumerate(giornali)
        ],
        "signature_rows": [
            ("Responsabile di scavo", ""),
            ("Direttore dei lavori", ""),
            ("Responsabile del procedimento", ""),
            ("Rappresentante committenza", ""),
        ],
    }
    return model


def build_giornale_entry(giornale: Dict[str, Any], index: int, total: int) -> Dict[str, Any]:
    sections = [
        compact_table_section("1. Informazioni generali", [
            ("Data", date_value(giornale.get("data"))),
            ("Ora inizio", optional_value(giornale.get("ora_inizio"))),
            ("Ora fine", optional_value(giornale.get("ora_fine"))),
            ("Responsabile scavo", optional_value(giornale.get("responsabile_scavo") or giornale.get("responsabile_nome"))),
            ("Compilatore", optional_value(giornale.get("compilatore"))),
        ]),
        compact_table_section("2. Condizioni meteorologiche", meteo_rows(giornale)),
        text_section("3. Attivita e area di intervento", compact_items([
            ("Area di intervento", giornale.get("area_intervento")),
            ("Saggio", giornale.get("saggio")),
            ("Obiettivi", giornale.get("obiettivi")),
            ("Descrizione lavori", giornale.get("descrizione_lavori")),
            ("Modalita di lavorazione", giornale.get("modalita_lavorazioni")),
        ])),
        resource_section(giornale),
        text_section("5. Stratigrafia e risultati", compact_items([
            ("US elaborate", join_list(giornale.get("us_elaborate"))),
            ("USM elaborate", join_list(giornale.get("usm_elaborate"))),
            ("USR elaborate", join_list(giornale.get("usr_elaborate"))),
            ("Interpretazione", giornale.get("interpretazione")),
            ("Campioni prelevati", giornale.get("campioni_prelevati")),
            ("Strutture", giornale.get("strutture")),
        ])),
        text_section("6. Materiali e documentazione", compact_items([
            ("Materiali rinvenuti", giornale.get("materiali_rinvenuti")),
            ("Documentazione prodotta", giornale.get("documentazione_prodotta")),
            ("Forniture e materiali", giornale.get("forniture")),
        ])),
        text_section("7. Disposizioni ed eventi", compact_items([
            ("Disposizioni RUP", giornale.get("disposizioni_rup")),
            ("Disposizioni direttore lavori", giornale.get("disposizioni_direttore")),
            ("Sospensioni", giornale.get("sospensioni")),
            ("Contestazioni", giornale.get("contestazioni")),
            ("Incidenti", giornale.get("incidenti")),
            ("Problematiche", giornale.get("problematiche")),
            ("Sopralluoghi", giornale.get("sopralluoghi")),
            ("Note generali", giornale.get("note_generali")),
        ])),
        media_section(giornale),
        compact_table_section("9. Validazione", [
            ("Validato", optional_bool(giornale.get("validato"))),
            ("Data validazione", optional_date_value(giornale.get("data_validazione"))),
            ("Data creazione", optional_date_value(giornale.get("created_at"))),
            ("Ultimo aggiornamento", optional_date_value(giornale.get("updated_at"))),
        ]),
    ]

    return {
        "heading": f"Giornale {index}/{total} - {date_value(giornale.get('data'))}",
        "sections": [section for section in sections if section_has_content(section)],
    }


def resource_section(giornale: Dict[str, Any]) -> Dict[str, Any]:
    operator_rows = []
    for op in giornale.get("operatori_presenti") or []:
        operator_rows.append([
            value(f"{op.get('nome', '')} {op.get('cognome', '')}".strip()),
            value(op.get("qualifica")),
            value(op.get("ore_lavorate") or "8"),
            value(op.get("note_presenza")),
        ])

    return {
        "title": "4. Risorse impiegate",
        "kind": "mixed",
        "items": compact_items([
            ("Attrezzature", giornale.get("attrezzatura_utilizzata")),
            ("Mezzi", giornale.get("mezzi_utilizzati")),
        ]),
        "tables": [
            {
                "title": "Operatori presenti",
                "headers": ["Nome", "Qualifica", "Ore", "Note"],
                "rows": operator_rows,
            }
        ] if operator_rows else [],
    }


def media_section(giornale: Dict[str, Any]) -> Dict[str, Any]:
    foto_rows = []
    photos = []
    for idx, foto in enumerate(giornale.get("foto") or [], 1):
        title = value(foto.get("title") or foto.get("original_filename") or foto.get("filename"))
        description = value(foto.get("description"))
        foto_rows.append([
            str(idx),
            title,
            description,
        ])
        photos.append({
            "index": idx,
            "title": title,
            "description": description,
            "image_bytes": foto.get("_image_bytes"),
        })

    allegati = giornale.get("allegati_paths") or []
    if isinstance(allegati, str):
        allegati = [allegati] if allegati.strip() else []

    return {
        "title": "8. Foto e allegati",
        "kind": "mixed",
        "items": compact_items([
            ("Foto collegate", str(len(foto_rows)) if foto_rows else None),
            ("Allegati", ", ".join(str(item) for item in allegati) if allegati else None),
        ]),
        "tables": [
            {
                "title": "Documentazione fotografica",
                "headers": ["N.", "Titolo/file", "Descrizione"],
                "rows": foto_rows,
            }
        ] if foto_rows else [],
        "photos": photos,
    }


def table_section(title: str, rows: List[Any]) -> Dict[str, Any]:
    return {"title": title, "kind": "table", "rows": rows}


def compact_table_section(title: str, rows: List[Any]) -> Dict[str, Any]:
    return table_section(title, compact_rows(rows))


def text_section(title: str, items: List[Any]) -> Dict[str, Any]:
    return {"title": title, "kind": "text", "items": items}


def compact_items(items: List[Any]) -> List[Any]:
    return [(label, value(text)) for label, text in items if has_value(text)]


def compact_rows(rows: List[Any]) -> List[Any]:
    return [(label, str(text).strip()) for label, text in rows if is_display_value(text)]


def numbered_table_sections(sections: List[Any]) -> List[Dict[str, Any]]:
    compacted = []
    for title, rows in sections:
        clean_rows = compact_rows(rows)
        if clean_rows:
            compacted.append((title, clean_rows))
    return [
        table_section(f"{index}. {title}", rows)
        for index, (title, rows) in enumerate(compacted, 1)
    ]


def section_has_content(section: Dict[str, Any]) -> bool:
    kind = section.get("kind")
    if kind == "table":
        return bool(section.get("rows"))
    if kind == "text":
        return bool(section.get("items"))
    if kind == "mixed":
        return bool(section.get("items") or section.get("tables") or section.get("photos"))
    return True


def meteo_rows(giornale: Dict[str, Any]) -> List[Any]:
    temps = []
    if has_value(giornale.get("temperatura")):
        temps.append(f"attuale {giornale.get('temperatura')} C")
    if has_value(giornale.get("temperatura_min")):
        temps.append(f"min {giornale.get('temperatura_min')} C")
    if has_value(giornale.get("temperatura_max")):
        temps.append(f"max {giornale.get('temperatura_max')} C")
    return [
        ("Condizioni", optional_value(str(giornale.get("condizioni_meteo")).upper() if has_value(giornale.get("condizioni_meteo")) else None)),
        ("Temperatura", ", ".join(temps) if temps else ""),
        ("Note meteo", optional_value(giornale.get("note_meteo"))),
    ]


def value(raw: Any) -> str:
    if not has_value(raw):
        return "N/D"
    return str(raw).strip()


def has_value(raw: Any) -> bool:
    if raw is None:
        return False
    if isinstance(raw, str):
        return bool(raw.strip())
    if isinstance(raw, (list, tuple, set, dict)):
        return bool(raw)
    return True


def is_display_value(raw: Any) -> bool:
    if not has_value(raw):
        return False
    text = str(raw).strip()
    return text not in {"N/D", "None"}


def optional_value(raw: Any) -> str:
    return str(raw).strip() if has_value(raw) else ""


def optional_bool(raw: Any) -> str:
    if raw is None:
        return ""
    return "Si" if raw else "No"


def join_list(raw: Any) -> str:
    if not raw:
        return ""
    if isinstance(raw, str):
        return raw
    return ", ".join(str(item) for item in raw)


def date_value(raw: Any) -> str:
    if not has_value(raw):
        return "N/D"
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).strftime("%d/%m/%Y")
        except ValueError:
            return raw
    try:
        return raw.strftime("%d/%m/%Y")
    except AttributeError:
        return str(raw)


def optional_date_value(raw: Any) -> str:
    return date_value(raw) if has_value(raw) else ""


def priority_label(raw: Any) -> str:
    if not has_value(raw):
        return "N/D"
    try:
        priority = int(raw)
    except (TypeError, ValueError):
        return value(raw)
    if priority >= 4:
        label = "alta"
    elif priority >= 2:
        label = "media"
    else:
        label = "bassa"
    return f"{priority}/5 - {label}"


def optional_priority_label(raw: Any) -> str:
    return priority_label(raw) if has_value(raw) else ""


def coordinates(lat: Any, lon: Any) -> str:
    if not has_value(lat) or not has_value(lon):
        return "N/D"
    return f"{lat}, {lon}"


def optional_coordinates(lat: Any, lon: Any) -> str:
    return coordinates(lat, lon) if has_value(lat) and has_value(lon) else ""


def money(raw: Any) -> str:
    if not has_value(raw):
        return "N/D"
    try:
        return f"EUR {float(raw):,.2f}"
    except (TypeError, ValueError):
        return value(raw)


def optional_money(raw: Any) -> str:
    return money(raw) if has_value(raw) else ""
