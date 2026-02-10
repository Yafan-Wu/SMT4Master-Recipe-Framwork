# Code/Transformator/MasterRecipeValidator.py
import re
from pathlib import Path
from lxml import etree

# ==========================================================
# XSD picking + XML validation (keeps old public API)
# ==========================================================

def _guess_root_xsd(allschema_dir: str) -> str:
    p = Path(allschema_dir)
    xsds = sorted([x for x in p.rglob("*.xsd") if x.is_file()])
    # prefer masterrecipe.xsd if present

    allschemas = next(iter(p.rglob("AllSchemas.xsd")), None)
    if allschemas:
        return str(allschemas)
    batchinfo = next(iter(p.rglob("BatchML-BatchInformation.xsd")), None)
    if batchinfo:
        return str(batchinfo)
    for x in p.rglob("*.xsd"):
        if "masterrecipe" in x.name.lower():
             return str(x)
    xsds = sorted([x for x in p.rglob("*.xsd") if x.is_file()],
                  key=lambda x: x.stat().st_size, reverse=True)
    return str(xsds[0]) if xsds else ""


def validate_master_recipe_xml(
    master_recipe_xml_path: str,
    allschema_dir: str,
    root_xsd_path: str | None = None
) -> tuple[bool, list[str], str | None]:
    """
    BACKWARD-COMPAT API expected by Results.py / Workers.py

    Returns: (ok, errors, used_root_xsd_path)
    """
    used_root = root_xsd_path or _guess_root_xsd(allschema_dir)
    if not used_root:
        return False, [f"[XSD] No .xsd found under: {allschema_dir}"], None

    try:
        xml_doc = etree.parse(str(master_recipe_xml_path))
    except Exception as e:
        return False, [f"[XML] Failed to parse XML: {e}"], used_root

    try:
        xsd_doc = etree.parse(str(used_root))
        schema = etree.XMLSchema(xsd_doc)
    except Exception as e:
        return False, [f"[XSD] Failed to parse XSD ({used_root}): {e}"], used_root

    ok = schema.validate(xml_doc)
    errors: list[str] = []
    if not ok:
        for err in schema.error_log:
            errors.append(f"[XSD] {err}")
    return ok, errors, used_root


# ==========================================================
# UUID checker
# ==========================================================

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{12}$"
)


def _is_uuid(s: str) -> bool:
    return bool(_UUID_RE.match(s or ""))


def _extract_uuid_from_id(raw_id: str) -> str | None:
    """
    Extract UUID from formats like:
      - UUID
      - prefix:UUID
      - res:UUID
      - ...UUID... (UUID embedded)
    """
    if not raw_id:
        return None

    rid = raw_id.strip()
    if _is_uuid(rid):
        return rid

    if ":" in rid:
        last = rid.split(":")[-1].strip()
        if _is_uuid(last):
            return last

    m = re.search(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
        rid,
    )
    if m:
        u = m.group(0)
        if _is_uuid(u):
            return u

    return None


def _extract_opcua_guid_from_id(raw_id: str) -> str | None:
    """
    Extract GUID UUID from OPC UA NodeId forms such as:
      - ns=2;g=UUID
      - nsu=...;g=UUID
      - UUID
    """
    if not raw_id:
        return None

    rid = raw_id.strip()

    # allow plain UUID / prefix:UUID / embedded UUID
    u = _extract_uuid_from_id(rid)
    if u:
        return u

    # parse 'g=' segment
    m = re.search(r"(?:^|;)\s*g\s*=\s*([0-9a-fA-F\-]{36})\s*(?:;|$)", rid)
    if m:
        u = m.group(1).strip()
        if _is_uuid(u):
            return u

    return _extract_uuid_from_id(rid)


def _looks_like_uuid_index(resources_data: dict) -> bool:
    """
    Heuristic: if dict keys are UUIDs and values are dict entries or list entries.
    """
    if not isinstance(resources_data, dict) or not resources_data:
        return False
    sample = list(resources_data.keys())[:3]
    if not sample:
        return False
    uuid_like = sum(1 for k in sample if isinstance(k, str) and _is_uuid(k)) >= 2
    if not uuid_like:
        return False
    v = resources_data.get(sample[0])
    return isinstance(v, dict) or isinstance(v, list)


