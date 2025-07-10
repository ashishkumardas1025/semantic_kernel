import pandas as pd

# Load the Excel sheets
capability_list_df = pd.read_excel("path_to_capability_list.xlsx")
project_tshirt_df = pd.read_excel("path_to_project_tshirt.xlsx")

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
