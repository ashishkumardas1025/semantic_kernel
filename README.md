import os
import pandas as pd

# Directory containing the Excel files
directory_path = "path_to_directory"

# Initialize lists to hold the data from the sheets
capability_list_data = []
project_tshirt_data = []

# Iterate through each file in the directory
for filename in os.listdir(directory_path):
    if filename.endswith(".xlsx"):
        file_path = os.path.join(directory_path, filename)

        # Open the Excel file
        with pd.ExcelFile(file_path) as xls:
            # Check for the presence of the relevant sheets
            if "Capability List" in xls.sheet_names:
                capability_list_df = pd.read_excel(file_path, sheet_name="Capability List")
                capability_list_data.append(capability_list_df)

            if "Project T-Shirt" in xls.sheet_names:
                project_tshirt_df = pd.read_excel(file_path, sheet_name="Project T-Shirt")
                project_tshirt_data.append(project_tshirt_df)

# Concatenate the data from all files
if capability_list_data:
    capability_list_df = pd.concat(capability_list_data, ignore_index=True)

if project_tshirt_data:
    project_tshirt_df = pd.concat(project_tshirt_data, ignore_index=True)

# Function to link and consolidate data based on capability
def link_and_consolidate_data(capability_list_df, project_tshirt_df):
    consolidated_data = []

    # Iterate through each row in the Capability List sheet
    for _, capability_row in capability_list_df.iterrows():
        capability = capability_row["Capability"]
        scope_business_description = capability_row["Scope/Business Description"]
        system_changes = capability_row["System Change"]

        # Find matching capability in the Project T-Shirt sheet
        matching_rows = project_tshirt_df[project_tshirt_df["Capability"] == capability]

        for _, tshirt_row in matching_rows.iterrows():
            intake_bc = tshirt_row["Intake BC"]
            intake_sa = tshirt_row["Intake SA"]
            team_information = tshirt_row["Team Information"]
            estimation_contact = tshirt_row["Estimation Contact"]
            ba_qa_support = tshirt_row.get("BA & QA Support", "")
            cost_information = {
                "Low": tshirt_row["Low"],
                "Med": tshirt_row["Med"],
                "Upper": tshirt_row["Upper"],
                "Sub Total": tshirt_row["Sub Total"],
                "Project Support": tshirt_row["Project Support"],
                "Total": tshirt_row["Total"]
            }

            # Create a consolidated entry
            consolidated_entry = {
                "sheet": "Capability List",
                "capability": capability,
                "scope_business_description": scope_business_description,
                "system_changes": system_changes,
                "Intake BC": intake_bc,
                "Intake SA": intake_sa,
                "Team Information": team_information,
                "Estimation Contact": estimation_contact,
                "BA & QA Support": ba_qa_support,
                "Cost Information": cost_information
            }

            consolidated_data.append(consolidated_entry)

    return consolidated_data

# Link and consolidate data
consolidated_data = link_and_consolidate_data(capability_list_df, project_tshirt_df)

# Example output
for entry in consolidated_data:
    print(entry)
----------------------
{
  "sheet": "Capability List",
  "capability": "Mutual Funds Product Selection",
  "scope_business_description": "In OLBB, users need to select mutual fund as a product for selection during investment.",
  "system_changes": "Enable support for selection in MF accounts at product selection widget.",
  "Intake BC": "Business Case Details",
  "Intake SA": "Solution Architecture Details",
  "Team Information": "OLBB-CUA",
  "Estimation Contact": "Contact Details",
  "BA & QA Support": "Support Details (if available)",
  "Cost Information": {
    "Low": 1000,
    "Med": 2000,
    "Upper": 3000,
    "Sub Total": 4000,
    "Project Support": 500,
    "Total": 4500
  }
}