# ==========================================================
# Deep UUID extraction from arbitrary prop structures
# ==========================================================

def _collect_uuids_anywhere(obj) -> list[str]:
    """
    Recursively collect UUID strings from nested dict/list/str.
    """
    found = set()

    def walk(x):
        if x is None:
            return
        if isinstance(x, str):
            matches = re.findall(
                r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
                x,
            )
            for u in matches:
                if _is_uuid(u):
                    found.add(u)
            return
        if isinstance(x, dict):
            for v in x.values():
                walk(v)
            return
        if isinstance(x, (list, tuple, set)):
            for v in x:
                walk(v)
            return

    walk(obj)
    return list(found)


def _extract_uuids_from_prop(prop: dict) -> list[str]:
    """
    Return list of UUID candidates from a property dict.
    Tries common keys first, then falls back to recursive scan.
    """
    if not isinstance(prop, dict):
        return []

    # Common key variants across different parsers / formats
    key_candidates = [
        # original keys
        "propertyRealizedBy", "property_realized_by",
        # capitalization / spelling variants
        "PropertyRealizedBy", "propertyRealisedBy", "property_realised_by", "PropertyRealisedBy",
        "realizedBy", "realisedBy",
        # reference-ish containers (often nested)
        "semanticId", "semanticID", "semantic_id",
        "reference", "ref", "references",
        "id", "ID", "identifier",
    ]

    uuids: list[str] = []

    # 1) Try candidate keys
    for k in key_candidates:
        if k not in prop:
            continue
        v = prop.get(k)
        if isinstance(v, str):
            u = _extract_uuid_from_id(v)
            if u:
                uuids.append(u)
            else:
                uuids.extend(_collect_uuids_anywhere(v))
        else:
            uuids.extend(_collect_uuids_anywhere(v))

    # 2) If still nothing, scan entire prop (more aggressive)
    if not uuids:
        uuids = _collect_uuids_anywhere(prop)

    # De-dup while preserving order
    deduped = []
    seen = set()
    for u in uuids:
        if not _is_uuid(u):
            continue
        if u in seen:
            continue
        seen.add(u)
        deduped.append(u)
    return deduped


# ==========================================================
# Capability -> UUID index (store ALL candidates)
# ==========================================================

def build_uuid_index_from_capabilities(resources_data: dict) -> tuple[dict, list[str]]:
    """
    Build uuid_index = { uuid: [entry, entry, ...] }

    entry contains:
      resource_key, resource, capability_name, property_name, property_unit, ...
    """
    warnings: list[str] = []
    uuid_index: dict = {}

    if not resources_data:
        return uuid_index, warnings

    # If already UUID-indexed, just return it
    if _looks_like_uuid_index(resources_data):
        return resources_data, warnings

    if not isinstance(resources_data, dict):
        warnings.append("[UUID-INDEX] resources_data is not a dict; cannot build UUID index.")
        return uuid_index, warnings

    for resource_key, caps_list in resources_data.items():
        # derive a short resource name (often HCxx) from the key
        resource_name = None
        if isinstance(resource_key, str):
            if "_" in resource_key:
                resource_name = resource_key.split("_")[-1].strip()
            else:
                resource_name = resource_key.strip()

        if not isinstance(caps_list, list):
            continue

        for block in caps_list:
            if not isinstance(block, dict):
                continue

            cap_name = None
            caps = block.get("capability") or []
            if isinstance(caps, list) and caps:
                c0 = caps[0]
                if isinstance(c0, dict):
                    cap_name = c0.get("capability_name") or c0.get("name")

            props = block.get("properties") or []
            if not isinstance(props, list):
                continue

            for prop in props:
                if not isinstance(prop, dict):
                    continue

                uuids = _extract_uuids_from_prop(prop)
                if not uuids:
                    continue

                for uuid in uuids:
                    entry = {
                        "uuid": uuid,
                        "resource_key": resource_key,
                        "resource": resource_name,
                        "capability_name": cap_name,
                        "property_name": prop.get("property_name"),
                        "property_ID": prop.get("property_ID"),
                        "property_unit": prop.get("property_unit"),
                        "valueType": prop.get("valueType"),
                        "raw_property": prop,
                    }

                    if uuid in uuid_index:
                        uuid_index[uuid].append(entry)
                        prev = uuid_index[uuid][0]
                        if (
                            prev.get("resource_key") != entry.get("resource_key")
                            or prev.get("capability_name") != entry.get("capability_name")
                            or prev.get("property_name") != entry.get("property_name")
                        ):
                            warnings.append(
                                f"[UUID-INDEX] Duplicate UUID {uuid} found in multiple properties. "
                                f"Candidates now: {len(uuid_index[uuid])}. "
                                f"First: {prev.get('resource_key')} / {prev.get('capability_name')} / {prev.get('property_name')}"
                            )
                    else:
                        uuid_index[uuid] = [entry]

    return uuid_index, warnings


