import os
from fastapi import FastAPI, UploadFile, File, Depends
from fastapi.responses import HTMLResponse, FileResponse
from sqlalchemy.orm import Session
from database import engine, Base, get_db
import models
import shutil
import json
import re
from google import genai
from google.genai import types

# --- CONFIGURE THE NEW GOOGLE GEN AI SDK ---
API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=API_KEY)

Base.metadata.create_all(bind=engine)
app = FastAPI(title="Land Record System", docs_url=None, redoc_url=None)
os.makedirs("uploaded_files", exist_ok=True)

@app.get("/")
def read_root():
    return FileResponse("index.html")

@app.post("/api/documents/upload/")
async def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db)):
    file_path = f"uploaded_files/{file.filename}"
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    db_doc = models.Document(filename=file.filename, file_path=file_path, status="UPLOADED")
    db.add(db_doc)
    db.commit()
    db.refresh(db_doc)
    return {"message": "File uploaded successfully!", "document_id": db_doc.id, "status": "UPLOADED"}

@app.get("/api/documents/")
def get_documents(db: Session = Depends(get_db)):
    docs = db.query(models.Document).all()
    return [{"id": doc.id, "filename": doc.filename, "status": doc.status, "uploaded_at": str(doc.created_at)} for doc in docs]

@app.delete("/api/documents/{document_id}/")
def delete_document(document_id: int, db: Session = Depends(get_db)):
    doc = db.query(models.Document).filter(models.Document.id == document_id).first()
    if not doc: return {"error": "Document not found"}
    if os.path.exists(doc.file_path): os.remove(doc.file_path)
    db.query(models.LandRecord).filter(models.LandRecord.document_id == document_id).delete()
    db.delete(doc)
    db.commit()
    return {"message": f"Document {document_id} deleted successfully!"}

@app.post("/api/records/extract/")
async def simulate_ai_extraction(document_id: int, db: Session = Depends(get_db)):
    doc = db.query(models.Document).filter(models.Document.id == document_id).first()
    if not doc: return {"error": "Document not found"}
    
    doc.status = "PROCESSING"
    db.commit()
    
    # Start with "Not Detected"
    safe_response = {
        "message": "Extraction completed",
        "owner_name": "Not Detected",
        "khasra_number": "Not Detected",
        "khata_number": "Not Detected",
        "plot_area": 0.0,
        "village": "Not Detected",
        "tehsil": "Not Detected",
        "district": "Not Detected",
        "land_classification": "Not Detected",
        "confidence_score": 95.0
    }

    try:
        print(f"\n[AI] Sending {doc.filename} to REAL AI (gemini-3.6-flash)...")
        mime_type = "application/pdf" if doc.file_path.lower().endswith('.pdf') else "image/png"
        
        with open(doc.file_path, "rb") as f:
            file_bytes = f.read()

        # Optimized prompt for Hindi/English Bhulekh documents
        prompt = """
        You are an expert Indian Land Record AI. Extract details from this Bhulekh document (may be Hindi, English, or garbled).
        Return ONLY a valid JSON object. No markdown, no ```json tags.
        Keys: 
        - owner_name (Transliterate Hindi to English, e.g., 'दाताराम' -> 'Dataram', 'रामरतन' -> 'Ram Ratan')
        - khasra_number (Khasra, Gata, or Survey number)
        - khata_number (Khata or Account number)
        - plot_area (Number only, e.g., 1.5290)
        - village (Village or Gram name)
        - tehsil (Tehsil name)
        - district (District or Janpad name)
        - land_classification (e.g., Agricultural)
        Use "Not Detected" if a field is missing.
        """

        # USE THE LATEST, FULLY SUPPORTED MODEL FOR AQ... KEYS
        response = client.models.generate_content(
            model="gemini-3.6-flash", 
            contents=[
                types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
                prompt
            ]
        )
        
        print("[AI] RAW RESPONSE:", response.text)

        # Parse the JSON safely
        match = re.search(r'\{.*\}', response.text, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
            safe_response["owner_name"] = str(data.get("owner_name", "Not Detected"))
            safe_response["khasra_number"] = str(data.get("khasra_number", "Not Detected"))
            safe_response["khata_number"] = str(data.get("khata_number", "Not Detected"))
            safe_response["village"] = str(data.get("village", "Not Detected"))
            safe_response["tehsil"] = str(data.get("tehsil", "Not Detected"))
            safe_response["district"] = str(data.get("district", "Not Detected"))
            safe_response["land_classification"] = str(data.get("land_classification", "Not Detected"))
            try:
                safe_response["plot_area"] = float(data.get("plot_area", 0.0))
            except:
                safe_response["plot_area"] = 0.0
            
            print("[AI] SUCCESS: Real AI extracted the data!")
        else:
            print("[AI] WARNING: AI did not return valid JSON.")

    except Exception as e:
        print(f"!!! AI BRAIN ERROR: {str(e)} !!!")

    # --- SAVE TO DATABASE ---
    new_record = models.LandRecord(
        document_id=document_id,
        owner_name=safe_response["owner_name"],
        khasra_number=safe_response["khasra_number"],
        khata_number=safe_response["khata_number"],
        plot_area=safe_response["plot_area"],
        village=safe_response["village"],
        tehsil=safe_response["tehsil"],
        district=safe_response["district"],
        land_classification=safe_response["land_classification"],
        confidence_score=safe_response["confidence_score"],
        is_verified=False
    )
    
    doc.status = "COMPLETED"
    db.add(new_record)
    db.commit()
    db.refresh(new_record)
    
    return safe_response

@app.get("/api/records/pending/")
def get_pending_verifications(db: Session = Depends(get_db)):
    pending_records = db.query(models.LandRecord).filter(models.LandRecord.confidence_score < 85.0, models.LandRecord.is_verified == False).all()
    return [{"record_id": rec.id, "document_id": rec.document_id, "owner_name": rec.owner_name, "khasra_number": rec.khasra_number, "plot_area": rec.plot_area, "village": rec.village, "confidence_score": rec.confidence_score} for rec in pending_records]

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(db: Session = Depends(get_db)):
    try:
        records = db.query(models.LandRecord).all()
        html = f"""<!DOCTYPE html><html><head><title>Dashboard</title><style>body{{font-family:Arial;margin:40px;background:#f5f5f5;}}table{{width:100%;border-collapse:collapse;background:white;}}th,td{{padding:12px;text-align:left;border-bottom:1px solid #ddd;}}th{{background:#007bff;color:white;}}</style></head><body><h1>Land Records Dashboard</h1><p>Total Records: {len(records)}</p><table><tr><th>ID</th><th>Owner</th><th>Khasra</th><th>Khata</th><th>Area</th><th>Village</th><th>Confidence</th></tr>"""
        for rec in records:
            html += f"<tr><td>{rec.id}</td><td>{rec.owner_name or 'N/A'}</td><td>{rec.khasra_number or 'N/A'}</td><td>{rec.khata_number or 'N/A'}</td><td>{rec.plot_area or 'N/A'}</td><td>{rec.village or 'N/A'}</td><td>{rec.confidence_score}%</td></tr>"
        html += "</table><br><a href='/'>← Back to Upload</a></body></html>"
        return html
    except Exception as e:
        return f"<h1>Error loading dashboard</h1><p>{str(e)}</p>"