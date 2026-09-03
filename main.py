from fastapi import FastAPI, UploadFile, File, Depends
from fastapi.responses import HTMLResponse, FileResponse
from sqlalchemy.orm import Session
from database import engine, Base, get_db
import models
import shutil
import os

# Create database tables when the app starts
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Land Record System")

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
# DELETE API (NEW!)
# ==========================================

@app.delete("/api/documents/{document_id}/")
def delete_document(document_id: int, db: Session = Depends(get_db)):
    # Step 1: Find the document in the database
    doc = db.query(models.Document).filter(models.Document.id == document_id).first()
    
    if not doc:
        return {"error": "Document not found"}
    
    # Step 2: Delete the actual file from the 'uploaded_files' folder
    if os.path.exists(doc.file_path):
        os.remove(doc.file_path)
    
    # Step 3: Delete the related land records (if any)
    db.query(models.LandRecord).filter(models.LandRecord.document_id == document_id).delete()
    
    # Step 4: Delete the document record from the database
    db.delete(doc)
    db.commit()
    
    return {"message": f"Document {document_id} deleted successfully!"}

# ==========================================
# AI SIMULATION & VERIFICATION APIs
# ==========================================

@app.post("/api/records/extract/")
def simulate_ai_extraction(document_id: int, db: Session = Depends(get_db)):
    doc = db.query(models.Document).filter(models.Document.id == document_id).first()
    if not doc:
        return {"error": "Document not found"}
    
    doc.status = "COMPLETED"
    db.commit()

    # TODO: During the hackathon, your AI teammate will give you a function like this:
    # real_ai_data = ai_teammate.extract_text(doc.file_path)
    
    # For now, we will just save empty/placeholder data until the AI is ready
    real_ai_data = {
        "owner_name": "Pending AI Extraction",
        "khasra_number": "Pending",
        "plot_area": 0.0,
        "village": "Pending",
        "confidence_score": 0.0
    }

    new_record = models.LandRecord(
        document_id=document_id,
        owner_name=real_ai_data["owner_name"],
        khasra_number=real_ai_data["khasra_number"],
        plot_area=real_ai_data["plot_area"],
        village=real_ai_data["village"],
        confidence_score=real_ai_data["confidence_score"],
        is_verified=False
    )
    db.add(new_record)
    db.commit()
    db.refresh(new_record)

    return {"message": "AI extraction simulated and saved!", "record_id": new_record.id}

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
    ]# ==========================================
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
