from fastapi import FastAPI, UploadFile, File, Depends
from fastapi.responses import HTMLResponse, FileResponse
from sqlalchemy.orm import Session
from database import engine, Base, get_db
import models
import shutil
import os
import re

# Create database tables when the app starts
Base.metadata.create_all(bind=engine)

   app = FastAPI(title="Land Record System", docs_url=None, redoc_url=None)

# Create a folder to store the actual uploaded files
os.makedirs("uploaded_files", exist_ok=True)

@app.get("/")
def read_root():
    return FileResponse("index.html")

# ==========================================
# UPLOAD & FETCH APIs
# ==========================================

@app.post("/api/documents/upload/")
async def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db)):
    file_path = f"uploaded_files/{file.filename}"
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    db_doc = models.Document(
        filename=file.filename, 
        file_path=file_path, 
        status="UPLOADED"
    )
    db.add(db_doc)
    db.commit()
    db.refresh(db_doc)
    
    return {
        "message": "File uploaded successfully!", 
        "document_id": db_doc.id, 
        "status": "UPLOADED"
    }

@app.get("/api/documents/")
def get_documents(db: Session = Depends(get_db)):
    docs = db.query(models.Document).all()
    return [
        {
            "id": doc.id, 
            "filename": doc.filename, 
            "status": doc.status, 
            "uploaded_at": str(doc.created_at)
        } 
        for doc in docs
    ]

# ==========================================
# DELETE API
# ==========================================

@app.delete("/api/documents/{document_id}/")
def delete_document(document_id: int, db: Session = Depends(get_db)):
    doc = db.query(models.Document).filter(models.Document.id == document_id).first()
    if not doc:
        return {"error": "Document not found"}
    
    if os.path.exists(doc.file_path):
        os.remove(doc.file_path)
    
    db.query(models.LandRecord).filter(models.LandRecord.document_id == document_id).delete()
    db.delete(doc)
    db.commit()
    
    return {"message": f"Document {document_id} deleted successfully!"}

# ==========================================
# AI EXTRACTION API (REAL OCR)
# ==========================================

@app.post("/api/records/extract/")
def simulate_ai_extraction(document_id: int, db: Session = Depends(get_db)):
    import easyocr
    
    doc = db.query(models.Document).filter(models.Document.id == document_id).first()
    if not doc:
        return {"error": "Document not found"}
    
    doc.status = "PROCESSING"
    db.commit()
    
    try:
        reader = easyocr.Reader(['en', 'hi'], gpu=False)
        results = reader.readtext(doc.file_path)
        extracted_text = " ".join([r[1] for r in results])
        
        avg_confidence = sum([r[2] for r in results]) / len(results) * 100 if results else 0.0
        text_upper = extracted_text.upper()
        
        khata_match = re.search(r'KHATA\s*NO\.?\s*[:\-]?\s*(\d+)', text_upper)
        khata = khata_match.group(1) if khata_match else "Not Detected"
        
        tehsil_match = re.search(r'TEHSIL\s*[:\-]?\s*([A-Z\s]+?)(?:DISTRICT|$)', text_upper)
        tehsil = tehsil_match.group(1).strip() if tehsil_match else "Not Detected"
        
        district_match = re.search(r'DISTRICT\s*[:\-]?\s*([A-Z\s]+?)(?:STATE|$)', text_upper)
        district = district_match.group(1).strip() if district_match else "Not Detected"
        
        classification_match = re.search(r'(AGRICULTURAL|RESIDENTIAL|COMMERCIAL|BARREN)', text_upper)
        classification = classification_match.group(1).title() if classification_match else "Not Detected"

        new_record = models.LandRecord(
            document_id=document_id,
            owner_name=extracted_text[:50] if extracted_text else "Not Detected",
            khasra_number=re.search(r'KHASRA\s*[:\-]?\s*(\d+[/\d]*)', text_upper).group(1) if re.search(r'KHASRA\s*[:\-]?\s*(\d+[/\d]*)', text_upper) else "Not Detected",
            khata_number=khata,
            plot_area=float(re.search(r'(\d+\.?\d*)\s*(?:ACRE|HECTARE)', text_upper).group(1)) if re.search(r'(\d+\.?\d*)\s*(?:ACRE|HECTARE)', text_upper) else 0.0,
            village=re.search(r'VILLAGE\s*[:\-]?\s*([A-Z\s]+?)(?:TEHSIL|$)', text_upper).group(1).strip() if re.search(r'VILLAGE\s*[:\-]?\s*([A-Z\s]+?)(?:TEHSIL|$)', text_upper) else "Not Detected",
            tehsil=tehsil,
            district=district,
            land_classification=classification,
            confidence_score=round(avg_confidence, 2),
            is_verified=False
        )
        
        doc.status = "COMPLETED"
        db.add(new_record)
        db.commit()
        db.refresh(new_record)
        
        return {
            "message": "AI extraction completed!",
            "record_id": new_record.id,
            "owner_name": new_record.owner_name,
            "khasra_number": new_record.khasra_number,
            "khata_number": new_record.khata_number,
            "plot_area": new_record.plot_area,
            "village": new_record.village,
            "tehsil": new_record.tehsil,
            "district": new_record.district,
            "land_classification": new_record.land_classification,
            "confidence_score": new_record.confidence_score
        }
        
    except Exception as e:
        doc.status = "ERROR"
        db.commit()
        return {"error": f"OCR failed: {str(e)}"}

