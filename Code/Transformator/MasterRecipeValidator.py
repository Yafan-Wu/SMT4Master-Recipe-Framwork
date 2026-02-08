# Code/Transformator/MasterRecipeValidator.py
import re
from pathlib import Path
from lxml import etree

# =========================
# XML / XSD Validation
# =========================

def _guess_root_xsd(allschema_dir: str) -> str:
    p = Path(allschema_dir)
    xsds = sorted([x for x in p.rglob('*.xsd') if x.is_file()])
    if not xsds:
        raise FileNotFoundError(f"No .xsd files found under: {allschema_dir}")
    if len(xsds) == 1:
        return str(xsds[0])

    def score(x: Path):
        name = x.name.lower()
        kw = 0
        for k in ("master", "recipe", "b2mml"):
            if k in name:
                kw += 10
        depth = len(x.relative_to(p).parts)
        size = x.stat().st_size
        return (kw, -depth, size)

    return str(sorted(xsds, key=score, reverse=True)[0])


def validate_master_recipe_xml(master_recipe_xml_path: str,
                               allschema_dir: str,
                               root_xsd_path: str | None = None):
    xml_path = Path(master_recipe_xml_path)
    if not xml_path.exists():
        raise FileNotFoundError(xml_path)

    used_root = root_xsd_path or _guess_root_xsd(allschema_dir)
    parser = etree.XMLParser(remove_blank_text=True, recover=False, huge_tree=True)

    xml_doc = etree.parse(str(xml_path), parser)
    xsd_doc = etree.parse(str(used_root), parser)

    schema = etree.XMLSchema(xsd_doc)
    ok = schema.validate(xml_doc)

    if ok:
        return True, [], used_root

    errors = []
    for e in schema.error_log:
        loc = f"line {e.line}, col {e.column}" if e.line else "(no line)"
        errors.append(f"{loc}: {e.message}")

    return False, errors, used_root


# =========================
# Parameter Validation (UUID / OPC UA GUID)
# =========================

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{12}$"
)

_OPCUA_NODEID_GUID_RE = re.compile(
    r"^(?:ns=\d+;|nsu=[^;]+;)?[gG]=("
    r"[0-9a-fA-F]{8}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{12})$"
)

def _is_opcua_guid(s: str) -> bool:
    """
    Accepts OPC UA GUID formats:
      - 550e8400-e29b-41d4-a716-446655440000
      - ns=2;g=550e8400-e29b-41d4-a716-446655440000
      - nsu=urn:your:ns;g=550e8400-e29b-41d4-a716-446655440000
    Also tolerates a leading prefix before ":" (e.g. "res:...").
    """
    return bool(_extract_opcua_guid_from_id(s))


def _is_uuid(s: str) -> bool:
    return bool(s) and bool(_UUID_RE.fullmatch(s.strip()))


def _extract_uuid_from_id(raw_id: str) -> str | None:
    """
    Accepts:
      - 550e8400-e29b-41d4-a716-446655440000
      - res:550e8400-e29b-41d4-a716-446655440000
      - anyprefix:UUID
    """
    if not raw_id:
        return None
    s = raw_id.strip()
    if ":" in s:
        s = s.split(":", 1)[1].strip()
    return s if _is_uuid(s) else None

def _extract_opcua_guid_from_id(raw_id: str) -> str | None:
    """
    Extract GUID from OPC UA NodeId strings.
    Accepts:
      - 550e8400-e29b-41d4-a716-446655440000
      - res:550e8400-e29b-41d4-a716-446655440000
      - ns=2;g=550e8400-e29b-41d4-a716-446655440000
      - nsu=urn:your:ns;g=550e8400-e29b-41d4-a716-446655440000
      - res:ns=2;g=550e8400-e29b-41d4-a716-446655440000
    Returns the canonical GUID (xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx) or None.
    """
    if not raw_id:
        return None
    s = raw_id.strip()
    if ":" in s:
        s = s.split(":", 1)[1].strip()
    # plain GUID
    if _is_uuid(s):
        return s
    m = _OPCUA_NODEID_GUID_RE.fullmatch(s)
    if not m:
        return None
    return m.group(1)


