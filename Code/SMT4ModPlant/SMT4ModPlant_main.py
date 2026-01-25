# Code/SMT4ModPlant/SMT4ModPlant_main.py
import json
from z3 import Solver, Bool, Not, Sum, If, is_true, sat, And

# Global constants
TRANSPORT_CAPABILITIES = ["Dosing", "Transfer", "Discharge"]

# ---------------------------------------------------------
# HELPER FUNCTIONS (Condensed for brevity, logic unchanged)
# ---------------------------------------------------------

def load_json(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        return json.load(f)

def capability_matching(recipe_sem_id, cap_entry):
    def tail(s):
        if s is None:
            return ""
        s = str(s).strip()
        # Support both "#" and "/" IRI styles (take the last fragment as the local name)
        if "#" in s:
            s = s.split("#")[-1]
        if "/" in s:
            s = s.split("/")[-1]
        return s.strip()

    recipe_tail = tail(recipe_sem_id)

    cap_id = cap_entry['capability'][0].get('capability_ID', '')
    cap_name = cap_entry['capability'][0].get('capability_name', '')

    # 1) Match by capability_ID (after extracting/normalizing the local name)
    if tail(cap_id) == recipe_tail and recipe_tail != "":
        return True

    # 2) Also allow matching by capability_name
    #    (In many AAS models, the semantic ID and the human-readable name may come from different vocabularies)
    if tail(cap_name) == recipe_tail and recipe_tail != "":
        return True

    # 3) generalized_by: normalize each entry as well and match against the recipe local name
    generalized = cap_entry.get('generalized_by', [])
    if isinstance(generalized, list):
        if any(tail(g) == recipe_tail for g in generalized if g is not None):
            return True

    return False

def property_value_match(param_value, prop):
    import re
    discrete_values = []
    for k, v in prop.items():
        if k.startswith('value') and k != 'valueType' and v is not None:
            try:
                discrete_values.append(float(v))
            except (ValueError, TypeError):
                continue

    value_min = prop.get('valueMin')
    value_max = prop.get('valueMax')

    if value_min is not None or value_max is not None:
        match = re.match(r'(>=|<=|>|<|=)?\s*([0-9\.,]+)', str(param_value))
        if match:
            op, val = match.groups()
            val = float(val.replace(',', '.'))
            op = op or '='
            if value_min is not None:
                try:
                    value_min_f = float(value_min)
                    if op in ('=', '>=') and val < value_min_f: return False
                    if op == '>' and val <= value_min_f: return False
                except ValueError: pass
            if value_max is not None:
                try:
                    value_max_f = float(value_max)
                    if op in ('=', '<=') and val > value_max_f: return False
                    if op == '<' and val >= value_max_f: return False
                except ValueError: pass
            return True

    if discrete_values:
        match = re.match(r'(>=|<=|>|<|=)?\s*([0-9\.,]+)', str(param_value))
        if match:
            op, val = match.groups()
            op = op or '='
            pval = float(val.replace(',', '.'))
            if op in ('=', None): return pval in discrete_values
            elif op == '>=': return any(dv >= pval for dv in discrete_values)
            elif op == '<=': return any(dv <= pval for dv in discrete_values)
            elif op == '>': return any(dv > pval for dv in discrete_values)
            elif op == '<': return any(dv < pval for dv in discrete_values)
        return False
    return True

def properties_compatible(recipe_step, cap_entry):
    if "Parameters" not in recipe_step or not recipe_step["Parameters"]:
        return True, []
    matched_props = []
    for param in recipe_step["Parameters"]:
        param_key = param.get("Key")
        param_unit = param.get("UnitOfMeasure")
        value_str = param.get("ValueString")
        match_found = False
        for prop in cap_entry.get("properties", []):
            if prop.get("property_ID") == param_key:
                if param_unit and prop.get("property_unit") and param_unit != prop.get("property_unit"):
                    continue
                if property_value_match(value_str, prop):
                    matched_props.append((param, prop))
                    match_found = True
                    break
        if not match_found:
            return False, []
    return True, matched_props

def check_preconditions_for_step(recipe, step, cap_entry):
    step_id = step['ID']
    links = recipe.get('DirectedLinks', [])
    input_material_ids = [link['FromID'] for link in links if link.get('ToID') == step_id]
    
    materials = recipe.get('Inputs', []) + recipe.get('Intermediates', [])
    input_materials = [mat for mat in materials if mat['ID'] in input_material_ids]
    
    for prop in cap_entry.get('properties', []):
        for constraint in prop.get('property_constraint', []):
            if constraint.get('conditional_type') == "Pre":
                constraint_id = constraint.get('property_constraint_ID')
                constraint_unit = constraint.get('property_constraint_unit')
                constraint_value_str = constraint.get('property_constraint_value')
                matched = False
                for mat in input_materials:
                    if mat.get('Key') == constraint_id and mat.get('UnitOfMeasure') == constraint_unit:
                        try:
                            import re
                            match = re.match(r'(>=|<=|>|<|=)?\s*([0-9\.,]+)', constraint_value_str)
                            if match:
                                op, val = match.groups()
                                op = op or '='
                                cval = float(val.replace(',', '.'))
                                mval = float(mat['Quantity'])
                                if ((op == '>=' and mval >= cval) or (op == '>' and mval > cval) or
                                    (op == '<=' and mval <= cval) or (op == '<' and mval < cval) or
                                    (op == '=' and mval == cval)):
                                    matched = True
                                    break
                        except Exception: continue
                if not matched: return False
    return True

def has_transfer_capability(res, capabilities_data):
    if res not in capabilities_data: return False
    for cap in capabilities_data[res]:
        if cap['capability'][0]['capability_name'] in TRANSPORT_CAPABILITIES: return True
    return False

def needs_transfer_to_step(step, current_res_idx, resources, step_by_id, step_resource_to_caps_props, recipe):
    step_id = step['ID']
    links = recipe.get('DirectedLinks', [])
    for link in links:
        if link.get('ToID') == step_id:
            from_id = link['FromID']
            for idx, candidate_step in enumerate(recipe['ProcessElements']):
                if candidate_step['ID'] == from_id:
                    for k, _ in enumerate(resources):
                        if k != current_res_idx:
                            entry = step_resource_to_caps_props[idx][k]
                            if entry and isinstance(entry, tuple) and len(entry) > 0:
                                return True
    return False

def is_materialflow_consistent(model, step_resource_to_caps_props, process_steps, resources, recipe, Assignment):
    material_location = {inp['ID']: None for inp in recipe.get('Inputs', [])}
    material_location.update({interm['ID']: None for interm in recipe.get('Intermediates', [])})
    material_location.update({out['ID']: None for out in recipe.get('Outputs', [])})
        
    step_by_id = {step['ID']: idx for idx, step in enumerate(process_steps)}
    resource_map = {}
    
    for i, step in enumerate(process_steps):
        for j, res in enumerate(resources):
            var = Assignment[i][j]
            if var is not None and is_true(model[var]):
                resource_map[step['ID']] = res
                
    for link in recipe.get('DirectedLinks', []):
        from_id = link['FromID']
        to_id = link['ToID']
        
        if from_id in step_by_id and to_id in material_location:
            if from_id not in resource_map: return False 
            res_of_step = resource_map[from_id]
            step_idx = step_by_id[from_id]
            res_idx = resources.index(res_of_step)
            caps, _ = step_resource_to_caps_props[step_idx][res_idx]
            is_transfer = any(c in TRANSPORT_CAPABILITIES for c in caps)
            if is_transfer: material_location[to_id] = None 
            else: material_location[to_id] = res_of_step
            continue
            
        if from_id in material_location and to_id in step_by_id:
            if to_id not in resource_map: return False
            assigned_res = resource_map[to_id]
            from_res = material_location[from_id]
            step_idx = step_by_id[to_id]
            res_idx = resources.index(assigned_res)
            caps, _ = step_resource_to_caps_props[step_idx][res_idx]
            is_transfer = any(c in TRANSPORT_CAPABILITIES for c in caps)
            if is_transfer:
                if from_res is None: pass
                elif from_res != assigned_res: return False
            else:
                if from_res is not None and from_res != assigned_res: return False
                material_location[from_id] = assigned_res
    return True

def solution_to_json(model, process_steps, resources, step_resource_to_caps_props, Assignment, recipe, capabilities, solution_id):
    """Convert the solution to JSON format"""
    solution_data = {
        "solution_id": solution_id,
        "assignments": [],
        "material_flow_consistent": True
    }
    
    for i, step in enumerate(process_steps):
        for j, res in enumerate(resources):
            var = Assignment[i][j]
            if var is not None and is_true(model[var]):
                caps, cap_prop_pairs = step_resource_to_caps_props[i][j]
                
                assignment_info = {
                    "step_id": step['ID'],
                    "step_description": step['Description'],
                    "resource": res,
                    "capabilities": caps,
                    "parameter_matches": []
                }
                
                if "Parameters" in step and step["Parameters"]:
                    for param in step["Parameters"]:
                        param_info = {
                            "description": param.get('Description'),
                            "key": param.get('Key'),
                            "unit": param.get('UnitOfMeasure'),
                            "value": param.get('ValueString')
                        }
                        assignment_info["parameter_matches"].append(param_info)
                
                capability_details = []
                for cap_name, matched_props in cap_prop_pairs:
                    cap_info = {"capability_name": cap_name, "matched_properties": []}
                    for param, prop in matched_props:
                        prop_info = {
                            "property_id": prop.get('property_ID'),
                            "property_name": prop.get('property_name'),
                            "property_unit": prop.get('property_unit'),
                        }
                        discrete_values = []
                        for key in prop.keys():
                            if key.startswith('value') and key not in ['valueType', 'valueMin', 'valueMax']:
                                val = prop.get(key)
                                if val is not None:
                                    try: discrete_values.append(float(val))
                                    except (ValueError, TypeError): discrete_values.append(val)
                        
                        value_min = prop.get('valueMin')
                        value_max = prop.get('valueMax')
                        
                        if discrete_values:
                            if len(discrete_values) == 1:
                                prop_info["value"] = discrete_values[0]
                                prop_info["value_type"] = "exact"
                            else:
                                prop_info["values"] = discrete_values
                                prop_info["value_type"] = "discrete_set"
                        elif value_min is not None or value_max is not None:
                            prop_info["value_min"] = value_min
                            prop_info["value_max"] = value_max
                            prop_info["value_type"] = "range"
                        else:
                            prop_info["value_type"] = "unspecified"
                        cap_info["matched_properties"].append(prop_info)
                    capability_details.append(cap_info)
                
                assignment_info["capability_details"] = capability_details
                solution_data["assignments"].append(assignment_info)
    return solution_data

def format_capability_string(cap_prop_pairs):
    display_parts = []
    for cap_name, matched_props in cap_prop_pairs:
        param_strs = []
        for param, prop in matched_props:
            req_val = param.get('ValueString', '?')
            param_desc = param.get('Description', 'Param').split(' ')[0] 
            res_val = "?"
            v_min = prop.get('valueMin')
            v_max = prop.get('valueMax')
            discrete_vals = []
            for k, v in prop.items():
                if k.startswith('value') and k not in ['valueType', 'valueMin', 'valueMax'] and v is not None:
                    discrete_vals.append(str(v))
            if v_min is not None or v_max is not None:
                res_val = f"[{v_min or '-inf'} - {v_max or 'inf'}]"
            elif discrete_vals:
                res_val = f"{{{','.join(discrete_vals)}}}"
            param_strs.append(f"{param_desc}: {req_val} -> {res_val}")
        if param_strs:
            display_parts.append(f"{cap_name} ({', '.join(param_strs)})")
        else:
            display_parts.append(cap_name)
    return "\n".join(display_parts)

# ---------------------------------------------------------
# EXPORTED FUNCTION
# ---------------------------------------------------------

def _sanitize_resource_name(res: str) -> str:
    """Make resource names safe for use in Z3 variable identifiers."""
    return res.replace(":", "").replace(" ", "_")


def _match_step_to_resource_caps(
    recipe_data,
    step,
    res,
    capabilities_data,
):
    """
    Collect matching capabilities and their matched properties for a given (step, resource).

    Returns:
        matching_caps: list[str]  - capability names that match this step
        matching_props: list[tuple[str, dict]] - (capability_name, matched_props_local)
    """
    sem_id = step.get("SemanticDescription", "")
    cap_list = capabilities_data[res]

    matching_caps = []
    matching_props = []

    for cap_entry in cap_list:
        # Semantic match (robust logic is implemented in capability_matching)
        if not capability_matching(sem_id, cap_entry):
            continue

        # Property/value/unit matching between recipe step and capability
        is_prop_match, matched_props_local = properties_compatible(step, cap_entry)
        if not is_prop_match:
            continue

        # Preconditions (e.g., required upstream results, constraints, etc.)
        if not check_preconditions_for_step(recipe_data, step, cap_entry):
            continue

        cap_name = cap_entry["capability"][0]["capability_name"]
        matching_caps.append(cap_name)
        matching_props.append((cap_name, matched_props_local))

    return matching_caps, matching_props


def _build_model_and_assignments(
    recipe_data,
    capabilities_data,
    process_steps,
    resources,
):
    """
    Build the SMT model skeleton:
      - Create assignment Bool variables assign_{stepID}_r{j}_{resource}
      - Pre-eliminate invalid (step, resource) pairs by forcing Not(var)
      - Store matching caps/props for later reporting + material-flow checking

    Returns:
        solver: z3.Solver
        Assignment: 2D list of Bool or None (None means impossible assignment)
        step_resource_to_caps_props: 2D list storing (matching_caps, matching_props)
    """
    solver = Solver()
    step_by_id = {step["ID"]: idx for idx, step in enumerate(process_steps)}

    step_resource_to_caps_props = [[[] for _ in resources] for _ in process_steps]
    Assignment = []

    for i, step in enumerate(process_steps):
        row = []

        for j, res in enumerate(resources):
            matching_caps, matching_props = _match_step_to_resource_caps(
                recipe_data=recipe_data,
                step=step,
                res=res,
                capabilities_data=capabilities_data,
            )

            # Create a stable and collision-resistant variable name.
            varname = f"assign_{step['ID']}_r{j}_{_sanitize_resource_name(res)}"
            var = Bool(varname)

            # Transfer feasibility is checked here as an early pruning rule:
            # If a step might require transport, resources without transport capability are invalid.
            transfer_needed = needs_transfer_to_step(
                step, j, resources, step_by_id, step_resource_to_caps_props, recipe_data
            )
            transfer_cap = has_transfer_capability(res, capabilities_data)

            valid = True
            if transfer_needed and not transfer_cap:
                valid = False
            if not matching_caps:
                # No compatible capability found on this resource for this step.
                valid = False

            if valid:
                step_resource_to_caps_props[i][j] = (matching_caps, matching_props)
                row.append(var)
            else:
                # Mark as impossible and add hard constraint to forbid it.
                row.append(None)
                solver.add(Not(var))

        Assignment.append(row)

    return solver, Assignment, step_resource_to_caps_props


def _add_exactly_one_resource_per_step_constraints(solver, Assignment):
    """
    Enforce that each process step is executed on exactly one resource.
    If a step has zero candidates, the model becomes UNSAT immediately.
    """
    for step_vars in Assignment:
        vars_for_step = [v for v in step_vars if v is not None]
        if vars_for_step:
            solver.add(Sum([If(v, 1, 0) for v in vars_for_step]) == 1)
        else:
            # No candidates => forced UNSAT.
            solver.add(False)


def _block_current_solution(solver, Assignment, model):
    """
    Block the current solution so the next SAT call finds a different assignment.
    We block the conjunction of all variables that were True in this solution.
    """
    true_vars = []
    for row in Assignment:
        for v in row:
            if v is not None and is_true(model[v]):
                true_vars.append(v)

    if true_vars:
        solver.add(Not(And(true_vars)))


def _append_solution_results_for_gui(
    all_results_for_gui,
    solution_id,
    process_steps,
    resources,
    Assignment,
    model,
    step_resource_to_caps_props,
):
    """
    Convert one model solution into GUI rows and append into all_results_for_gui.
    """
    if solution_id > 1:
        # Keep your original GUI separation behavior between solutions.
        all_results_for_gui.append({})

    for i, step in enumerate(process_steps):
        for j, res in enumerate(resources):
            var = Assignment[i][j]
            if var is not None and is_true(model[var]):
                _, cap_prop_pairs = step_resource_to_caps_props[i][j]
                formatted_cap_str = format_capability_string(cap_prop_pairs)

                all_results_for_gui.append({
                    "solution_id": solution_id,
                    "step_id": step["ID"],
                    "description": step["Description"],
                    "resource": res,
                    "capabilities": formatted_cap_str,
                    "status": "Matched"
                })


def run_optimization(recipe_data, capabilities_data, log_callback=print, generate_json=False, find_all_solutions=True):
    """
    Solve the recipe-to-resource assignment problem using SMT.

    Args:
        recipe_data: Parsed recipe structure (expects recipe_data['ProcessElements'])
        capabilities_data: Dict[resource_name -> list of capability entries]
        log_callback: Logger function (default: print)
        generate_json: If True, also build JSON solution objects
        find_all_solutions: If True, enumerate all solutions (with blocking clauses)

    Returns:
        (gui_results_list, all_solutions_json_list)
    """
    process_steps = recipe_data["ProcessElements"]
    resources = list(capabilities_data.keys())

    log_callback(f"Starting optimization (Find All: {find_all_solutions})...")

    # 1) Build model + assignment variables with early pruning rules.
    solver, Assignment, step_resource_to_caps_props = _build_model_and_assignments(
        recipe_data=recipe_data,
        capabilities_data=capabilities_data,
        process_steps=process_steps,
        resources=resources,
    )

    # 2) Add core "exactly one resource per step" constraints.
    _add_exactly_one_resource_per_step_constraints(solver, Assignment)

    log_callback("Solving constraints...")

    attempt_count = 0
    max_attempts = 2_000_000

    all_results_for_gui = []
    all_json_solutions = []
    valid_solution_count = 0

    # 3) Enumerate SAT models, filter by material-flow consistency, block each found model.
    while solver.check() == sat:
        model = solver.model()
        attempt_count += 1

        # Additional semantic/material-flow filter (outside SMT constraints).
        if is_materialflow_consistent(
            model, step_resource_to_caps_props, process_steps, resources, recipe_data, Assignment
        ):
            valid_solution_count += 1
            log_callback(f"Solution {valid_solution_count} Found (Attempt {attempt_count})!")

            if generate_json:
                solution_json = solution_to_json(
                    model, process_steps, resources, step_resource_to_caps_props,
                    Assignment, recipe_data, capabilities_data, valid_solution_count
                )
                all_json_solutions.append(solution_json)

            _append_solution_results_for_gui(
                all_results_for_gui=all_results_for_gui,
                solution_id=valid_solution_count,
                process_steps=process_steps,
                resources=resources,
                Assignment=Assignment,
                model=model,
                step_resource_to_caps_props=step_resource_to_caps_props,
            )

            if not find_all_solutions:
                break

        # Block current assignment and continue searching.
        _block_current_solution(solver, Assignment, model)

        if attempt_count >= max_attempts:
            break

    if valid_solution_count == 0:
        log_callback("UNSAT (No Solution Found).")
    else:
        log_callback(f"Search finished. Found {valid_solution_count} valid solution(s).")

    return all_results_for_gui, all_json_solutions