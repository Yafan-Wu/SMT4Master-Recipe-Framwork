# Code/GUI/Workers.py
import sys
import os
import traceback
import re
from pathlib import Path
from PyQt6.QtCore import QThread, pyqtSignal

# [NEW] XML/XSD validation support for exported Master Recipe
from lxml import etree

# 引入后端函数
try:
    from Code.SMT4ModPlant.GeneralRecipeParser import parse_general_recipe
    from Code.SMT4ModPlant.AASxmlCapabilityParser import parse_capabilities_robust
    from Code.SMT4ModPlant.SMT4ModPlant_main import run_optimization
    from Code.Optimizer.Optimization import SolutionOptimizer
except ImportError as e:
    print("Import Error inside Workers.py: Could not load backend modules.")
    print(f"Specific Error: {e}")


# =========================
# Master Recipe Validation
# =========================
def _guess_root_xsd(allschema_dir: str) -> str:
    """Best-effort guess of the root XSD inside an allschema folder.

    Strategy:
    1) If only one .xsd exists -> use it.
    2) Prefer names containing 'master' or 'recipe' or 'b2mml'.
    3) Otherwise pick the largest .xsd (often the root) as a fallback.
    """
    p = Path(allschema_dir)
    xsds = sorted([x for x in p.rglob('*.xsd') if x.is_file()])
    if not xsds:
        raise FileNotFoundError(f"No .xsd files found under: {allschema_dir}")
    if len(xsds) == 1:
        return str(xsds[0])

    def score(x: Path) -> tuple:
        name = x.name.lower()
        kw = 0
        for k in ("master", "recipe", "b2mml"):
            if k in name:
                kw += 10
        # Prefer files at folder root (shallower)
        depth = len(x.relative_to(p).parts)
        # Prefer larger
        size = x.stat().st_size
        return (kw, -depth, size)

    xsds_sorted = sorted(xsds, key=score, reverse=True)
    return str(xsds_sorted[0])


def validate_master_recipe_xml(master_recipe_xml_path: str, allschema_dir: str, root_xsd_path: str | None = None):
    """Validate a B2MML master recipe XML against XSD(s) in allschema folder.

    Args:
        master_recipe_xml_path: Path to exported MasterRecipe_*.xml
        allschema_dir: Folder that contains XSD set (with includes/imports)
        root_xsd_path: Optional explicit root XSD. If None, we guess.

    Returns:
        (ok: bool, errors: list[str], used_root_xsd: str)
    """
    xml_path = Path(master_recipe_xml_path)
    if not xml_path.exists():
        raise FileNotFoundError(f"Master recipe XML not found: {master_recipe_xml_path}")

    schema_dir = Path(allschema_dir)
    if not schema_dir.exists() or not schema_dir.is_dir():
        raise NotADirectoryError(f"allschema folder not found: {allschema_dir}")

    used_root = root_xsd_path or _guess_root_xsd(allschema_dir)
    xsd_path = Path(used_root)
    if not xsd_path.exists():
        raise FileNotFoundError(f"Root XSD not found: {used_root}")

    # Parse XML and XSD with proper base_url so relative includes/imports work
    parser = etree.XMLParser(remove_blank_text=True, recover=False, huge_tree=True)
    xml_doc = etree.parse(str(xml_path), parser)

    xsd_doc = etree.parse(str(xsd_path), parser)
    schema = etree.XMLSchema(xsd_doc)

    ok = schema.validate(xml_doc)
    if ok:
        return True, [], str(xsd_path)

    # Collect readable errors
    errors = []
    for e in schema.error_log:
        loc = f"line {e.line}, col {e.column}" if e.line else "(no line)"
        errors.append(f"{loc}: {e.message}")
    return False, errors, str(xsd_path)


# =========================
# Parameter Validation (Master Recipe vs parsed AAS)
# =========================

def _walk_any(obj):
    """Yield (path, key, value) tuples for dict/list structures."""
    stack = [("", obj)]
    while stack:
        path, cur = stack.pop()
        if isinstance(cur, dict):
            for k, v in cur.items():
                p = f"{path}.{k}" if path else str(k)
                yield (p, k, v)
                stack.append((p, v))
        elif isinstance(cur, list):
            for idx, v in enumerate(cur):
                p = f"{path}[{idx}]"
                yield (p, idx, v)
                stack.append((p, v))


def _normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

def _is_uuid(s: str) -> bool:
    return bool(s) and bool(_UUID_RE.match(s.strip()))

def _tokenize(s: str) -> list[str]:
    """Tokenize a string into lower-case alnum tokens, keeping numbers, dropping very short tokens."""
    if not s:
        return []
    parts = re.split(r"[^A-Za-z0-9]+", s.lower())
    toks = [p for p in parts if p and len(p) >= 2]
    return toks