# ==========================================================
# MasterRecipe Parameter Validation (HCxx preference)
# ==========================================================

def validate_master_recipe_parameters(
    master_recipe_xml_path: str,
    resources_data: dict,
    id_format: str = "opcua"
):
    """
    Returns:
      ok(bool), errors(list[str]), warnings(list[str]), checked(int), details(list[dict])

    Validation:
      - Extract UUID from Parameter/ID (uuid / prefix:uuid / OPC UA g=uuid)
      - UUID must exist in uuid_index built from capabilities

    HC preference:
      If UUID has multiple candidates, prefer candidate whose resource_key/resource matches HC token
      extracted from Description (e.g. 'HC29_...').
    """
    parser = etree.XMLParser(remove_blank_text=True, recover=True, huge_tree=True)
    doc = etree.parse(str(master_recipe_xml_path), parser)

    params = doc.findall('.//{*}MasterRecipe//{*}Formula//{*}Parameter')

    uuid_index, idx_warnings = build_uuid_index_from_capabilities(resources_data)

    errors: list[str] = []
    warnings: list[str] = []
    warnings.extend(idx_warnings)

    details: list[dict] = []
    checked = 0

    for p in params:
        desc_el = p.find('./{*}Description')
        desc = (desc_el.text or "").strip() if desc_el is not None else ""

        id_el = p.find('./{*}ID')
        raw_id = (id_el.text or "").strip() if id_el is not None else ""

        if id_format.lower() in {"opcua", "opcua_guid", "opcua-nodeid"}:
            uuid = _extract_opcua_guid_from_id(raw_id)
        else:
            uuid = _extract_uuid_from_id(raw_id)

        checked += 1

        if not uuid:
            errors.append(f"[INVALID-ID] {desc or '(no description)'}: {raw_id}")
            details.append({
                "status": "INVALID_ID",
                "description": desc,
                "raw_id": raw_id,
            })
            continue

        if uuid not in uuid_index:
            errors.append(f"[UNKNOWN-UUID] {uuid} ({desc})")
            details.append({
                "status": "UNKNOWN_UUID",
                "description": desc,
                "uuid": uuid,
            })
            continue

        cands = uuid_index[uuid]
        if isinstance(cands, dict):
            cands = [cands]

        # IMPORTANT: works for "HC29_..." (no \b word-boundary)
        m = re.search(r"(HC\d+)", desc or "")
        expected_hc = m.group(1) if m else None

        hit = None
        if expected_hc:
            # 1) Prefer resource_key containing the HC token (e.g. "..._HC29")
            for c in cands:
                rk = (c.get("resource_key") or "")
                if expected_hc in str(rk):
                    hit = c
                    break
            # 2) Or the derived resource name equals HCxx
            if hit is None:
                for c in cands:
                    if (c.get("resource") or "").strip() == expected_hc:
                        hit = c
                        break

            # If multiple candidates exist but none match expected HC, log a hint
            if hit is None and len(cands) > 1:
                cand_keys = [str(c.get("resource_key")) for c in cands]
                warnings.append(
                    f"[HC-PREF] {desc}: expected {expected_hc}, but candidates are: {cand_keys}"
                )

        # 3) Fallback: first candidate
        if hit is None:
            hit = cands[0]

        details.append({
            "status": "FOUND",
            "description": desc,
            "uuid": uuid,
            "resource_key": hit.get("resource_key"),
            "resource": hit.get("resource"),
            "capability_name": hit.get("capability_name"),
            "property_name": hit.get("property_name"),
            "property_unit": hit.get("property_unit"),
            "candidates_count": len(cands),
        })

    return len(errors) == 0, errors, warnings, checked, details
