import os
import pandas as pd
from sqlalchemy import (
    create_engine, Column, String, Date, Numeric, Integer,
    ForeignKey, DateTime, func, Text, insert
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.dialects.postgresql import JSONB

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/ooh_reports")

Base = declarative_base()

class Campaign(Base):
    __tablename__ = 'campaigns'

    id = Column(String(255), primary_key=True)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=func.now())

    # --- Campaign Details ---
    created_on = Column(Date, nullable=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    media_type = Column(String(100), nullable=True)
    total_cost_ooh = Column(Numeric, nullable=True)
    net_cost = Column(Numeric, nullable=True)

    # --- Buyer Details ---
    created_by = Column(String(255), nullable=True)
    company = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True)
    dsp = Column(String(255), nullable=True)
    seat_id = Column(String(100), nullable=True)
    brand = Column(String(255), nullable=True)
    product = Column(String(255), nullable=True)
    ad_plays_planned = Column(String(100), nullable=True)

    # --- Estimation (OOH only) ---
    audience_segment = Column(String(255), nullable=True)
    total_ooh_impressions_planned = Column(Numeric, nullable=True)
    unique_reach_planned = Column(Numeric, nullable=True)
    average_frequency = Column(Numeric, nullable=True)
    ecpm_mxn_planned = Column(Numeric, nullable=True)
    campaign_audience_concentration = Column(Numeric, nullable=True)
    share_of_time = Column(String(50), nullable=True)

    inventories = relationship("OOHInventory", back_populates="campaign", cascade="all, delete-orphan")
    performances = relationship("Performance", back_populates="campaign", cascade="all, delete-orphan")


class OOHInventory(Base):
    __tablename__ = 'ooh_inventory'

    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(String(255), ForeignKey('campaigns.id', ondelete='CASCADE'), nullable=False)

    # --- Campaign Plan: Inventory Planning ---
    reference_id = Column(String(100), nullable=True)
    name = Column(String(255), nullable=True)
    billboard_name = Column(String(255), nullable=True)
    ooh_impressions = Column(Numeric, nullable=True)
    unique_reach = Column(String(100), nullable=True)
    frequency = Column(Numeric, nullable=True)
    ecpm_mxn = Column(Numeric, nullable=True)
    audience_concentration = Column(Numeric, nullable=True)

    # --- Inventory Details ---
    media_owner = Column(String(255), nullable=True)
    format = Column(String(255), nullable=True)
    resolution = Column(String(100), nullable=True)
    size = Column(String(100), nullable=True)
    creative = Column(Text, nullable=True)
    latitude = Column(Numeric, nullable=True)
    longitude = Column(Numeric, nullable=True)
    exclusions = Column(Text, nullable=True)
    asset_images = Column(Text, nullable=True)
    category = Column(String(100), nullable=True)
    location = Column(String(255), nullable=True)
    venue_type = Column(String(255), nullable=True)
    no_of_screens = Column(Integer, nullable=True)
    spot_duration_sec = Column(Numeric, nullable=True)
    spots_per_hour = Column(Numeric, nullable=True)
    inv_ad_plays = Column(Numeric, nullable=True)
    language_support = Column(String(255), nullable=True)
    address = Column(Text, nullable=True)
    site_description = Column(Text, nullable=True)

    # --- Costing ---
    media_cost_mxn = Column(Numeric, nullable=True)
    total_cost_mxn = Column(Numeric, nullable=True)

    campaign = relationship("Campaign", back_populates="inventories")


class Performance(Base):
    __tablename__ = 'performance'

    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(String(255), ForeignKey('campaigns.id', ondelete='CASCADE'), nullable=False)
    date = Column(Date, nullable=True)
    ad_plays = Column(Numeric, nullable=True)
    billed_ad_play = Column(Numeric, nullable=True)
    billed_impressions = Column(Numeric, nullable=True)
    ooh_impressions = Column(Numeric, nullable=True)
    media_cost = Column(Numeric, nullable=True)
    spent = Column(Numeric, nullable=True)
    publisher = Column(String(255), nullable=True)
    inventory = Column(String(255), nullable=True)
    extra_data = Column(JSONB, nullable=True)
    file_name = Column(String(255), nullable=True)
    uploaded_at = Column(DateTime, default=func.now())

    campaign = relationship("Campaign", back_populates="performances")


engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db_session():
    return SessionLocal()


def clean_numeric(val):
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(val, (int, float)):
        return float(val)
    val_str = str(val).replace('MXN', '').replace('$', '').replace(',', '').strip()
    # Quitar sufijos de texto como "- DB"
    val_str = val_str.split('-')[0].strip() if '-' in val_str else val_str
    try:
        return float(val_str)
    except ValueError:
        return None