def _score_tokens(needle_tokens: list[str], cand_tokens: list[str]) -> float:
    if not needle_tokens:
        return 0.0
    ns = set(needle_tokens)
    cs = set(cand_tokens)
    if not cs:
        return 0.0
    inter = ns & cs
    return len(inter) / max(1, len(ns))

def _collect_strings(obj) -> set[str]:
    """Collect all string-like tokens from nested structures."""
    out = set()
    for _, k, v in _walk_any(obj):
        if isinstance(k, str) and k:
            out.add(k)
        if isinstance(v, str) and v:
            out.add(v)
    return out


def _find_resource_key(resources_data: dict, hint: str) -> str | None:
    """Try to map 'HC29' -> a key in resources_data like 'resource: 2025-04_HC29'."""
    if not resources_data or not hint:
        return None
    hint_n = _normalize(hint)
    best = None
    for k in resources_data.keys():
        kn = _normalize(k)
        if hint_n and hint_n in kn:
            if best is None or len(kn) < len(_normalize(best)):
                best = k
    return best


def _extract_param_parts(desc: str) -> tuple[str | None, str]:
    """From 'HC29_Revolutions_per_minute' -> ('HC29', 'Revolutions_per_minute')."""
    if not desc:
        return None, ""
    m = re.match(r"^([A-Za-z]{1,5}\d{1,6})[\s_\-:]+(.+)$", desc.strip())
    if m:
        return m.group(1), m.group(2)
    return None, desc.strip()


def _try_extract_unit_and_constraints(obj) -> tuple[str | None, float | None, float | None, set[str] | None]:
    """Best-effort: scan dict for unit/min/max/enum/allowedValues."""
    unit = None
    min_v = None
    max_v = None
    enums = None

    unit_keys = {"unit", "uom", "unitofmeasure", "unit_of_measure", "unitofmeas", "measureunit"}
    min_keys = {"min", "minimum", "lower", "low", "minvalue"}
    max_keys = {"max", "maximum", "upper", "high", "maxvalue"}
    enum_keys = {"allowedvalues", "enum", "enumeration", "values", "allowed", "permittedvalues"}

    for _, k, v in _walk_any(obj):
        if isinstance(k, str):
            kn = _normalize(k)
            if unit is None and kn in unit_keys and isinstance(v, str) and v.strip():
                unit = v.strip()
            if min_v is None and kn in min_keys:
                try:
                    min_v = float(v)
                except Exception:
                    pass
            if max_v is None and kn in max_keys:
                try:
                    max_v = float(v)
                except Exception:
                    pass
            if enums is None and kn in enum_keys:
                if isinstance(v, list):
                    enums = {str(x) for x in v if str(x).strip()}
                elif isinstance(v, str) and v.strip():
                    import re as _re
                    parts = _re.split(r"[;,|\n]+", v)
                    enums = {p.strip() for p in parts if p.strip()}
    return unit, min_v, max_v, enums


