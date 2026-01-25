# Code/Optimizer/Optimization.py
import json
import os
import xml.etree.ElementTree as ET
from typing import Dict, List, Any

class SolutionOptimizer:
    def __init__(self):
        # Default weights
        self.weights = {
            "EnergyCost": 0.4,
            "UseCost": 0.3,
            "CO2Footprint": 0.3
        }
        self.resource_costs = {}

    def set_weights(self, energy_weight, use_weight, co2_weight):
        """Set custom weights and normalize them"""
        total = energy_weight + use_weight + co2_weight
        if total == 0:
            total = 1
        self.weights = {
            "EnergyCost": energy_weight / total,
            "UseCost": use_weight / total,
            "CO2Footprint": co2_weight / total
        }

    def extract_resource_cost_data(self, xml_file_path: str) -> Dict[str, float]:
        """Extract resource cost data from AAS XML file"""
        try:
            tree = ET.parse(xml_file_path)
            root = tree.getroot()
            
            cost_data = {
                "EnergyCost": 0.0,
                "UseCost": 0.0,
                "CO2Footprint": 0.0
            }
            
            # Find OptimizationCost submodel (namespace agnostic search)
            for submodel in root.findall('.//{*}submodel'):
                id_short = submodel.find('{*}idShort')
                if id_short is not None and id_short.text == 'OptimizationCost':
                    for prop in submodel.findall('.//{*}property'):
                        prop_id = prop.find('{*}idShort')
                        value_elem = prop.find('{*}value')
                        
                        if prop_id is not None and value_elem is not None:
                            prop_name = prop_id.text
                            if prop_name in cost_data:
                                try:
                                    cost_data[prop_name] = float(value_elem.text)
                                except (ValueError, TypeError):
                                    cost_data[prop_name] = 0.0
            return cost_data
            
        except Exception as e:
            print(f"Error processing file {xml_file_path}: {e}")
            return None

    def load_resource_costs_from_dir(self, resource_dir: str):
        """Load cost data for all XML files in a directory"""
        if not os.path.exists(resource_dir):
            print(f"Directory not found: {resource_dir}")
            return

        for filename in os.listdir(resource_dir):
            if filename.lower().endswith('.xml'):
                file_path = os.path.join(resource_dir, filename)
                # Resource name is filename without extension (e.g. "2025-04_HC10")
                resource_name = os.path.splitext(filename)[0]
                
                cost_data = self.extract_resource_cost_data(file_path)
                if cost_data:
                    self.resource_costs[resource_name] = cost_data

    def calculate_solution_cost(self, solution: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate total cost for a single solution"""
        total_energy_cost = 0.0
        total_use_cost = 0.0
        total_co2_footprint = 0.0
        resource_usage = {}
        
        for assignment in solution['assignments']:
            # Handle "resource: NAME" format
            resource_str = assignment['resource']
            resource_name = resource_str.split(': ')[1] if ': ' in resource_str else resource_str
            
            if resource_name in self.resource_costs:
                cost_data = self.resource_costs[resource_name]
                total_energy_cost += cost_data['EnergyCost']
                total_use_cost += cost_data['UseCost']
                total_co2_footprint += cost_data['CO2Footprint']
                
                resource_usage[resource_name] = resource_usage.get(resource_name, 0) + 1
        
        composite_score = (
            total_energy_cost * self.weights["EnergyCost"] +
            total_use_cost * self.weights["UseCost"] +
            total_co2_footprint * self.weights["CO2Footprint"]
        )
        
        return {
            "solution_id": solution['solution_id'],
            "total_energy_cost": total_energy_cost,
            "total_use_cost": total_use_cost,
            "total_co2_footprint": total_co2_footprint,
            "composite_score": composite_score,
            "resource_usage": resource_usage,
            "weighted_breakdown": {
                "energy": total_energy_cost * self.weights["EnergyCost"],
                "use": total_use_cost * self.weights["UseCost"],
                "co2": total_co2_footprint * self.weights["CO2Footprint"]
            }
        }

    def optimize_solutions_from_memory(self, solutions_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Optimize solutions passed directly from memory (no file I/O).
        Returns a list of dicts with cost details, sorted by composite score (ascending).
        """
        evaluated_solutions = []
        
        for solution in solutions_data:
            cost_result = self.calculate_solution_cost(solution)
            evaluated_solutions.append(cost_result)
        
        # Sort by composite score (Lower is better/optimal)
        evaluated_solutions.sort(key=lambda x: x["composite_score"])
        
        return evaluated_solutions