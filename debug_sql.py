import sqlalchemy
from sqlalchemy import create_engine
from database import Campaign, OOHInventory, get_db_session, init_db
import pandas as pd

print("SQLAlchemy Version:", sqlalchemy.__version__)

db = get_db_session()
try:
    # Let's inspect the columns of ooh_inventory table from SQLAlchemy perspective
    print("\nSQLAlchemy OOHInventory Columns:")
    for col in OOHInventory.__table__.columns:
        print(f"  {col.name}: {col.type}")
        
    # Let's see if we can perform a simple single row insert manually and if it works
    inv = OOHInventory(
        campaign_id='Mx_AdsmovilOOH_Sigma_Fud Panela_Cdmx_Abr-May V1',
        name='Test',
        billboard_name='Test Billboard',
        reference_id='TEST-REF',
        ooh_impressions=1000,
        unique_reach='500',
        frequency=1.2,
        ecpm_mxn=100.0,
        audience_concentration=1.0,
        media_owner='Sankofa',
        format='LED',
        resolution='1920*1080',
        size='4*6',
        latitude=19.357,
        longitude=-99.197,
        category='OUTDOOR',
        location='Mexico City',
        address='Test Address'
    )
    db.add(inv)
    db.commit()
    print("\n✅ Single row insert committed successfully!")
    
    # Clean up single row insert
    db.delete(inv)
    db.commit()
    print("✅ Single row insert cleaned up successfully!")
    
except Exception as e:
    print("\n❌ Single row insert failed:", e)
    db.rollback()
finally:
    db.close()
