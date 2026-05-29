import sqlalchemy
from sqlalchemy import create_engine, insert
from database import Campaign, OOHInventory, get_db_session, init_db, clean_numeric
from app import parse_campaign_excel
import pandas as pd

print("SQLAlchemy Version:", sqlalchemy.__version__)

db = get_db_session()
try:
    # First, let's clean any existing campaign
    campaign_id = 'Mx_AdsmovilOOH_Sigma_Fud Panela_Cdmx_Abr-May V1'
    existing = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if existing:
        db.delete(existing)
        db.commit()
        print("Cleared existing campaign.")
        
    # Ingest Campaign details from file
    metadata, df_inventory = parse_campaign_excel("Sigma CDMX Aprovado.xlsx")
    
    # Create campaign
    camp = Campaign(
        id=metadata["id"],
        name=metadata["name"] if pd.notna(metadata["name"]) else metadata["id"],
        start_date=metadata["start_date"],
        end_date=metadata["end_date"]
    )
    db.add(camp)
    db.flush() # Flush to database so campaign exists for foreign key
    print("Flushed campaign.")
    
    # Core bulk insert for inventory
    inventory_records = df_inventory.to_dict(orient='records')
    ooh_inventories_to_insert = []
    for rec in inventory_records:
        ooh_inventories_to_insert.append({
            'campaign_id': metadata["id"],
            'name': rec.get('Name'),
            'billboard_name': rec.get('Billboard Name'),
            'reference_id': rec.get('Reference ID'),
            'ooh_impressions': clean_numeric(rec.get('OOH Impressions')),
            'unique_reach': str(rec.get('Unique Reach')) if pd.notna(rec.get('Unique Reach')) else None,
            'frequency': clean_numeric(rec.get('Frequency')),
            'ecpm_mxn': clean_numeric(rec.get('eCPM (MXN)')),
            'audience_concentration': clean_numeric(rec.get('Audience Concentration')),
            'media_owner': rec.get('Media Owner'),
            'format': rec.get('Format'),
            'resolution': rec.get('Resolution (W x H) px'),
            'size': rec.get('Size (W x H) ft'),
            'latitude': clean_numeric(rec.get('Latitude')),
            'longitude': clean_numeric(rec.get('Longitude')),
            'category': rec.get('Category'),
            'location': rec.get('Location'),
            'address': rec.get('Address')
        })
        
    print(f"Constructed {len(ooh_inventories_to_insert)} records to insert.")
    
    # Execute core insert statement
    db.execute(insert(OOHInventory), ooh_inventories_to_insert)
    db.commit()
    print("✅ Core insert committed successfully!")
    
except Exception as e:
    print("\n❌ Core insert failed:", e)
    db.rollback()
finally:
    db.close()
