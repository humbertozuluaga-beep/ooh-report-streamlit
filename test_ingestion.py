import sys
import os
import pandas as pd

# Import app modules directly from current directory
from database import get_db_session, Campaign, OOHInventory, Performance
from app import parse_campaign_excel

def test_full_pipeline():
    print("=========================================")
    print("STARTING PIPELINE END-TO-END VERIFICATION")
    print("=========================================")
    
    workspace_dir = "."
    
    # 1. Parse and ingest Campaign
    campaign_file = os.path.join(workspace_dir, "Sigma CDMX Aprovado.xlsx")
    print(f"\n1. Ingesting Campaign details from: {os.path.basename(campaign_file)}")
    metadata, df_inventory = parse_campaign_excel(campaign_file)
    
    print(f"   Deal (Campaign) ID: {metadata['id']}")
    print(f"   Campaign Name: {metadata['name']}")
    print(f"   Dates: {metadata['start_date']} to {metadata['end_date']}")
    print(f"   Inventory records found: {len(df_inventory)}")
    
    # Save to Postgres
    db = get_db_session()
    try:
        from database import save_campaign_to_db, save_performance_to_db
        
        # Ingest campaign
        inventory_records = df_inventory.to_dict(orient='records')
        save_campaign_to_db(
            db=db,
            campaign_id=metadata["id"],
            campaign_name=metadata["name"],
            start_date=metadata["start_date"],
            end_date=metadata["end_date"],
            inventory_records=inventory_records
        )
        print("   ✅ Campaign details and OOH inventory successfully written to PostgreSQL!")
        
        # 2. Ingest Performance Sheets
        performance_files = [
            "1 JCD - KIOSCO_Sigma Fud Queso CDMX_AbrJun26.xlsx",
            "1 Sankofa 1 Pantalla 800x384.xlsx"
        ]
        
        for pf_name in performance_files:
            pf_path = os.path.join(workspace_dir, pf_name)
            print(f"\n2. Ingesting performance file: {pf_name}")
            xl = pd.ExcelFile(pf_path)
            df_perf = xl.parse("MAX Line Item Report")
            
            rows_saved = save_performance_to_db(db, metadata["id"], df_perf, pf_name)
            print(f"   ✅ Saved {rows_saved} performance rows into PostgreSQL under campaign ID: {metadata['id']}")
            
        # 3. Verify Database counts
        print("\n3. Verifying Database Counts & Relations:")
        campaign_count = db.query(Campaign).count()
        inventory_count = db.query(OOHInventory).filter(OOHInventory.campaign_id == metadata["id"]).count()
        performance_count = db.query(Performance).filter(Performance.campaign_id == metadata["id"]).count()
        
        print(f"   Campaign count: {campaign_count}")
        print(f"   Inventory count (expected 38): {inventory_count}")
        print(f"   Performance count (expected 432): {performance_count}")
        
        assert campaign_count == 1, f"Expected 1 campaign, found {campaign_count}"
        assert inventory_count == 38, f"Expected 38 inventory records, found {inventory_count}"
        assert performance_count == 432, f"Expected 432 performance records, found {performance_count}"
        
        print("\n🎉 ALL INGESTION PIPELINE VERIFICATIONS PASSED 100% PERFECTLY!")
        
    except Exception as e:
        print(f"\n❌ PIPELINE VERIFICATION FAILED: {e}")
        db.rollback()
        raise e
    finally:
        db.close()

if __name__ == "__main__":
    test_full_pipeline()