def validate_master_recipe_parameters(master_recipe_xml_path: str, resources_data: dict):
    """Validate that parameters in a MasterRecipe XML exist in parsed AAS capabilities.

    Matching priority:
      1) If Parameter/ID contains a UUID (e.g. '002:4f60...'), try to match that UUID inside parsed AAS first.
      2) Otherwise match by Parameter/Description (and its suffix without the 'HCxx_' prefix) using token overlap.

    Notes:
      - We log *FOUND* items into `details` so the UI can show full matches.
      - We also compute and store the closest candidate when missing.

    Returns:
        ok: bool
        errors: list[str]
        warnings: list[str]
        checked: int
        details: list[dict]
    """
    xml_path = Path(master_recipe_xml_path)
    if not xml_path.exists():
        raise FileNotFoundError(f"Master recipe XML not found: {master_recipe_xml_path}")
    if not isinstance(resources_data, dict) or not resources_data:
        raise ValueError("No parsed AAS resources available for parameter validation.")

    parser = etree.XMLParser(remove_blank_text=True, recover=True, huge_tree=True)
    doc = etree.parse(str(xml_path), parser)

    params = doc.findall('.//{*}MasterRecipe//{*}Formula//{*}Parameter')
    errors: list[str] = []
    warnings: list[str] = []
    details: list[dict] = []
    checked = 0

    for p in params:
        desc_el = p.find('./{*}Description')
        desc = (desc_el.text or '').strip() if desc_el is not None else ''
        if not desc:
            continue

        id_el = p.find('./{*}ID')
        raw_id = (id_el.text or '').strip() if id_el is not None else ''
        uuid = None
        if raw_id and ":" in raw_id:
            maybe = raw_id.split(":", 1)[1].strip()
            if _is_uuid(maybe):
                uuid = maybe

        val_el = p.find('./{*}Value/{*}ValueString')
        val_str = (val_el.text or '').strip() if val_el is not None else ''

        uom_el = p.find('./{*}Value/{*}UnitOfMeasure')
        uom = (uom_el.text or '').strip() if uom_el is not None else None

        res_hint, param_name = _extract_param_parts(desc)

        # Build needles
        needles: list[str] = []
        if uuid:
            needles.append(uuid)
        needles.append(desc)
        if param_name and param_name != desc:
            needles.append(param_name)

        # Token-based needle for fuzzy matching (ignore the HCxx prefix token)
        desc_tokens = [t for t in _tokenize(desc) if not re.fullmatch(r"[a-z]{1,5}\d{1,6}", t)]
        name_tokens = [t for t in _tokenize(param_name) if not re.fullmatch(r"[a-z]{1,5}\d{1,6}", t)]
        needle_tokens = desc_tokens or name_tokens

        scope_key = _find_resource_key(resources_data, res_hint) if res_hint else None
        scopes = [(scope_key, resources_data.get(scope_key))] if scope_key else list(resources_data.items())

        found = False
        matched_resource = None
        matched_candidate = None
        best_score = 0.0

        found_unit = None
        found_min = None
        found_max = None
        found_enums = None

        # Search
        for rk, rdata in scopes:
            if rdata is None:
                continue

            strings = list(_collect_strings(rdata))
            if not strings:
                continue

            # Fast path: UUID exact match anywhere
            if uuid:
                for s in strings:
                    if isinstance(s, str) and uuid.lower() in s.lower():
                        found = True
                        matched_resource = rk
                        matched_candidate = s
                        best_score = 1.0
                        break
                if found:
                    found_unit, found_min, found_max, found_enums = _try_extract_unit_and_constraints(rdata)
                    break

            # Otherwise compute best token overlap score
            for s in strings:
                if not isinstance(s, str) or not s.strip():
                    continue
                cand_tokens = _tokenize(s)
                sc = _score_tokens(needle_tokens, cand_tokens)
                if sc > best_score:
                    best_score = sc
                    matched_candidate = s
                    matched_resource = rk

            # Accept if score passes threshold
            # 0.60 means at least 60% of needle tokens appear in the candidate
            if best_score >= 0.60:
                found = True
                found_unit, found_min, found_max, found_enums = _try_extract_unit_and_constraints(rdata)
                break

        checked += 1

        if not found:
            # Missing
            if scope_key:
                errors.append(f"[MISSING] {desc} not found in parsed AAS for resource: {scope_key}")
                details.append({
                    "status": "MISSING",
                    "description": desc,
                    "resource_hint": scope_key,
                    "matched_resource": matched_resource,
                    "matched_candidate": matched_candidate,
                    "score": float(best_score),
                    "uuid": uuid,
                })
            else:
                errors.append(f"[MISSING] {desc} not found in parsed AAS resources")
                details.append({
                    "status": "MISSING",
                    "description": desc,
                    "resource_hint": None,
                    "matched_resource": matched_resource,
                    "matched_candidate": matched_candidate,
                    "score": float(best_score),
                    "uuid": uuid,
                })
            continue

        # Found
        details.append({
            "status": "FOUND",
            "description": desc,
            "matched_resource": matched_resource,
            "matched_candidate": matched_candidate,
            "score": float(best_score),
            "uuid": uuid,
        })

        # Optional unit check
        if uom and found_unit and _normalize(uom) != _normalize(found_unit):
            warnings.append(f"[UNIT] {desc}: MasterRecipe unit='{uom}' vs AAS unit='{found_unit}'")

        # Optional range / enum checks (best-effort)
        if val_str:
            if found_enums:
                if val_str not in found_enums and _normalize(val_str) not in {_normalize(x) for x in found_enums}:
                    preview = sorted(list(found_enums))
                    errors.append(
                        f"[ENUM] {desc}: value '{val_str}' not in allowed set {preview[:8]}{'...' if len(preview)>8 else ''}"
                    )
            try:
                v = float(val_str)
                if found_min is not None and v < found_min:
                    errors.append(f"[RANGE] {desc}: value {v} < min {found_min}")
                if found_max is not None and v > found_max:
                    errors.append(f"[RANGE] {desc}: value {v} > max {found_max}")
            except Exception:
                pass

    ok = len(errors) == 0
    return ok, errors, warnings, checked, details

