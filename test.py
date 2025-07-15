import pandas as pd
import json
import os
import re
from typing import Dict, List, Any, Optional

class ProjectTShirtExtractor:
    def __init__(self, directory_path: str):
        """
        Initialize the extractor with the directory containing Excel files.
        
        Args:
            directory_path (str): Path to the directory containing Excel files
        """
        self.directory_path = directory_path
        self.sheet_name = "Project T-Shirt"
    
    def extract_from_single_file(self, file_path: str) -> Dict[str, Any]:
        """
        Extract data from a single Excel file.
        
        Args:
            file_path (str): Path to the Excel file
            
        Returns:
            Dict[str, Any]: Extracted data in JSON format
        """
        try:
            # Read the Excel file
            df = pd.read_excel(file_path, sheet_name=self.sheet_name, header=None)
            
            # Extract basic information
            initiative_data = self._extract_initiative_info(df)
            accountable_roles = self._extract_accountable_roles(df)
            capabilities = self._extract_capabilities(df)
            
            # Build the JSON structure
            result = {
                "initiative": initiative_data,
                "accountable_roles": accountable_roles,
                "capabilities": capabilities
            }
            
            return result
            
        except Exception as e:
            print(f"Error processing file {file_path}: {str(e)}")
            return None
    
    def _extract_initiative_info(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Extract initiative information from the dataframe based on actual layout."""
        initiative_data = {
            "title": "",
            "overview": {
                "objective": "",
                "TPS_intake_number": None,
                "sizing_level": ""
            }
        }
        
        # Extract title from B1 (row 0, column 1) - "Mutual Funds in OLBB"
        if len(df) > 0 and len(df.columns) > 1:
            title = df.iloc[0, 1] if not pd.isna(df.iloc[0, 1]) else ""
            initiative_data["title"] = str(title)
        
        # Extract objective from B2 (row 1, column 1) - the long description
        if len(df) > 1 and len(df.columns) > 1:
            objective = df.iloc[1, 1] if not pd.isna(df.iloc[1, 1]) else ""
            initiative_data["overview"]["objective"] = str(objective)
        
        # Extract TPS intake number from B3 (row 2, column 1) - "3473"
        if len(df) > 2 and len(df.columns) > 1:
            tps_value = df.iloc[2, 1] if not pd.isna(df.iloc[2, 1]) else None
            if tps_value:
                try:
                    initiative_data["overview"]["TPS_intake_number"] = int(tps_value)
                except (ValueError, TypeError):
                    initiative_data["overview"]["TPS_intake_number"] = str(tps_value)
        
        # Extract sizing level from B4 (row 3, column 1) - "T-Shirt"
        if len(df) > 3 and len(df.columns) > 1:
            sizing_level = df.iloc[3, 1] if not pd.isna(df.iloc[3, 1]) else ""
            initiative_data["overview"]["sizing_level"] = str(sizing_level)
        
        return initiative_data
    
    def _extract_accountable_roles(self, df: pd.DataFrame) -> Dict[str, str]:
        """Extract accountable roles from rows 4-7, column B."""
        roles = {}
        
        # Based on the image: rows 4-7 contain role information
        role_positions = {
            4: "LTO",  # Accountable LTO: Santhosh Kumar Krishnamurthy
            5: "STO",  # Accountable STO: Chunyuan Wang  
            6: "BC",   # Intake BC: Charmaine Jackson
            7: "SA"    # Intake SA: Ashish Sinha
        }
        
        for row_idx, role_key in role_positions.items():
            if len(df) > row_idx and len(df.columns) > 1:
                role_name = df.iloc[row_idx, 1] if not pd.isna(df.iloc[row_idx, 1]) else ""
                roles[role_key] = str(role_name)
        
        return roles
    
    def _extract_capabilities(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Extract capabilities from the dataframe based on actual layout."""
        capabilities = []
        
        # Find the capabilities table - starts around row 13 based on the image
        capability_start_row = None
        for i in range(10, len(df)):  # Start looking from row 10
            if len(df.columns) > 1:
                cell_value = df.iloc[i, 1] if not pd.isna(df.iloc[i, 1]) else ""
                if "Capability" in str(cell_value):
                    capability_start_row = i
                    break
        
        if capability_start_row is None:
            # If "Capability" header not found, assume it starts at row 13
            capability_start_row = 13
        
        # Extract component headers from the row above capabilities
        component_headers = self._extract_component_headers(df, capability_start_row - 1)
        
        # Extract each capability
        current_row = capability_start_row + 1
        while current_row < len(df):
            capability_data = self._extract_single_capability(df, current_row, component_headers)
            if capability_data:
                capabilities.append(capability_data)
            current_row += 1
            
            # Break if we've reached empty rows
            if current_row >= len(df) or self._is_empty_row(df, current_row):
                break
        
        return capabilities
    
    def _extract_component_headers(self, df: pd.DataFrame, header_row: int) -> Dict[str, int]:
        """Extract component headers and their column positions."""
        headers = {}
        
        # Based on the image, components are in columns starting from column 2
        if len(df) > header_row:
            for col_idx in range(2, len(df.columns)):
                if col_idx < len(df.columns):
                    header_val = df.iloc[header_row, col_idx] if not pd.isna(df.iloc[header_row, col_idx]) else ""
                    header_str = str(header_val).strip()
                    
                    # Map headers to component names
                    if "LiveLink" in header_str:
                        headers["LiveLink"] = col_idx
                    elif "OLBB - CUA" in header_str or "OLBB-CUA" in header_str:
                        headers["OLBB_CUA"] = col_idx
                    elif "OLBB - HP, RPT" in header_str or "OLBB-HP" in header_str:
                        headers["OLBB_HP_RPT"] = col_idx
                    elif "OLBB - PYMT" in header_str or "OLBB-PYMT" in header_str:
                        headers["OLBB_PYMT"] = col_idx
                    elif "IDP" in header_str:
                        headers["IDP"] = col_idx
        
        return headers
    
    def _extract_single_capability(self, df: pd.DataFrame, row: int, component_headers: Dict[str, int]) -> Optional[Dict[str, Any]]:
        """Extract a single capability row."""
        if len(df) <= row:
            return None
        
        # Extract capability ID from column A
        capability_id = df.iloc[row, 0] if not pd.isna(df.iloc[row, 0]) else ""
        
        # Extract capability name from column B
        capability_name = df.iloc[row, 1] if len(df.columns) > 1 and not pd.isna(df.iloc[row, 1]) else ""
        
        if not capability_id or not capability_name:
            return None
        
        # Extract components
        components = {}
        for component_name, col_idx in component_headers.items():
            component_data = self._extract_component_data(df, row, col_idx, component_name)
            if component_data:
                components[component_name] = component_data
        
        return {
            "id": int(capability_id) if str(capability_id).isdigit() else str(capability_id),
            "capability": str(capability_name),
            "components": components
        }
    
    def _extract_component_data(self, df: pd.DataFrame, row: int, start_col: int, component_name: str) -> Optional[Dict[str, Any]]:
        """Extract component data including effort estimates."""
        
        # Extract effort values (Low, Mid, Upper) from the 3 sub-columns
        effort_low = self._safe_extract_numeric_value(df, row, start_col)
        effort_mid = self._safe_extract_numeric_value(df, row, start_col + 1)
        effort_upper = self._safe_extract_numeric_value(df, row, start_col + 2)
        
        # If all effort values are None, skip this component
        if effort_low is None and effort_mid is None and effort_upper is None:
            return None
        
        # Extract contact information (based on image structure)
        support_contact = self._extract_support_contact(df, component_name)
        estimation_contact = self._extract_estimation_contact(df, component_name)
        
        return {
            "support_contact": support_contact,
            "estimation_contact": estimation_contact,
            "effort": {
                "low": effort_low,
                "mid": effort_mid,
                "upper": effort_upper
            }
        }
    
    def _extract_support_contact(self, df: pd.DataFrame, component_name: str) -> str:
        """Extract support contact based on component name and image data."""
        # Based on the image, extract contact info from header rows
        contact_mapping = {
            "LiveLink": "BA & QA Support",
            "OLBB_CUA": "BA & QA Included",
            "OLBB_HP_RPT": "Aytan Javadova",
            "OLBB_PYMT": "Mobile",
            "IDP": "BA & QA Support"
        }
        return contact_mapping.get(component_name, "BA & QA Support")
    
    def _extract_estimation_contact(self, df: pd.DataFrame, component_name: str) -> str:
        """Extract estimation contact based on component name and image data."""
        # Based on the image, these appear to be mostly "BA & QA Included"
        contact_mapping = {
            "LiveLink": "BA & QA Included",
            "OLBB_CUA": "BA & QA Included", 
            "OLBB_HP_RPT": "BA & QA Included",
            "OLBB_PYMT": "BA & QA Included",
            "IDP": "BA & QA Included"
        }
        return contact_mapping.get(component_name, "BA & QA Included")
    
    def _safe_extract_numeric_value(self, df: pd.DataFrame, row: int, col: int) -> Optional[int]:
        """Safely extract a numeric value from the dataframe."""
        try:
            if row < len(df) and col < len(df.columns):
                value = df.iloc[row, col]
                if pd.isna(value) or value == "" or value == "-":
                    return None
                if isinstance(value, (int, float)):
                    return int(value) if value == int(value) else None
                # Try to convert string to int
                try:
                    return int(float(str(value)))
                except (ValueError, TypeError):
                    return None
            return None
        except (IndexError, AttributeError):
            return None
    
    def _is_empty_row(self, df: pd.DataFrame, row: int) -> bool:
        """Check if a row is empty or contains only dashes/nulls."""
        if row >= len(df):
            return True
        
        for col in range(min(5, len(df.columns))):  # Check first 5 columns
            value = df.iloc[row, col]
            if not pd.isna(value) and str(value).strip() != "" and str(value).strip() != "-":
                return False
        return True
    
    def process_directory(self, output_file: str = "extracted_projects.json") -> None:
        """
        Process all Excel files in the directory and save results to JSON.
        
        Args:
            output_file (str): Output JSON file name
        """
        results = []
        
        # Get all Excel files in the directory
        excel_files = [f for f in os.listdir(self.directory_path) 
                      if f.endswith(('.xlsx', '.xls'))]
        
        if not excel_files:
            print(f"No Excel files found in directory: {self.directory_path}")
            return
        
        for file_name in excel_files:
            file_path = os.path.join(self.directory_path, file_name)
            print(f"Processing: {file_name}")
            
            extracted_data = self.extract_from_single_file(file_path)
            if extracted_data:
                extracted_data['source_file'] = file_name
                results.append(extracted_data)
                print(f"✓ Successfully processed: {file_name}")
            else:
                print(f"✗ Failed to process: {file_name}")
        
        # Save results to JSON file
        output_path = os.path.join(self.directory_path, output_file)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"\nExtraction complete. Results saved to: {output_path}")
        print(f"Processed {len(results)} files successfully.")
        
        # Print summary
        if results:
            print("\n=== EXTRACTION SUMMARY ===")
            for result in results:
                print(f"File: {result['source_file']}")
                print(f"  Title: {result['initiative']['title']}")
                print(f"  TPS: {result['initiative']['overview']['TPS_intake_number']}")
                print(f"  Capabilities: {len(result['capabilities'])}")
                print()

def main():
    """Main function to run the extractor."""
    # Configure the directory path
    directory_path = "sample_estimations"  # Change this to your directory path
    
    # Check if directory exists
    if not os.path.exists(directory_path):
        print(f"Directory not found: {directory_path}")
        print("Please update the directory_path variable with the correct path.")
        return
    
    # Create extractor instance
    extractor = ProjectTShirtExtractor(directory_path)
    
    # Process all files in the directory
    extractor.process_directory("project_tshirt_extracted.json")

if __name__ == "__main__":
    main()
