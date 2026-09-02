from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime
from database import Base
import datetime

# Table 1: To store information about the uploaded files
class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, index=True)
    file_path = Column(String)
    status = Column(String, default="UPLOADED") # UPLOADED, PROCESSING, COMPLETED
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

# Table 2: To store the actual land record data extracted by AI
class LandRecord(Base):
    __tablename__ = "land_records"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer) # Links back to the Document table
    owner_name = Column(String, nullable=True)
    khasra_number = Column(String, nullable=True)
    plot_area = Column(Float, nullable=True)
    village = Column(String, nullable=True)
    confidence_score = Column(Float, default=0.0)
    is_verified = Column(Boolean, default=False)
