# Code/SMT4ModPlant/MasterRecipeGenerator.py
import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import datetime
import uuid
import os
import re

def generate_b2mml_master_recipe(resources_data, solutions_data_list, general_recipe_data, selected_solution_id, output_path):
    """
    Generate B2MML Master Recipe from memory data.
    """
    
    # 1. Find the specific solution object
    target_solution = None
    if isinstance(solutions_data_list, dict) and 'solutions' in solutions_data_list:
        search_list = solutions_data_list['solutions']
    else:
        search_list = solutions_data_list

    for sol in search_list:
        if sol['solution_id'] == selected_solution_id:
            target_solution = sol
            break
            
    if not target_solution:
        raise ValueError(f"Solution ID {selected_solution_id} not found in the provided data.")

    # 2. Clean Resource Keys
    clean_resources = {}
    for key, val in resources_data.items():
        clean_key = key.replace("resource: ", "").strip()
        clean_resources[clean_key] = val
        clean_resources[key] = val

    # --- Helper Functions ---
    def get_clean_resource_name(res_string):
        """Replicate original script's cleaning logic for IDs"""
        return res_string.replace('resource: ', '').replace('2025-04_', '')

    def find_property_realized_by(resource_name_in_sol, capability_name, property_name, property_id=None):
        clean_res_name = resource_name_in_sol.replace("resource: ", "").strip()
        if clean_res_name not in clean_resources:
            return None
        
        res_data_entry = clean_resources[clean_res_name]
        search_candidates = [res_data_entry] if isinstance(res_data_entry, dict) else res_data_entry

        for cap_data in search_candidates:
            # 1. Check Capability Name Match (Loose)
            if 'capability' in cap_data:
                pass 
            
            # 2. Search Properties (Name First, then ID)
            properties_list = cap_data.get('properties', [])
            if 'capability' in cap_data:
                for c in cap_data['capability']:
                    properties_list.extend(c.get('properties', []))

            for prop in properties_list:
                # A. Match by Name
                p_name = prop.get('property_name', '')
                if property_name and (p_name == property_name or p_name.lower() == property_name.lower()):
                    return prop.get('propertyRealizedBy')
                
                # B. Match by ID
                p_id = prop.get('property_ID', '')
                if property_id and p_id == property_id:
                    return prop.get('propertyRealizedBy')
        return None

    def map_data_type(json_type):
        mapping = {'xs:int': 'integer', 'xs:double': 'double', 'int': 'integer', 'double': 'double', 'duration': 'duration'}
        return mapping.get(json_type, json_type)

    def map_unit(unit_uri):
        mapping = {
            'http://si-digital-framework.org/SI/units/second': 'Sekunde',
            'http://si-digital-framework.org/SI/units/litre': 'Liter',
            'http://si-digital-framework.org/SI/units/degreeCelsius': 'Grad Celsius',
            'http://qudt.org/vocab/unit/REV-PER-MIN': 'Umdrehungen pro Minute',
            'http://qudt.org/vocab/unit/PERCENT': 'Prozent',
            'http://qudt.org/vocab/unit/CYC-PER-SEC': 'Zyklen pro Sekunde'
        }
        if unit_uri:
            return mapping.get(unit_uri, unit_uri.split('/')[-1] if '/' in unit_uri else unit_uri)
        return "Unknown"

    # --- XML Generation ---
    root = ET.Element('b2mml:BatchInformation', attrib={
        'xmlns:xsi': 'http://www.w3.org/2001/XMLSchema-instance',
        'xsi:schemaLocation': 'http://www.mesa.org/xml/B2MML Schema/AllSchemas.xsd',
        'xmlns:b2mml': 'http://www.mesa.org/xml/B2MML'
    })

    # 1. List Header
    list_header = ET.SubElement(root, 'b2mml:ListHeader')
    ET.SubElement(list_header, 'b2mml:ID').text = 'ListHeadID'
    ET.SubElement(list_header, 'b2mml:CreateDate').text = datetime.now().isoformat()

    # 2. Batch Description
    gen_recipe_id = general_recipe_data.get('ID', 'GeneralRecipe001')
    desc_elem = ET.SubElement(root, 'b2mml:Description')
    desc_elem.text = f"This Batch Information includes the Master Recipe based on General Recipe {gen_recipe_id} and Optimal Solution {selected_solution_id}"

    # 3. Master Recipe Block
    master_recipe = ET.SubElement(root, 'b2mml:MasterRecipe')
    ET.SubElement(master_recipe, 'b2mml:ID').text = f"MasterRecipe_{selected_solution_id}"
    ET.SubElement(master_recipe, 'b2mml:Version').text = '1.0.0'
    ET.SubElement(master_recipe, 'b2mml:VersionDate').text = datetime.now().isoformat()
    
    mr_desc = ET.SubElement(master_recipe, 'b2mml:Description')
    mr_desc.text = f"Master recipe based on General Recipe {gen_recipe_id} and optimized solution {selected_solution_id} using resources from optimization"

    # 4. [MODIFIED] Header (Product Info with Timestamp)
    header_elem = ET.SubElement(master_recipe, 'b2mml:Header')
    
    # Generate current time for dynamic ID/Name
    current_ts = datetime.now()
    # Format: Product_20260114_153045
    dynamic_product_id = f"Product_{current_ts.strftime('%Y%m%d_%H%M%S')}"
    # Format: Product_2026-01-14 15:30:45
    dynamic_product_name = f"Product_{current_ts.strftime('%Y-%m-%d %H:%M:%S')}"
    
    ET.SubElement(header_elem, 'b2mml:ProductID').text = dynamic_product_id
    ET.SubElement(header_elem, 'b2mml:ProductName').text = dynamic_product_name

    # 5. Equipment Requirement (Global Constraint)
    eq_req = ET.SubElement(master_recipe, 'b2mml:EquipmentRequirement')
    ET.SubElement(eq_req, 'b2mml:ID').text = 'Equipment Requirement for the HCs'
    constraint = ET.SubElement(eq_req, 'b2mml:Constraint')
    ET.SubElement(constraint, 'b2mml:ID').text = 'Material constraint'
    ET.SubElement(constraint, 'b2mml:Condition').text = 'Material == H2O'
    ET.SubElement(eq_req, 'b2mml:Description').text = 'Only water is allowed for the stirring and heating process'

    # 6. Formula
    formula = ET.SubElement(master_recipe, 'b2mml:Formula')
    
    param_mapping = {}
    global_param_counter = 1

    # --- Process Parameters ---
    for pe in general_recipe_data['ProcessElements']:
        assignment = None
        for a in target_solution['assignments']:
            if a['step_id'] == pe['ID']:
                assignment = a
                break
        if not assignment: continue

        if 'Parameters' in pe and pe['Parameters']:
            for param in pe['Parameters']:
                realized_by_id = None
                
                # Match logic
                if 'capability_details' in assignment:
                    for cap_det in assignment['capability_details']:
                        for match_prop in cap_det.get('matched_properties', []):
                            if match_prop.get('property_id') == param['Key']:
                                realized_by_id = find_property_realized_by(
                                    assignment['resource'], 
                                    cap_det['capability_name'], 
                                    match_prop.get('property_name'),
                                    match_prop.get('property_id')
                                )
                                break
                        if realized_by_id: break
                
                if not realized_by_id:
                    realized_by_id = 'null'

                fmt_id = f"{global_param_counter:03d}:{realized_by_id}"
                param_mapping[param['ID']] = fmt_id
                
                p_elem = ET.SubElement(formula, 'b2mml:Parameter')
                ET.SubElement(p_elem, 'b2mml:ID').text = fmt_id
                
                res_clean = get_clean_resource_name(assignment['resource'])
                p_desc_text = f"{res_clean}_{param['Description'].replace(' ', '_')}"
                ET.SubElement(p_elem, 'b2mml:Description').text = p_desc_text
                ET.SubElement(p_elem, 'b2mml:ParameterType').text = 'ProcessParameter'
                ET.SubElement(p_elem, 'b2mml:ParameterSubType').text = 'ST'
                
                val_elem = ET.SubElement(p_elem, 'b2mml:Value')
                val_str = param.get('ValueString', '')
                if val_str.startswith(('>=', '<=', '>', '<', '=')):
                    m = re.search(r'\d+(\.\d+)?', val_str)
                    if m: val_str = m.group(0)
                
                ET.SubElement(val_elem, 'b2mml:ValueString').text = val_str
                ET.SubElement(val_elem, 'b2mml:DataInterpretation').text = 'Constant'
                ET.SubElement(val_elem, 'b2mml:DataType').text = map_data_type(param.get('DataType', 'string'))
                ET.SubElement(val_elem, 'b2mml:UnitOfMeasure').text = map_unit(param.get('UnitOfMeasure', ''))
                
                global_param_counter += 1

    # --- Procedure Logic (Pre-calculation) ---
    steps_data = []
    # Start
    steps_data.append({'id': 'S1', 're_id': 'Init', 'desc': 'Init'})
    
    step_ctr = 2
    re_ctr = 1
    
    for pe in general_recipe_data['ProcessElements']:
        s_id = f"S{step_ctr}"
        assignment = next((a for a in target_solution['assignments'] if a['step_id'] == pe['ID']), None)
        if not assignment: continue
        
        res_clean = get_clean_resource_name(assignment['resource'])
        re_id = None
        cap_name = "Unknown"
        
        if 'capability_details' in assignment and assignment['capability_details']:
            cap_name = assignment['capability_details'][0]['capability_name']
        
        # Determine Step ID (Recipe Element ID)
        clean_res_key = assignment['resource'].replace('resource: ', '').strip()
        if clean_res_key in clean_resources:
            res_data_entry = clean_resources[clean_res_key]
            search_candidates = [res_data_entry] if isinstance(res_data_entry, dict) else res_data_entry
            
            for res_data in search_candidates:
                if 'realized_by' in res_data and res_data['realized_by']:
                     re_id = f"{re_ctr:03d}:{res_data['realized_by'][0]}"
                     break
                if 'capability' in res_data:
                    for c in res_data['capability']:
                        if c.get('capability_name') == cap_name and 'realized_by' in c and c['realized_by']:
                            re_id = f"{re_ctr:03d}:{c['realized_by'][0]}"
                            break
                    if re_id: break
        
        if not re_id:
             re_id = f"{re_ctr:03d}:{str(uuid.uuid4())}"
             
        desc = f"{re_ctr:03d}:{res_clean}_{pe['Description']}:{cap_name}"
        
        steps_data.append({
            'id': s_id, 
            're_id': re_id, 
            'desc': desc, 
            'pe': pe, 
            'ass': assignment
        })
        step_ctr += 1
        re_ctr += 1
        
    # End
    steps_data.append({'id': f"S{step_ctr}", 're_id': 'End', 'desc': 'End'})

    # --- Write Procedure Logic ---
    proc_logic = ET.SubElement(master_recipe, 'b2mml:ProcedureLogic')
    
    # 1. Write LINKS
    link_counter = 1
    for i in range(len(steps_data) - 1):
        t_id = f"T{i+1}"
        
        # Link Step -> Trans
        l1 = ET.SubElement(proc_logic, 'b2mml:Link')
        ET.SubElement(l1, 'b2mml:ID').text = f"L{link_counter}"
        fid = ET.SubElement(l1, 'b2mml:FromID')
        ET.SubElement(fid, 'b2mml:FromIDValue').text = steps_data[i]['id']
        ET.SubElement(fid, 'b2mml:FromType').text = 'Step'
        ET.SubElement(fid, 'b2mml:IDScope').text = 'External'
        tid = ET.SubElement(l1, 'b2mml:ToID')
        ET.SubElement(tid, 'b2mml:ToIDValue').text = t_id
        ET.SubElement(tid, 'b2mml:ToType').text = 'Transition'
        ET.SubElement(tid, 'b2mml:IDScope').text = 'External'
        
        ET.SubElement(l1, 'b2mml:LinkType').text = 'ControlLink'
        ET.SubElement(l1, 'b2mml:Depiction').text = 'LineAndArrow'
        ET.SubElement(l1, 'b2mml:EvaluationOrder').text = '1'
        ET.SubElement(l1, 'b2mml:Description').text = 'string'
        link_counter += 1
        
        # Link Trans -> Step
        l2 = ET.SubElement(proc_logic, 'b2mml:Link')
        ET.SubElement(l2, 'b2mml:ID').text = f"L{link_counter}"
        fid = ET.SubElement(l2, 'b2mml:FromID')
        ET.SubElement(fid, 'b2mml:FromIDValue').text = t_id
        ET.SubElement(fid, 'b2mml:FromType').text = 'Transition'
        ET.SubElement(fid, 'b2mml:IDScope').text = 'External'
        tid = ET.SubElement(l2, 'b2mml:ToID')
        ET.SubElement(tid, 'b2mml:ToIDValue').text = steps_data[i+1]['id']
        ET.SubElement(tid, 'b2mml:ToType').text = 'Step'
        ET.SubElement(tid, 'b2mml:IDScope').text = 'External'
        
        ET.SubElement(l2, 'b2mml:LinkType').text = 'ControlLink'
        ET.SubElement(l2, 'b2mml:Depiction').text = 'LineAndArrow'
        ET.SubElement(l2, 'b2mml:EvaluationOrder').text = '1'
        ET.SubElement(l2, 'b2mml:Description').text = 'string'
        link_counter += 1

    # 2. Write STEPS
    for s in steps_data:
        step_xml = ET.SubElement(proc_logic, 'b2mml:Step')
        ET.SubElement(step_xml, 'b2mml:ID').text = s['id']
        ET.SubElement(step_xml, 'b2mml:RecipeElementID').text = s['re_id']
        ET.SubElement(step_xml, 'b2mml:RecipeElementVersion')
        ET.SubElement(step_xml, 'b2mml:Description').text = s['desc']

    # 3. Write TRANSITIONS
    for i in range(len(steps_data) - 1):
        t_id = f"T{i+1}"
        trans = ET.SubElement(proc_logic, 'b2mml:Transition')
        ET.SubElement(trans, 'b2mml:ID').text = t_id
        cond = ET.SubElement(trans, 'b2mml:Condition')
        if i == 0: cond.text = "True"
        else: cond.text = f"Step {steps_data[i]['desc']} Completed"

    # --- Recipe Elements ---
    # Begin
    re_init = ET.SubElement(master_recipe, 'b2mml:RecipeElement')
    ET.SubElement(re_init, 'b2mml:ID').text = 'Init'
    ET.SubElement(re_init, 'b2mml:RecipeElementType').text = 'Begin'
    
    # End
    re_end = ET.SubElement(master_recipe, 'b2mml:RecipeElement')
    ET.SubElement(re_end, 'b2mml:ID').text = 'End'
    ET.SubElement(re_end, 'b2mml:RecipeElementType').text = 'End'

    # Details
    for s in steps_data:
        if 'pe' not in s: continue 
        
        re_elem = ET.SubElement(master_recipe, 'b2mml:RecipeElement')
        ET.SubElement(re_elem, 'b2mml:ID').text = s['re_id']
        
        pe_name_map = {'Mixing_of_Liquids': 'Mixing', 'Dosing': 'Dosing', 'Heating_of_liquids': 'Heating'}
        pe_short = pe_name_map.get(s['pe']['Description'], s['pe']['Description'])
        cap_clean = s['desc'].split(':')[-1]
        res_clean = get_clean_resource_name(s['ass']['resource'])
        
        ET.SubElement(re_elem, 'b2mml:Description').text = f"{res_clean}_{pe_short}_Procedure"
        ET.SubElement(re_elem, 'b2mml:RecipeElementType').text = 'Operation'
        
        ET.SubElement(re_elem, 'b2mml:ActualEquipmentID').text = f"{res_clean}Instance"
        
        eq_ref = ET.SubElement(re_elem, 'b2mml:EquipmentRequirement')
        ET.SubElement(eq_ref, 'b2mml:ID').text = 'Equipment Requirement for the HCs'
        
        for param in s['pe']['Parameters']:
            if param['ID'] in param_mapping:
                p_ref = ET.SubElement(re_elem, 'b2mml:Parameter')
                ET.SubElement(p_ref, 'b2mml:ID').text = param_mapping[param['ID']]
                ET.SubElement(p_ref, 'b2mml:ParameterType').text = 'ProcessParameter'

    # Output
    xml_str = ET.tostring(root, encoding='unicode')
    dom = minidom.parseString(xml_str)
    pretty_xml = dom.toprettyxml(indent='\t')
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(pretty_xml)
    
    return True