# ==========================================
# PENDING VERIFICATIONS API
# ==========================================

@app.get("/api/records/pending/")
def get_pending_verifications(db: Session = Depends(get_db)):
    pending_records = db.query(models.LandRecord).filter(
        models.LandRecord.confidence_score < 85.0,
        models.LandRecord.is_verified == False
    ).all()
    
    return [
        {
            "record_id": rec.id,
            "document_id": rec.document_id,
            "owner_name": rec.owner_name,
            "khasra_number": rec.khasra_number,
            "plot_area": rec.plot_area,
            "village": rec.village,
            "confidence_score": rec.confidence_score
        }
        for rec in pending_records
    ]

# ==========================================
# HTML DASHBOARD
# ==========================================

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(db: Session = Depends(get_db)):
    records = db.query(models.LandRecord).all()
    
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Land Records Dashboard</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }
            h1 { color: #333; }
            table { width: 100%; border-collapse: collapse; background: white; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            th, td { padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }
            th { background-color: #007bff; color: white; }
            tr:hover { background-color: #f5f5f5; }
            .low-confidence { color: #dc3545; font-weight: bold; }
            .high-confidence { color: #28a745; font-weight: bold; }
        </style>
    </head>
    <body>
        <h1>🏛️ Land Records Dashboard</h1>
        <p>Total Records: """ + str(len(records)) + """</p>
        <table>
            <tr>
                <th>ID</th>
                <th>Owner Name</th>
                <th>Khasra Number</th>
                <th>Plot Area</th>
                <th>Village</th>
                <th>Confidence Score</th>
                <th>Verified</th>
            </tr>
    """
    
    for rec in records:
        confidence_class = "low-confidence" if rec.confidence_score < 85 else "high-confidence"
        verified_text = "✅ Yes" if rec.is_verified else "⏳ Pending"
        
        html += f"""
            <tr>
                <td>{rec.id}</td>
                <td>{rec.owner_name or 'N/A'}</td>
                <td>{rec.khasra_number or 'N/A'}</td>
                <td>{rec.plot_area or 'N/A'}</td>
                <td>{rec.village or 'N/A'}</td>
                <td class="{confidence_class}">{rec.confidence_score}%</td>
                <td>{verified_text}</td>
            </tr>
        """
    
    html += """
        </table>
        <br>
        <p><a href="/docs">← Back to API Documentation</a></p>
    </body>
    </html>
    """
    return html