# Linee Guida Enum - FastZoom

## Scopo

Nel progetto i valori enum salvati a DB devono essere stabili e coerenti.
Per questo input utente (anche in italiano) viene normalizzato tramite mapping centralizzato.

Riferimenti:

- `app/models/archaeological_enums.py` e modelli correlati
- `app/utils/enum_mappings.py`

## Regole Operative

1. Salvare a DB solo il valore canonicale previsto dall'enum.
2. Convertire input libero prima della persistenza.
3. Non creare conversioni ad-hoc nei router.
4. Loggare conversioni ambigue/fallback.

## Uso Corretto

Esempio tipico nel service layer:

```python
from app.utils.enum_mappings import enum_converter

photo_type = enum_converter.convert_to_enum(PhotoType, payload.get("photo_type"))
if photo_type is None:
    raise ValueError("photo_type non valido")
```

## Aggiungere un Nuovo Enum

1. Definire l'enum nel layer modelli.
2. Aggiungere mapping in `EnumConverter`.
3. Registrare l'enum in `ENUM_CLASS_MAPPINGS`.
4. Coprire casi frequenti (sinonimi/alias) senza eccessi.
5. Aggiungere test unitari.

## Best Practice

- Mantenere mapping piccoli e spiegabili.
- Preferire alias espliciti a regex aggressive.
- Evitare side-effect: la conversione deve essere pura e deterministica.
- Trattare `None`/stringhe vuote in modo coerente.

## Anti-Pattern da Evitare

- Conversione inline duplicata in piu endpoint.
- Salvataggio diretto di testo utente senza validazione enum.
- Mapping che cambiano semantica (es. alias troppo generici).
