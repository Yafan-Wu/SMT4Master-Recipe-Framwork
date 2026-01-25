import xml.etree.ElementTree as ET
import json
import zipfile
import os
from pathlib import Path

def parse_capabilities_robust(file_path):
    """
    Parses an AAS file (XML or AASX format) and extracts capabilities.
    """
    
    tree = None
    file_path_str = str(file_path)
    
    # -------------------------------------------------------
    # Handle .aasx (ZIP archive) and standard .xml
    # -------------------------------------------------------
    if file_path_str.lower().endswith('.aasx'):
        try:
            with zipfile.ZipFile(file_path, 'r') as z:
                # Find the main XML file inside the archive
                xml_files = [
                    f for f in z.namelist() 
                    if f.endswith('.xml') 
                    and not f.startswith('_rels') 
                    and '[Content_Types]' not in f
                ]
                
                if not xml_files:
                    print(f"Warning: No valid XML found in AASX package: {file_path}")
                    return []
                
                # Use the first found XML file
                target_xml = xml_files[0]
                
                # Read and parse directly from the zip stream
                with z.open(target_xml) as f:
                    tree = ET.parse(f)
        except zipfile.BadZipFile:
            print(f"Error: File is corrupted or not a valid AASX package: {file_path}")
            return []
        except Exception as e:
            print(f"Error processing AASX file {file_path}: {e}")
            return []
    else:
        # Standard XML file parsing
        try:
            tree = ET.parse(file_path)
        except ET.ParseError as e:
            print(f"Error parsing XML file {file_path}: {e}")
            return []
        except Exception as e:
            print(f"Error reading file {file_path}: {e}")
            return []

    # -------------------------------------------------------
    # Core Parsing Logic
    # -------------------------------------------------------
    root = tree.getroot()
    ns = {'aas': 'https://admin-shell.io/aas/3/0'}

    capabilities = []

    # Iterate through all Submodels
    for capability_SM in root.findall(".//aas:submodel", ns):
        capability_SM_value = capability_SM.find(".//aas:value", ns)
        
        if capability_SM_value is not None and "https://admin-shell.io/idta/CapabilityDescription/1/0/Submodel" in capability_SM_value.text:
            
            for capability_sets in capability_SM.findall("aas:submodelElements/aas:submodelElementCollection", ns):
                for capability_container in capability_sets.findall("aas:value/aas:submodelElementCollection", ns):
                    for capability_element in capability_container.findall("aas:value/aas:capability", ns):
                        if capability_element is not None:
                            capability_element_name = capability_element.find("aas:idShort", ns)
                            capability_element_reference = capability_element.find("aas:supplementalSemanticIds//aas:value", ns)
                            capability_comment = capability_container.find("aas:value/aas:multiLanguageProperty/aas:value//aas:text", ns)
                            
                            capability = {
                                'capability': [],
                                'properties': [],
                                'generalized_by': [],
                                'realized_by': []
                            }

                            capability['capability'].append({
                                'capability_name': capability_element_name.text if capability_element_name is not None else "Unknown",
                                'capability_comment': capability_comment.text if capability_comment is not None else "",
                                'capability_ID': capability_element_reference.text if capability_element_reference is not None else ""
                            })

                            # Process Properties
                            for property_sets in capability_container.findall(".//aas:submodelElementCollection", ns):
                                property_sets_value = property_sets.find(".//aas:value", ns)
                                if property_sets_value is not None and "https://admin-shell.io/idta/CapabilityDescription/PropertySet/1/0" in property_sets_value.text:
                                    for property_container in property_sets.findall(".//aas:submodelElementCollection", ns):

                                        # Range Properties
                                        property_type_range = property_container.find("aas:value/aas:range", ns)
                                        if property_type_range is not None:
                                            # ... (Extraction logic identical to previous versions) ...
                                            prop_name = property_type_range.find("aas:idShort", ns)
                                            prop_id = property_type_range.find("aas:supplementalSemanticIds//aas:value", ns)
                                            unit = property_type_range.find("aas:embeddedDataSpecifications//aas:value", ns)
                                            vtype = property_type_range.find("aas:valueType", ns)
                                            min_val = property_type_range.find("aas:min", ns)
                                            max_val = property_type_range.find("aas:max", ns)
                                            prop_comment = property_container.find("aas:value/aas:multiLanguageProperty/aas:value//aas:text", ns)
                                            prop_relBy = property_container.find("aas:value/aas:relationshipElement/aas:second//aas:value", ns)

                                            prop_entry = {
                                                'property_name': prop_name.text if prop_name is not None else "",
                                                'property_comment': prop_comment.text if prop_comment is not None else "",
                                                'property_ID': prop_id.text if prop_id is not None else "",
                                                'property_unit': unit.text if unit is not None else "",
                                                'valueType': vtype.text if vtype is not None else "",
                                                'valueMin': min_val.text if min_val is not None else "",
                                                'valueMax': max_val.text if max_val is not None else "",
                                                'propertyRealizedBy': prop_relBy.text if prop_relBy is not None else "",
                                                'property_constraint': []
                                            }
                                            
                                            # Constraints Logic
                                            for capability_relations in capability_container.findall(".//aas:submodelElementCollection", ns):
                                                capability_relations_semantic_id = capability_relations.find("aas:semanticId//aas:value", ns)
                                                if capability_relations_semantic_id is not None and "https://admin-shell.io/idta/CapabilityDescription/CapabilityRelations/1/0" in capability_relations_semantic_id.text:
                                                    for constraint_sets in capability_relations.findall("aas:value/aas:submodelElementCollection", ns):
                                                        constraint_set_semantic_id = constraint_sets.find("aas:semanticId//aas:value", ns)
                                                        if constraint_set_semantic_id is not None and "https://admin-shell.io/idta/CapabilityDescription/ConstraintSet/1/0" in constraint_set_semantic_id.text:
                                                            for constraint_set in constraint_sets.findall("aas:value/aas:submodelElementCollection", ns):
                                                                constraint_set_semantic_id = constraint_set.find("aas:semanticId//aas:value", ns)
                                                                if constraint_set_semantic_id is not None and "https://admin-shell.io/idta/CapabilityDescription/PropertyConstraintContainer/1/0" in constraint_set_semantic_id.text:
                                                                    for relationship_constraint in constraint_set.findall("aas:value/aas:submodelElementCollection/aas:value/aas:relationshipElement", ns):
                                                                        second_keys = relationship_constraint.find("aas:second/aas:keys", ns)
                                                                        if second_keys is not None:
                                                                            key_elements = second_keys.findall("aas:key", ns)
                                                                            if key_elements:
                                                                                last_key = key_elements[-1]
                                                                                last_value = last_key.find("aas:value", ns)
                                                                                if last_value is not None and prop_name is not None and last_value.text == prop_name.text:
                                                                                    # Parse constraint details
                                                                                    constraint_type = None
                                                                                    conditional_type = None
                                                                                    property_constraint_ID = None
                                                                                    property_constraint_unit = None
                                                                                    property_constraint_value = None

                                                                                    for property_elements in constraint_set.findall("aas:value/aas:property", ns):
                                                                                        property_element_semantic_id = property_elements.find("aas:semanticId//aas:value", ns)
                                                                                        if property_element_semantic_id is not None:
                                                                                            sid_text = property_element_semantic_id.text
                                                                                            if "ConstraintType/1/0" in sid_text:
                                                                                                val = property_elements.find("aas:value", ns)
                                                                                                constraint_type = val.text if val is not None else ""
                                                                                            elif "PropertyConditionalType/1/0" in sid_text:
                                                                                                val = property_elements.find("aas:value", ns)
                                                                                                conditional_type = val.text if val is not None else ""
                                                                                            elif "BasicConstraint/1/0" in sid_text:
                                                                                                cid = property_elements.find("aas:supplementalSemanticIds//aas:value", ns)
                                                                                                u = property_elements.find("aas:embeddedDataSpecifications//aas:value", ns)
                                                                                                q = property_elements.find("aas:qualifiers//aas:value", ns)
                                                                                                cv = property_elements.find("aas:value", ns)
                                                                                                property_constraint_ID = cid.text if cid is not None else ""
                                                                                                property_constraint_unit = u.text if u is not None else ""
                                                                                                raw_val = cv.text if cv is not None else ""
                                                                                                q_val = q.text if q is not None else ""
                                                                                                if q_val == "GREATER_THAN_0": property_constraint_value = ">" + raw_val
                                                                                                elif q_val == "GREATER_EQUAL_1": property_constraint_value = ">=" + raw_val
                                                                                                elif q_val == "EQUAL_2": property_constraint_value = "==" + raw_val
                                                                                                elif q_val == "NOT_EQUAL_3": property_constraint_value = "!=" + raw_val
                                                                                                elif q_val == "LESS_EQUAL_4": property_constraint_value = "<=" + raw_val
                                                                                                elif q_val == "LESS_THAN_5": property_constraint_value = "<" + raw_val
                                                                                                else: property_constraint_value = raw_val

                                                                                    constraint = {
                                                                                        'conditional_type': conditional_type if conditional_type else "",
                                                                                        'constraint_type': constraint_type if constraint_type else "",
                                                                                        'property_constraint_ID': property_constraint_ID if property_constraint_ID else "",
                                                                                        'property_constraint_unit': property_constraint_unit if property_constraint_unit else "",
                                                                                        'property_constraint_value': property_constraint_value if property_constraint_value else ""
                                                                                    }
                                                                                    if any(v != "" for v in constraint.values()):
                                                                                        prop_entry['property_constraint'].append(constraint)
                                            capability['properties'].append(prop_entry)

                                        # SubmodelElementList Properties
                                        property_type_submodelElementList = property_container.find("aas:value/aas:submodelElementList", ns)
                                        if property_type_submodelElementList is not None:
                                            prop_name = property_type_submodelElementList.find("aas:idShort", ns)
                                            prop_id = property_type_submodelElementList.find("aas:supplementalSemanticIds//aas:value", ns)
                                            unit = property_type_submodelElementList.find("aas:embeddedDataSpecifications//aas:value", ns)
                                            vtype = property_type_submodelElementList.find("aas:valueTypeListElement", ns)
                                            prop_comment = property_container.find("aas:value/aas:multiLanguageProperty/aas:value//aas:text", ns)
                                            prop_relBy = property_container.find("aas:value/aas:relationshipElement/aas:second//aas:value", ns)

                                            result = {
                                                'property_name': prop_name.text if prop_name is not None else "",
                                                'property_comment': prop_comment.text if prop_comment is not None else "",
                                                'property_ID': prop_id.text if prop_id is not None else "",
                                                'property_unit': unit.text if unit is not None else "",
                                                'valueType': vtype.text if vtype is not None else ""
                                            }
                                            value_list = property_type_submodelElementList.findall("aas:value/aas:property", ns)
                                            for i, val_elem in enumerate(value_list):
                                                val = val_elem.find("aas:value", ns)
                                                result[f"value{i}"] = val.text if val is not None else ""
                                            result['property_realized_by'] = prop_relBy.text if prop_relBy is not None else ""
                                            capability['properties'].append(result)

                            # Relations (GeneralizedBy / RealizedBy)
                            for capability_relations in capability_container.findall(".//aas:submodelElementCollection", ns):
                                capability_relations_semantic_id = capability_relations.find("aas:semanticId//aas:value", ns)
                                if capability_relations_semantic_id is not None and "https://admin-shell.io/idta/CapabilityDescription/CapabilityRelations/1/0" in capability_relations_semantic_id.text:
                                    for generalized_by_sets in capability_relations.findall("aas:value/aas:submodelElementCollection", ns):
                                        generalized_by_semantic_id = generalized_by_sets.find("aas:semanticId//aas:value", ns)
                                        if generalized_by_semantic_id is not None and "GeneralizedBySet/1/0" in generalized_by_semantic_id.text:
                                            for relationship_generalized_by in generalized_by_sets.findall("aas:value/aas:relationshipElement", ns):
                                                second_keys = relationship_generalized_by.find("aas:second/aas:keys", ns)
                                                if second_keys is not None:
                                                    key_elements = second_keys.findall("aas:key", ns)
                                                    if key_elements:
                                                        last_key = key_elements[-1]
                                                        last_value = last_key.find("aas:value", ns)
                                                        if last_value is not None:
                                                            capability['generalized_by'].append(last_value.text)
                                    for realized_by in capability_relations.findall("aas:value/aas:relationshipElement", ns):
                                        realized_by_semantic_id = realized_by.find("aas:semanticId//aas:value", ns)
                                        if realized_by_semantic_id is not None and "CapabilityRealizedBy/1/0" in realized_by_semantic_id.text:
                                            realized_by_value = realized_by.find("aas:second//aas:value", ns)
                                            if realized_by_value is not None:
                                                capability['realized_by'].append(realized_by_value.text)

                            capabilities.append(capability)

    return capabilities