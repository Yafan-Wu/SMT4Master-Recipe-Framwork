import json
import uuid
from datetime import datetime
import os
import xml.etree.ElementTree as ET
from xml.dom import minidom

# Namespace constants
B2MML_NS = "http://www.mesa.org/xml/B2MML"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
SCHEMA_LOCATION = "http://www.mesa.org/xml/B2MML Schema/AllSchemas.xsd"


def generate_b2mml_master_recipe(
    resources_data,
    solutions_data_list,
    general_recipe_data,
    selected_solution_id,
    output_path=None,
):
    """
    Generate a B2MML Master Recipe XML from in-memory data.

    Args:
        resources_data: Resource capability data parsed from AAS/XML.
        solutions_data_list: Optimization solutions (dict with 'solutions' or a list).
        general_recipe_data: General recipe data.
        selected_solution_id: The chosen optimal solution ID.
        output_path: Optional output file path. If None, returns the XML string.

    Returns:
        If output_path is None: Returns XML string.
        If output_path is provided: Writes XML to file and returns the file path (or XML string on write failure).
    """

    # --- Find the selected solution ---
    optimal_solution = None
    solutions_data = solutions_data_list

    if isinstance(solutions_data, dict) and "solutions" in solutions_data:
        solutions_list = solutions_data["solutions"]
    elif isinstance(solutions_data, list):
        solutions_list = solutions_data
    else:
        raise ValueError(f"Unsupported solutions data format: {type(solutions_data)}")

    for solution in solutions_list:
        if solution.get("solution_id") == selected_solution_id:
            optimal_solution = solution
            break

    if not optimal_solution:
        raise ValueError(f"Optimal solution {selected_solution_id} not found in solutions data")

    # --- Register namespaces to force prefix "b2mml" and keep "xsi" ---
    # IMPORTANT: Do this BEFORE creating any elements.
    ET.register_namespace("b2mml", B2MML_NS)
    ET.register_namespace("xsi", XSI_NS)

    # --- Element creation helper (B2MML namespace) ---
    def create_element(parent, tag, **kwargs):
        """Create a B2MML namespaced element."""
        return ET.SubElement(parent, f"{{{B2MML_NS}}}{tag}", **kwargs)

    # --- Create root (B2MML namespace) ---
    root = ET.Element(ET.QName(B2MML_NS, "BatchInformation"))
    # schemaLocation is an xsi attribute
    root.set(ET.QName(XSI_NS, "schemaLocation"), SCHEMA_LOCATION)

    # ListHeader
    list_header = create_element(root, "ListHeader")
    create_element(list_header, "ID").text = "ListHeadID"
    create_element(list_header, "CreateDate").text = datetime.now().isoformat() + "+01:00"

    # Description
    desc = create_element(root, "Description")
    desc.text = (
        "This Batch Information includes the Master Recipe based on General Recipe "
        f"{general_recipe_data.get('ID', 'Unknown')} and Optimal Solution {selected_solution_id}"
    )

    # MasterRecipe
    master_recipe = create_element(root, "MasterRecipe")
    create_element(master_recipe, "ID").text = f"MasterRecipe_{selected_solution_id}"
    create_element(master_recipe, "Version").text = "1.0.0"
    create_element(master_recipe, "VersionDate").text = datetime.now().isoformat() + "+01:00"

    recipe_desc = create_element(master_recipe, "Description")
    recipe_desc.text = (
        "Master recipe based on General Recipe "
        f"{general_recipe_data.get('ID', 'Unknown')} and optimized solution {selected_solution_id} "
        "using resources from optimization"
    )

    # Header
    header = create_element(master_recipe, "Header")
    create_element(header, "ProductID").text = "StirredHeatedWater"
    create_element(header, "ProductName").text = "Stirred and Heated Water"

    # EquipmentRequirement
    equipment_req = create_element(master_recipe, "EquipmentRequirement")
    create_element(equipment_req, "ID").text = "Equipment Requirement for the HCs"

    constraint = create_element(equipment_req, "Constraint")
    create_element(constraint, "ID").text = "Material constraint"
    create_element(constraint, "Condition").text = "Material == H2O"

    create_element(equipment_req, "Description").text = "Only water is allowed for the stirring and heating process"

    # Formula - Collect all parameters
    formula = create_element(master_recipe, "Formula")

    # Helper: Find propertyRealizedBy from resource data
    def find_property_realized_by(resource_name, capability_name, property_name):
        if resource_name not in resources_data:
            return None

        resource_caps = resources_data[resource_name]
        if isinstance(resource_caps, list):
            for capability_data in resource_caps:
                # Check capability name
                cap_match = False
                if "capability" in capability_data:
                    for cap in capability_data["capability"]:
                        if cap.get("capability_name") == capability_name:
                            cap_match = True
                            break

                if not cap_match:
                    continue

                # Search in properties
                for prop in capability_data.get("properties", []):
                    if prop.get("property_name") == property_name:
                        return prop.get("propertyRealizedBy")

                # Fallback: case-insensitive by property_name
                for prop in capability_data.get("properties", []):
                    if prop.get("property_name", "").lower() == property_name.lower():
                        return prop.get("propertyRealizedBy")

        return None

    # Map data types
    def map_data_type(json_type):
        mapping = {
            "xs:int": "integer",
            "xs:double": "double",
            "int": "integer",
            "double": "double",
            "duration": "duration",
        }
        return mapping.get(json_type, json_type)

    # Map units
    def map_unit(unit_uri):
        mapping = {
            "http://si-digital-framework.org/SI/units/second": "Sekunde",
            "http://si-digital-framework.org/SI/units/litre": "Liter",
            "http://si-digital-framework.org/SI/units/degreeCelsius": "Grad Celsius",
            "http://qudt.org/vocab/unit/REV-PER-MIN": "Umdrehungen pro Minute",
            "http://qudt.org/vocab/unit/PERCENT": "Prozent",
            "http://qudt.org/vocab/unit/CYC-PER-SEC": "CYC-PER-SEC",
        }
        if unit_uri in mapping:
            return mapping[unit_uri]
        return unit_uri.split("/")[-1] if "/" in unit_uri else unit_uri

    # Store parameter mapping - global parameter counter
    param_mapping = {}
    global_param_counter = 1

    # Validate general recipe structure
    if "ProcessElements" not in general_recipe_data:
        raise ValueError("General recipe data must contain 'ProcessElements'")

    # Process all parameters first, assign unique ID for each parameter
    for pe in general_recipe_data["ProcessElements"]:
        # Find corresponding assignment in the selected solution
        assignment = None
        for a in optimal_solution.get("assignments", []):
            if a.get("step_id") == pe.get("ID"):
                assignment = a
                break

        if not assignment:
            print(f"Warning: No assignment found for process element {pe.get('ID')}")
            continue

        if "Parameters" not in pe:
            continue

        for param in pe["Parameters"]:
            param_id = None

            # Special handling for Dosing
            if pe.get("ID") == "Dosing001" and param.get("ID") == "Dosing_Amount001":
                property_realized_by = find_property_realized_by(
                    assignment.get("resource", ""),
                    "Dosing",
                    "Litre",
                )
                param_id = property_realized_by
            else:
                # Find matching property in capability_details
                for capability_detail in assignment.get("capability_details", []):
                    for matched_prop in capability_detail.get("matched_properties", []):
                        if (
                            matched_prop.get("property_id") == param.get("Key")
                            and matched_prop.get("property_unit") == param.get("UnitOfMeasure")
                        ):
                            property_realized_by = find_property_realized_by(
                                assignment.get("resource", ""),
                                capability_detail.get("capability_name", ""),
                                matched_prop.get("property_name", ""),
                            )
                            param_id = property_realized_by
                            break
                    if param_id:
                        break

            # If propertyRealizedBy not found, skip this parameter
            if not param_id:
                print(f"Warning: No propertyRealizedBy found for parameter {param.get('ID')}, skipping...")
                continue

            formatted_param_id = f"{global_param_counter:03d}:{param_id}"
            param_mapping[param["ID"]] = formatted_param_id

            # Create Parameter element
            param_elem = create_element(formula, "Parameter")
            create_element(param_elem, "ID").text = formatted_param_id

            resource_short = assignment.get("resource", "").replace("resource: ", "").replace("2025-04_", "")
            param_desc = f"{resource_short}_{param.get('Description', '').replace(' ', '_')}"
            create_element(param_elem, "Description").text = param_desc

            create_element(param_elem, "ParameterType").text = "ProcessParameter"
            create_element(param_elem, "ParameterSubType").text = "ST"

            value_elem = create_element(param_elem, "Value")
            value_str = param.get("ValueString", "")
            if value_str.startswith(">=") or value_str.startswith("<="):
                value_str = value_str[2:]

            create_element(value_elem, "ValueString").text = value_str
            create_element(value_elem, "DataInterpretation").text = "Constant"
            create_element(value_elem, "DataType").text = map_data_type(param.get("DataType", ""))
            create_element(value_elem, "UnitOfMeasure").text = map_unit(param.get("UnitOfMeasure", ""))

            global_param_counter += 1

    # ProcedureLogic
    procedure_logic = create_element(master_recipe, "ProcedureLogic")

    # Create step list
    steps = []

    # 1) Start step
    steps.append({"id": "S1", "recipe_element_id": "Init", "description": "Init"})

    # 2) Operation steps in ProcessElements order
    step_counter = 2
    recipe_element_counter = 1

    for pe in general_recipe_data["ProcessElements"]:
        step_id = f"S{step_counter}"

        assignment = None
        for a in optimal_solution.get("assignments", []):
            if a.get("step_id") == pe.get("ID"):
                assignment = a
                break

        if not assignment:
            print(f"Warning: No assignment found for process element {pe.get('ID')}")
            continue

        resource_short = assignment.get("resource", "").replace("resource: ", "").replace("2025-04_", "")

        # Capability name (from assignment)
        capability_name = "Unknown"
        for cap_detail in assignment.get("capability_details", []) or []:
            if cap_detail.get("capability_name"):
                capability_name = cap_detail["capability_name"]
                break

        # Find realized_by from resource data
        recipe_element_id = None
        resource_key = assignment.get("resource", "")
        if resource_key in resources_data:
            resource_caps = resources_data[resource_key]
            if isinstance(resource_caps, list):
                for capability_data in resource_caps:
                    capabilities_matched = False
                    for cap in capability_data.get("capability", []) or []:
                        if cap.get("capability_name") in assignment.get("capabilities", []):
                            capabilities_matched = True
                            break

                    if capabilities_matched and capability_data.get("realized_by"):
                        realized_by_list = capability_data["realized_by"]
                        if realized_by_list:
                            recipe_element_id = f"{recipe_element_counter:03d}:{realized_by_list[0]}"
                            break

        # If not found, fallback to UUID
        if not recipe_element_id:
            recipe_element_id = f"{recipe_element_counter:03d}:{str(uuid.uuid4())}"

        step_description = f"{recipe_element_counter:03d}:{resource_short}_{pe.get('Description', '')}:{capability_name}"

        steps.append(
            {
                "id": step_id,
                "recipe_element_id": recipe_element_id,
                "description": step_description,
                "process_element": pe,
                "assignment": assignment,
                "recipe_element_number": recipe_element_counter,
                "capability_name": capability_name,
            }
        )

        # Store for later RecipeElement creation
        pe["recipe_element_id"] = recipe_element_id
        pe["recipe_element_number"] = recipe_element_counter
        pe["capability_name"] = capability_name

        step_counter += 1
        recipe_element_counter += 1

    # 3) End step
    steps.append({"id": f"S{step_counter}", "recipe_element_id": "End", "description": "End"})

    # Create links (Step -> Transition -> Step) sequentially
    link_counter = 1
    for i in range(len(steps) - 1):
        # Step i -> Transition i+1
        link = create_element(procedure_logic, "Link")
        create_element(link, "ID").text = f"L{link_counter}"

        from_id = create_element(link, "FromID")
        create_element(from_id, "FromIDValue").text = steps[i]["id"]
        create_element(from_id, "FromType").text = "Step"
        create_element(from_id, "IDScope").text = "External"

        to_id = create_element(link, "ToID")
        create_element(to_id, "ToIDValue").text = f"T{i+1}"
        create_element(to_id, "ToType").text = "Transition"
        create_element(to_id, "IDScope").text = "External"

        create_element(link, "LinkType").text = "ControlLink"
        create_element(link, "Depiction").text = "LineAndArrow"
        create_element(link, "EvaluationOrder").text = "1"
        create_element(link, "Description").text = "string"

        link_counter += 1

        # Transition i+1 -> Step i+1
        link = create_element(procedure_logic, "Link")
        create_element(link, "ID").text = f"L{link_counter}"

        from_id = create_element(link, "FromID")
        create_element(from_id, "FromIDValue").text = f"T{i+1}"
        create_element(from_id, "FromType").text = "Transition"
        create_element(from_id, "IDScope").text = "External"

        to_id = create_element(link, "ToID")
        create_element(to_id, "ToIDValue").text = steps[i + 1]["id"]
        create_element(to_id, "ToType").text = "Step"
        create_element(to_id, "IDScope").text = "External"

        create_element(link, "LinkType").text = "ControlLink"
        create_element(link, "Depiction").text = "LineAndArrow"
        create_element(link, "EvaluationOrder").text = "1"
        create_element(link, "Description").text = "string"

        link_counter += 1

    # Create Step elements
    for step in steps:
        step_elem = create_element(procedure_logic, "Step")
        create_element(step_elem, "ID").text = step["id"]
        create_element(step_elem, "RecipeElementID").text = step["recipe_element_id"]
        create_element(step_elem, "RecipeElementVersion")
        create_element(step_elem, "Description").text = step["description"]

    # Create Transition elements
    for i in range(1, len(steps)):
        transition = create_element(procedure_logic, "Transition")
        create_element(transition, "ID").text = f"T{i}"

        if i == 1:
            create_element(transition, "Condition").text = "True"
        else:
            prev_step_desc = steps[i - 1]["description"]
            create_element(transition, "Condition").text = f"Step {prev_step_desc} is Completed"

    # RecipeElements: Begin and End
    for elem_type, elem_id in [("Begin", "Init"), ("End", "End")]:
        recipe_elem = create_element(master_recipe, "RecipeElement")
        create_element(recipe_elem, "ID").text = elem_id
        create_element(recipe_elem, "RecipeElementType").text = elem_type

    # RecipeElements for each ProcessElement (sorted by recipe_element_number)
    recipe_elements_sorted = sorted(
        [pe for pe in general_recipe_data["ProcessElements"] if "recipe_element_number" in pe],
        key=lambda x: x["recipe_element_number"],
    )

    for pe in recipe_elements_sorted:
        assignment = None
        for a in optimal_solution.get("assignments", []):
            if a.get("step_id") == pe.get("ID"):
                assignment = a
                break

        if not assignment:
            continue

        recipe_elem = create_element(master_recipe, "RecipeElement")
        create_element(recipe_elem, "ID").text = pe["recipe_element_id"]

        resource_short = assignment.get("resource", "").replace("resource: ", "").replace("2025-04_", "")
        capability_name = pe.get("capability_name", "Unknown")

        pe_name_map = {
            "Mixing_of_Liquids": "Mixing",
            "Dosing": "Dosing",
            "Heating_of_liquids": "Heating",
        }
        pe_short = pe_name_map.get(pe.get("Description", ""), pe.get("Description", ""))

        create_element(recipe_elem, "Description").text = f"{resource_short}_{pe_short}_Procedure:{capability_name}"
        create_element(recipe_elem, "RecipeElementType").text = "Operation"
        create_element(recipe_elem, "ActualEquipmentID").text = f"{resource_short}Instance"

        equipment_req_ref = create_element(recipe_elem, "EquipmentRequirement")
        create_element(equipment_req_ref, "ID").text = "Equipment Requirement for the HCs"

        # Parameter references (only those actually added)
        for param in pe.get("Parameters", []) or []:
            if param.get("ID") in param_mapping:
                param_ref = create_element(recipe_elem, "Parameter")
                create_element(param_ref, "ID").text = param_mapping[param["ID"]]
                create_element(param_ref, "ParameterType").text = "ProcessParameter"

    # --- Serialize XML (with declaration) ---
    # Use bytes output so xml_declaration is correct and stable.
    xml_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)

    # Pretty print
    try:
        dom = minidom.parseString(xml_bytes)
        pretty_xml = dom.toprettyxml(indent="\t", encoding="utf-8").decode("utf-8")
    except Exception as e:
        print(f"Warning: Could not pretty-print XML: {e}")
        pretty_xml = xml_bytes.decode("utf-8")

    # Save or return
    if output_path:
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(pretty_xml)
            print(f"Successfully saved Master Recipe to: {output_path}")
            return output_path
        except Exception as e:
            print(f"Error saving file: {e}")
            return pretty_xml

    return pretty_xml


