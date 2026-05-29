import pandas as pd
xl = pd.ExcelFile("Sigma CDMX Aprovado.xlsx")
df_plan_raw = xl.parse("Campaign Plan", skiprows=21)
print("Row count of raw table after skiprows=21:", len(df_plan_raw))
print("Null Reference IDs:")
print(df_plan_raw[df_plan_raw["Reference ID"].isna()])
print("Reference IDs value counts (including nulls/unnamed):")
print(df_plan_raw["Reference ID"].value_counts(dropna=False))
