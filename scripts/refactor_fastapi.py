import re

def update_fastapi():
    with open("src/agentic_poc/application/fastapi_app.py", "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Update ALLOWED_MIME_TYPES
    content = content.replace(
        "\"application/pdf\": \"pdf\"",
        "\"application/pdf\": \"pdf\",\n    \"image/jpeg\": \"jpg\",\n    \"image/png\": \"png\""
    )

    # 2. Update FileUploadResponse
    content = content.replace(
        "class FileUploadResponse(BaseModel):\n    file_id: str\n    message: str",
        "class FileUploadResponse(BaseModel):\n    file_ids: List[str]\n    message: str"
    )

    # 3. Update StartRequest
    content = content.replace(
        "source_file_id: Optional[str] = Field(None,",
        "source_file_ids: Optional[List[str]] = Field(default_factory=list,"
    )

    # 4. Update api_upload_file
    upload_logic = """
@app.post("/workflows/upload", response_model=FileUploadResponse, status_code=201)
@limiter.limit("10/minute")
async def api_upload_file(request: Request, files: List[UploadFile] = File(...), user: str = Depends(verify_token)):
    uploaded_ids = []
    
    uploads_dir = pathlib.Path("./artifacts/uploads")
    uploads_dir.mkdir(parents=True, exist_ok=True)
    
    import re
    import hashlib
    
    for file in files:
        ext = file.filename.lower()
        if file.content_type not in ALLOWED_MIME_TYPES:
            raise HTTPException(status_code=400, detail=f"Invalid MIME type for {file.filename}.")
            
        is_valid_ext = any(ext.endswith(allowed) for allowed in [".xlsx", ".csv", ".pdf", ".jpg", ".jpeg", ".png"])
        if not is_valid_ext:
            raise HTTPException(status_code=400, detail=f"Invalid extension for {file.filename}.")
        
        file_id = f"upl_{uuid.uuid4()}"
        safe_name = pathlib.Path(file.filename).name
        safe_name = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', safe_name)
        stored_path = uploads_dir / f"{file_id}_{safe_name}"
        
        content = await file.read()
        size_bytes = len(content)
        if size_bytes > MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail=f"File {file.filename} exceeds {int(MAX_FILE_SIZE/(1024*1024))}MB limit.")
            
        file_hash = hashlib.sha256(content).hexdigest()
        
        # Check dupe
        existing_file = await get_file_by_hash(file_hash, user)
        if existing_file:
            await touch_file_last_used(existing_file['file_id'])
            uploaded_ids.append(existing_file['file_id'])
            continue
            
        with open(stored_path, "wb") as f:
            f.write(content)
            
        await register_file_metadata(
            file_id=file_id,
            owner_id=user,
            stored_path=str(stored_path),
            original_filename=file.filename,
            size_bytes=size_bytes,
            content_type=file.content_type,
            file_hash=file_hash
        )
        uploaded_ids.append(file_id)

    return {"file_ids": uploaded_ids, "message": f"Successfully uploaded {len(uploaded_ids)} files."}
"""
    # Use re.sub to replace the old api_upload_file
    content = re.sub(
        r'@app\.post\("/workflows/upload".*?return \{"file_id": file_id, "message": "File uploaded successfully"\}',
        upload_logic.strip(),
        content,
        flags=re.DOTALL
    )

    # 5. Update api_start_workflow
    # Replace req.source_file_id checks with req.source_file_ids array handling
    content = content.replace("if req.source_file_id:", "if req.source_file_ids:")
    content = content.replace("f_meta = await get_file_metadata(req.source_file_id)", "f_metas = [await get_file_metadata(fid) for fid in req.source_file_ids]")
    content = content.replace("if not f_meta:", "if not all(f_metas):")
    content = content.replace("if f_meta[\"owner_id\"] != user:", "if any(f[\"owner_id\"] != user for f in f_metas if f):")
    content = content.replace("await touch_file_last_used(req.source_file_id)", "[await touch_file_last_used(fid) for fid in req.source_file_ids]")
    content = content.replace("source_file_id=req.source_file_id if req.source_file_id else \"\"", "source_file_ids=req.source_file_ids if req.source_file_ids else []")
    content = content.replace("req.source_file_id, req.process_family_override", "req.source_file_ids, req.process_family_override")

    with open("src/agentic_poc/application/fastapi_app.py", "w", encoding="utf-8") as f:
        f.write(content)

    print("Updated fastapi_app.py!")

if __name__ == "__main__":
    update_fastapi()