def save_b2mml_xml(xml_content, filename="MasterRecipe_B2MML.xml"):
    """Save the B2MML XML to a file (legacy helper)."""
    with open(filename, "w", encoding="utf-8") as f:
        f.write(xml_content)
    print(f"B2MML Master Recipe saved to {filename}")
    return filename


def main():
    """Main function for standalone execution."""
    try:
        print("Loading data files...")

        required_files = [
            "parsed_resource_capabilities_output.json",
            "solutions.json",
            "optimization_report.json",
            "parsed_recipe_output.json",
        ]
        for fn in required_files:
            if not os.path.exists(fn):
                print(f"Error: {fn} not found")
                return

        with open("parsed_resource_capabilities_output.json", "r", encoding="utf-8") as f:
            resources = json.load(f)

        with open("solutions.json", "r", encoding="utf-8") as f:
            solutions = json.load(f)

        with open("optimization_report.json", "r", encoding="utf-8") as f:
            optimization = json.load(f)

        with open("parsed_recipe_output.json", "r", encoding="utf-8") as f:
            general_recipe = json.load(f)

        optimal_solution_id = optimization["optimal_solution"]["solution_id"]

        print("Generating B2MML Master Recipe...")

        solutions_data = {"solutions": solutions.get("solutions", [])}

        result = generate_b2mml_master_recipe(
            resources_data=resources,
            solutions_data_list=solutions_data,
            general_recipe_data=general_recipe,
            selected_solution_id=optimal_solution_id,
            output_path="MasterRecipe_B2MML.xml",
        )

        print("\nB2MML Master Recipe Generation Complete!")
        print(f"\nUsing Optimal Solution: {optimal_solution_id}")
        print(f"Composite Score: {optimization['optimal_solution']['composite_score']}")

        print("\nResource Usage:")
        for resource, count in optimization["optimal_solution"]["resource_usage"].items():
            resource_short = resource.replace("resource: ", "").replace("2025-04_", "")
            print(f"  {resource_short}: {count} step(s)")

        print(f"\nTotal Energy Cost: {optimization['optimal_solution']['total_energy_cost']}")
        print(f"Total Use Cost: {optimization['optimal_solution']['total_use_cost']}")
        print(f"Total CO2 Footprint: {optimization['optimal_solution']['total_co2_footprint']}")
        print(f"Material Flow Consistent: {optimization['optimal_solution']['material_flow_consistent']}")

        if isinstance(result, str) and result.endswith(".xml"):
            print(f"\nOutput file: {result}")

    except FileNotFoundError as e:
        print(f"Error: Required data file not found: {str(e)}")
        print("Please ensure all required JSON files are in the current directory:")
        for fn in [
            "parsed_resource_capabilities_output.json",
            "solutions.json",
            "optimization_report.json",
            "parsed_recipe_output.json",
        ]:
            print(f" - {fn}")
    except Exception as e:
        print(f"Error generating B2MML Master Recipe: {str(e)}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
