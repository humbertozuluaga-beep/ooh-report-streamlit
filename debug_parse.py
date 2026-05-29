import pandas as pd
import numpy as np

file_path = "Sigma CDMX Aprovado.xlsx"
xl = pd.ExcelFile(file_path)

# Let's inspect the sheets
print("Sheet Names:", xl.sheet_names)

# Ingest Campaign details
df_plan_raw = xl.parse("Campaign Plan", header=None)
print("\nRaw rows in Campaign Plan:")
for idx, row in df_plan_raw.head(20).iterrows():
    print(f"Row {idx}: {list(row)[:6]}")

# Let's find Reference ID
keyword = "Reference ID"
header_idx = None
for idx, row in df_plan_raw.iterrows():
    if any(isinstance(val, str) and keyword.lower() in val.lower() for val in row):
        header_idx = idx
        print(f"\nFound '{keyword}' at row index {idx}")
        print("Row content:", list(row))
        break

if header_idx is not None:
    df_inv = xl.parse("Campaign Plan", skiprows=header_idx)
    print("\nColumns after skiprows:", list(df_inv.columns))
    df_inv = df_inv.dropna(subset=["Reference ID"])
    df_inv.columns = [str(c).strip() for c in df_inv.columns]
    print("\nFiltered Columns:", list(df_inv.columns))
    print("\nFirst row of df_inv:")
    print(df_inv.iloc[0].to_dict())
    
    # Check if there is Inventory Details sheet
    if "Inventory Details" in xl.sheet_names:
        df_details_raw = xl.parse("Inventory Details", header=None)
        details_header_idx = None
        for idx, row in df_details_raw.iterrows():
            if any(isinstance(val, str) and keyword.lower() in val.lower() for val in row):
                details_header_idx = idx
                break
        if details_header_idx is not None:
            df_details = xl.parse("Inventory Details", skiprows=details_header_idx)
            df_details = df_details.dropna(subset=["Reference ID"])
            df_details.columns = [str(c).strip() for c in df_details.columns]
            df_details = df_details.loc[:, ~df_details.columns.str.contains('^Unnamed')]
            print("\nInventory Details columns:", list(df_details.columns))
            print("\nFirst row of details:")
            print(df_details.iloc[0].to_dict())
            
            # Let's do the merge
            cols_to_use = df_details.columns.difference(df_inv.columns).tolist() + ['Reference ID']
            merged_inv = pd.merge(df_inv, df_details[cols_to_use], on="Reference ID", how="left")
            print("\nMerged inventory columns:", list(merged_inv.columns))
            print("\nFirst row of merged inventory:")
            print(merged_inv.iloc[0].to_dict())
            
            # Let's check for any column alignment issues, particularly with latitude, longitude
            print("\nTypes in merged inventory:")
            for col in merged_inv.columns:
                print(f"  {col}: {merged_inv[col].dtype}")
                
            # Let's check if there are any non-numeric coordinates or values in merged_inv
            print("\nChecking latitude / longitude values:")
            print(merged_inv[['Reference ID', 'Latitude', 'Longitude']].head(10))
            
            # Print if any Latitude has non-numeric type
            for idx, row in merged_inv.iterrows():
                lat = row.get('Latitude')
                lon = row.get('Longitude')
                if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
                    print(f"Non-numeric coord at row {idx}: Ref ID {row.get('Reference ID')}, Lat: {lat} ({type(lat)}), Lon: {lon} ({type(lon)})")