class SMTWorker(QThread):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, int)
    # [MODIFIED] Signal now carries (gui_data_list, context_dict)
    finished_signal = pyqtSignal(list, dict)
    error_signal = pyqtSignal(str)

    def __init__(self, recipe_path, resource_dir, mode_index, weights):
        super().__init__()
        self.recipe_path = recipe_path
        self.resource_dir = resource_dir
        self.mode_index = mode_index # 0:Fast, 1:Pro, 2:Ultra
        self.weights = weights 

    def run(self):
        try:
            # 1. Parsing
            self.log_signal.emit(f"Parsing Recipe: {self.recipe_path}")
            recipe_data = parse_general_recipe(self.recipe_path)
            self.progress_signal.emit(10, 100)

            self.log_signal.emit(f"Scanning resource directory: {self.resource_dir}")
            resource_files = [f for f in os.listdir(self.resource_dir) if f.lower().endswith('.xml') or f.lower().endswith('.aasx')]
            
            if not resource_files:
                raise FileNotFoundError("No .xml or .aasx files found in the selected directory.")

            all_capabilities = {}
            total_files = len(resource_files)
            
            for idx, filename in enumerate(resource_files):
                full_path = os.path.join(self.resource_dir, filename)
                res_name = Path(filename).stem
                self.log_signal.emit(f"Parsing resource file: {filename}")
                
                try:
                    caps = parse_capabilities_robust(full_path)
                    if caps:
                        key_name = f"resource: {res_name}" 
                        all_capabilities[key_name] = caps
                except Exception as parse_err:
                    self.log_signal.emit(f"Warning: Failed to parse {filename}: {parse_err}")

                progress = 10 + int((idx + 1) / total_files * 20)
                self.progress_signal.emit(progress, 100)

            self.log_signal.emit(f"Loaded {len(all_capabilities)} valid resources.")
            if not all_capabilities: raise ValueError("No valid resources loaded.")

            # 2. SMT Logic Configuration
            find_all = (self.mode_index >= 1) # Pro or Ultra
            is_ultra = (self.mode_index == 2)
            
            mode_names = ['Fast', 'Pro', 'Ultra']
            self.log_signal.emit(f"Starting SMT Logic (Mode: {mode_names[self.mode_index]})...")
            
            # SMT run
            # Note: run_optimization returns (gui_results, json_solutions)
            # We force generate_json=True internally so we always have data for export, 
            # even in Fast/Pro mode if user wants to export.
            # Wait, user requirement: "Fast" finds 1 solution. 
            # Optimization logic in main: if generate_json=True, it builds the struct.
            # Let's ALWAYS generate the json struct in memory so export works for any valid solution found.
            
            gui_results, json_solutions = run_optimization(
                recipe_data, 
                all_capabilities, 
                log_callback=self.log_signal.emit, 
                generate_json=True, # Always generate structure for export capability
                find_all_solutions=find_all
            )
            
            self.progress_signal.emit(60, 100)

            # 3. Ultra Optimization Logic
            if is_ultra and json_solutions:
                self.log_signal.emit("Ultra Mode: Calculating costs and finding optimal solution...")
                
                optimizer = SolutionOptimizer()
                optimizer.set_weights(*self.weights)
                optimizer.load_resource_costs_from_dir(self.resource_dir)
                
                evaluated_solutions = optimizer.optimize_solutions_from_memory(json_solutions)
                
                sorted_gui_results = []
                
                for eval_sol in evaluated_solutions:
                    sol_id = eval_sol['solution_id']
                    rows = [r for r in gui_results if r.get('solution_id') == sol_id]
                    if sorted_gui_results: sorted_gui_results.append({})
                    
                    for row in rows:
                        row['composite_score'] = eval_sol['composite_score']
                        row['energy_cost'] = eval_sol['total_energy_cost']
                        row['use_cost'] = eval_sol['total_use_cost']
                        row['co2_footprint'] = eval_sol['total_co2_footprint']
                        sorted_gui_results.append(row)
                
                gui_results = sorted_gui_results
                if evaluated_solutions:
                    self.log_signal.emit(f"Optimization complete. Best Solution ID: {evaluated_solutions[0]['solution_id']}")

            self.progress_signal.emit(100, 100)
            
            # [NEW] Pack context for export
            # We need: Resources (all_capabilities), Solutions (json_solutions), General Recipe (recipe_data)
            context_data = {
                'resources': all_capabilities,
                'solutions': json_solutions,
                'recipe': recipe_data
            }
            
            self.finished_signal.emit(gui_results, context_data)

        except Exception as e:
            self.error_signal.emit(str(e))
            self.log_signal.emit(traceback.format_exc())