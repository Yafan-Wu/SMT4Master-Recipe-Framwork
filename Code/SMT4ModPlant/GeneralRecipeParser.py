import xml.etree.ElementTree as ET
import json

def parse_general_recipe(file_path):
    tree = ET.parse(file_path)
    root = tree.getroot()

    ns = {'b2mml': 'http://www.mesa.org/xml/B2MML'}

    recipe_data = {
        'ID': root.find('b2mml:ID', ns).text,
        'Description': root.find('b2mml:Description', ns).text,
        'Inputs': [],
        'Outputs': [],
        'Intermediates': [],
        'ProcessElements': [],
        'DirectedLinks': []
    }

    # Process Inputs
    for material in root.findall('.//b2mml:ProcessInputs/b2mml:Material', ns):
        recipe_data['Inputs'].append({
            'ID': material.find('b2mml:ID', ns).text,
            'Description': material.find('b2mml:Description', ns).text,
            'Quantity': material.find('.//b2mml:QuantityString', ns).text,
            'DataType': material.find('.//b2mml:DataType', ns).text,
            'UnitOfMeasure': material.find('.//b2mml:UnitOfMeasure', ns).text,
            'Key': material.find('.//b2mml:Key', ns).text
        })

    # Process Outputs
    for material in root.findall('.//b2mml:ProcessOutputs/b2mml:Material', ns):
        recipe_data['Outputs'].append({
            'ID': material.find('b2mml:ID', ns).text,
            'Description': material.find('b2mml:Description', ns).text,
            'Quantity': material.find('.//b2mml:QuantityString', ns).text,
            'DataType': material.find('.//b2mml:DataType', ns).text,
            'UnitOfMeasure': material.find('.//b2mml:UnitOfMeasure', ns).text,
            'Key': material.find('.//b2mml:Key', ns).text
        })

    # Process Intermediates
    for material in root.findall('.//b2mml:ProcessIntermediates/b2mml:Material', ns):
        recipe_data['Intermediates'].append({
            'ID': material.find('b2mml:ID', ns).text,
            'Description': material.find('b2mml:Description', ns).text,
            'Quantity': material.find('.//b2mml:QuantityString', ns).text,
            'DataType': material.find('.//b2mml:DataType', ns).text,
            'UnitOfMeasure': material.find('.//b2mml:UnitOfMeasure', ns).text,
            'Key': material.find('.//b2mml:Key', ns).text
        })

    # Directed Links (Workflow)
    for link in root.findall('.//b2mml:DirectedLink', ns):
        recipe_data['DirectedLinks'].append({
            'ID': link.find('b2mml:ID', ns).text,
            'FromID': link.find('b2mml:FromID', ns).text,
            'ToID': link.find('b2mml:ToID', ns).text
        })

    # Process Elements (Steps)
    for process_element in root.findall('.//b2mml:ProcessElement', ns):
        pe_data = {
            'ID': process_element.find('b2mml:ID', ns).text,
            'Description': process_element.find('b2mml:Description', ns).text,
            'Parameters': [],
            'SemanticDescription': None
        }

        for param in process_element.findall('.//b2mml:ProcessElementParameter', ns):
            value = param.find('b2mml:Value', ns)
            pe_data['Parameters'].append({
                'ID': param.find('b2mml:ID', ns).text,
                'Description': param.find('b2mml:Description', ns).text,
                'ValueString': value.find('b2mml:ValueString', ns).text if value is not None else None,
                'DataType': value.find('b2mml:DataType', ns).text if value is not None else None,
                'UnitOfMeasure': value.find('b2mml:UnitOfMeasure', ns).text if value is not None else None,
                'Key': value.find('b2mml:Key', ns).text if value is not None else None
            })

        # Semantic Description
        semantic = process_element.find('.//b2mml:OtherInformation/b2mml:OtherValue/b2mml:ValueString', ns)
        if semantic is not None:
            pe_data['SemanticDescription'] = semantic.text

        recipe_data['ProcessElements'].append(pe_data)

    return recipe_data