def _looks_like_uuid_index(resources_data: dict) -> bool:
    """
    If caller already passed resources_data as {uuid -> meta}, detect it.
    """
    if not isinstance(resources_data, dict) or not resources_data:
        return False
    # If "most" keys are UUIDs, treat it as UUID index.
    keys = list(resources_data.keys())[:30]
    if not keys:
        return False
    uuidish = sum(1 for k in keys if isinstance(k, str) and _is_uuid(k.strip()))
    return uuidish >= max(1, int(len(keys) * 0.7))


def build_uuid_index_from_capabilities(resources_data: dict) -> tuple[dict, list[str]]:
    """
    Convert parsed AAS capabilities (structure used in Workers/Results) into:
        uuid_index = { uuid: {resource_key, resource, capability_name, property_name, unit, ...} }
    Supports both keys:
        - propertyRealizedBy
        - property_realized_by

    Returns: (uuid_index, warnings)
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
        # resource_key example: "resource: 2025-04_HC29"
        if not isinstance(caps_list, list):
            continue

        # best-effort resource name
        resource_name = None
        if isinstance(resource_key, str):
            # often "..._HC29" at end
            if "_" in resource_key:
                resource_name = resource_key.split("_")[-1].strip()
            else:
                resource_name = resource_key.strip()

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

                raw_uuid = prop.get("propertyRealizedBy")
                if not raw_uuid:
                    raw_uuid = prop.get("property_realized_by")

                if not raw_uuid or not isinstance(raw_uuid, str):
                    continue

                uuid = raw_uuid.strip()
                if not _is_uuid(uuid):
                    # some files contain "" or trailing spaces; ignore non-UUID values
                    continue

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

                # Duplicate UUID handling:
                if uuid in uuid_index:
                    prev = uuid_index[uuid]
                    # If duplicate refers to different place, warn once.
                    if (prev.get("resource_key") != entry.get("resource_key") or
                        prev.get("capability_name") != entry.get("capability_name") or
                        prev.get("property_name") != entry.get("property_name")):
                        warnings.append(
                            f"[UUID-INDEX] Duplicate UUID {uuid} found in multiple properties. "
                            f"Keeping first: {prev.get('resource_key')} / {prev.get('capability_name')} / {prev.get('property_name')}"
                        )
                    continue

                uuid_index[uuid] = entry

    return uuid_index, warnings


def validate_master_recipe_parameters(master_recipe_xml_path: str,
                                      resources_data: dict,
                                      id_format: str = "opca"):
    """
    Parameter ID validation.

    id_format:
      - "uuid": expects a plain UUID (optionally prefixed with "res:" or anyprefix:)
      - "opcua": accepts OPC UA GUID NodeId forms (plain UUID, or ns=...;g=UUID / nsu=...;g=UUID)

    Validation:
      - Parameter/ID must contain a valid UUID (optionally with prefix like "res:UUID")
      - UUID must exist in parsed AAS capability properties (propertyRealizedBy / property_realized_by)
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
                "raw_id": raw_id
            })
            continue

        if uuid not in uuid_index:
            errors.append(f"[UNKNOWN-UUID] {uuid} ({desc})")
            details.append({
                "status": "UNKNOWN_UUID",
                "description": desc,
                "uuid": uuid
            })
            continue

        hit = uuid_index[uuid]
        details.append({
            "status": "FOUND",
            "description": desc,
            "uuid": uuid,
            "resource_key": hit.get("resource_key"),
            "resource": hit.get("resource"),
            "capability_name": hit.get("capability_name"),
            "property_name": hit.get("property_name"),
            "property_unit": hit.get("property_unit"),
        })

    return len(errors) == 0, errors, warnings, checked, details