def save_campaign_to_db(db, metadata, inventory_records):
    """
    Guarda la campaña (con todos sus metadatos) y su inventario en una sola
    transacción atómica. Si la campaña ya existe se elimina y re-inserta.
    """
    campaign_id = metadata['id']

    existing = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if existing:
        db.delete(existing)
        db.flush()

    campaign = Campaign(
        id=campaign_id,
        name=metadata['name'],
        # Campaign Details
        created_on=metadata.get('created_on'),
        start_date=metadata.get('start_date'),
        end_date=metadata.get('end_date'),
        media_type=metadata.get('media_type'),
        total_cost_ooh=metadata.get('total_cost_ooh'),
        net_cost=metadata.get('net_cost'),
        # Buyer Details
        created_by=metadata.get('created_by'),
        company=metadata.get('company'),
        email=metadata.get('email'),
        dsp=metadata.get('dsp'),
        seat_id=str(metadata['seat_id']) if metadata.get('seat_id') is not None else None,
        brand=metadata.get('brand'),
        product=metadata.get('product'),
        ad_plays_planned=str(metadata['ad_plays_planned']) if metadata.get('ad_plays_planned') is not None else None,
        # Estimation
        audience_segment=metadata.get('audience_segment'),
        total_ooh_impressions_planned=metadata.get('total_ooh_impressions_planned'),
        unique_reach_planned=metadata.get('unique_reach_planned'),
        average_frequency=metadata.get('average_frequency'),
        ecpm_mxn_planned=metadata.get('ecpm_mxn_planned'),
        campaign_audience_concentration=metadata.get('campaign_audience_concentration'),
        share_of_time=str(metadata['share_of_time']) if metadata.get('share_of_time') is not None else None,
    )
    db.add(campaign)
    db.flush()

    def _str(val):
        """Convierte a string solo si no es NaN/None."""
        if val is None:
            return None
        try:
            if pd.isna(val):
                return None
        except (TypeError, ValueError):
            pass
        return str(val)

    def _int(val):
        n = clean_numeric(val)
        return int(n) if n is not None else None

    ooh_inventories_to_insert = []
    for rec in inventory_records:
        ooh_inventories_to_insert.append({
            'campaign_id': campaign_id,
            # Campaign Plan
            'reference_id': _str(rec.get('Reference ID')),
            'name': _str(rec.get('Name')),
            'billboard_name': _str(rec.get('Billboard Name')),
            'ooh_impressions': clean_numeric(rec.get('OOH Impressions')),
            'unique_reach': _str(rec.get('Unique Reach')),
            'frequency': clean_numeric(rec.get('Frequency')),
            'ecpm_mxn': clean_numeric(rec.get('eCPM (MXN)')),
            'audience_concentration': clean_numeric(rec.get('Audience Concentration')),
            # Inventory Details
            'media_owner': _str(rec.get('Media Owner')),
            'format': _str(rec.get('Format')),
            'resolution': _str(rec.get('Resolution (W x H) px')),
            'size': _str(rec.get('Size (W x H) ft')),
            'creative': _str(rec.get('Creative')),
            'latitude': clean_numeric(rec.get('Latitude')),
            'longitude': clean_numeric(rec.get('Longitude')),
            'exclusions': _str(rec.get('Exclusions')),
            'asset_images': _str(rec.get('Asset Images')),
            'category': _str(rec.get('Category')),
            'location': _str(rec.get('Location')),
            'venue_type': _str(rec.get('Venue Type')),
            'no_of_screens': _int(rec.get('No of Screens')),
            'spot_duration_sec': clean_numeric(rec.get('Spot Duration (sec)')),
            'spots_per_hour': clean_numeric(rec.get('Spots / Hour')),
            'inv_ad_plays': clean_numeric(rec.get('Ad Plays')),
            'language_support': _str(rec.get('Language Support')),
            'address': _str(rec.get('Address')),
            'site_description': _str(rec.get('Site Description')),
            # Costing
            'media_cost_mxn': clean_numeric(rec.get('Media Cost(MXN)')),
            'total_cost_mxn': clean_numeric(rec.get('Total Cost(MXN)')),
        })

    if ooh_inventories_to_insert:
        db.execute(insert(OOHInventory), ooh_inventories_to_insert)

    db.commit()
    return campaign


# Columnas conocidas del schema de performance
_KNOWN_PERF_COLS = {
    'Date', 'Ad Plays', 'Billed Ad Play', 'Billed Impressions',
    'OOH Impressions', 'Media Cost', 'Spent', 'Publisher', 'Inventory'
}


def save_performance_to_db(db, campaign_id, performance_df, file_name):
    """
    Guarda métricas de performance. Las columnas conocidas se mapean a campos
    tipados; el resto se almacena en extra_data (JSONB).
    Retorna 0 si el archivo ya fue importado previamente.
    """
    already_exists = db.query(Performance).filter(
        Performance.campaign_id == campaign_id,
        Performance.file_name == file_name
    ).first()
    if already_exists:
        return 0

    extra_cols = [c for c in performance_df.columns if c not in _KNOWN_PERF_COLS]

    perf_records = []
    for _, row in performance_df.iterrows():
        row_date = row.get('Date')
        if pd.notna(row_date):
            if isinstance(row_date, (int, float)):
                row_date = pd.to_datetime(row_date, unit='D', origin='1899-12-30').date()
            elif isinstance(row_date, str):
                try:
                    row_date = pd.to_datetime(row_date).date()
                except ValueError:
                    row_date = None
            elif hasattr(row_date, 'date'):
                row_date = row_date.date()
        else:
            row_date = None

        extra = {}
        for col in extra_cols:
            val = row.get(col)
            if pd.notna(val):
                extra[col] = val if isinstance(val, (int, float, bool)) else str(val)

        perf_records.append({
            'campaign_id': campaign_id,
            'date': row_date,
            'ad_plays': clean_numeric(row.get('Ad Plays')),
            'billed_ad_play': clean_numeric(row.get('Billed Ad Play')),
            'billed_impressions': clean_numeric(row.get('Billed Impressions')),
            'ooh_impressions': clean_numeric(row.get('OOH Impressions')),
            'media_cost': clean_numeric(row.get('Media Cost')),
            'spent': clean_numeric(row.get('Spent')),
            'publisher': str(row.get('Publisher')) if pd.notna(row.get('Publisher')) else None,
            'inventory': str(row.get('Inventory')) if pd.notna(row.get('Inventory')) else None,
            'extra_data': extra if extra else None,
            'file_name': file_name,
        })

    if perf_records:
        db.execute(insert(Performance), perf_records)
        db.commit()
        return len(perf_records)
    return 0
