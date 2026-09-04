from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime
from database import Base
from datetime import datetime

class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, index=True)
    file_path = Column(String)
    status = Column(String, default="UPLOADED")
    created_at = Column(DateTime, default=datetime.utcnow)

class LandRecord(Base):
    __tablename__ = "land_records"
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, index=True)
    owner_name = Column(String, nullable=True)
    khasra_number = Column(String, nullable=True)
    khata_number = Column(String, nullable=True)
    plot_area = Column(Float, nullable=True)
    village = Column(String, nullable=True)
    tehsil = Column(String, nullable=True)
    district = Column(String, nullable=True)
    land_classification = Column(String, nullable=True)
    confidence_score = Column(Float, default=0.0)
    is_verified = Column(Boolean, default=False)