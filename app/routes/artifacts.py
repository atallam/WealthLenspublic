"""
WealthLens OSS — Artifact Routes (encrypted file storage)
POST   /api/artifacts/upload   — upload file (encrypted)
GET    /api/artifacts/{id}     — download file (decrypted)
DELETE /api/artifacts/{id}     — delete artifact
"""

import base64
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user, AuthContext
from app.models import Holding, Artifact
from app.encryption import encrypt_json, decrypt_json, encrypt_field, decrypt_field
from fastapi.responses import Response

router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])


@router.post("/upload", status_code=201)
async def upload_artifact(
    holding_id: str = Form(...),
    description: str = Form(""),
    file: UploadFile = File(...),
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Verify holding ownership
    holding = (
        db.query(Holding)
        .filter(Holding.id == holding_id, Holding.user_id == auth.user_id)
        .first()
    )
    if not holding:
        raise HTTPException(status_code=404, detail="Holding not found")

    # Read file and encrypt
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:  # 10MB limit
        raise HTTPException(status_code=413, detail="File too large (max 10MB)")

    content_b64 = base64.b64encode(content).decode()
    encrypted_file = encrypt_field(content_b64, auth.dek)

    meta = {"filename": file.filename, "description": description}

    artifact = Artifact(
        holding_id=holding_id,
        user_id=auth.user_id,
        encrypted_meta=encrypt_json(meta, auth.dek),
        encrypted_file=encrypted_file,
    )
    db.add(artifact)
    db.commit()
    db.refresh(artifact)

    return {"id": artifact.id, "holding_id": holding_id, **meta}


@router.get("/{artifact_id}")
async def download_artifact(
    artifact_id: str,
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    artifact = (
        db.query(Artifact)
        .filter(Artifact.id == artifact_id, Artifact.user_id == auth.user_id)
        .first()
    )
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")

    meta = decrypt_json(artifact.encrypted_meta, auth.dek)
    content_b64 = decrypt_field(artifact.encrypted_file, auth.dek)
    content = base64.b64decode(content_b64)

    filename = meta.get("filename", "download")
    return Response(
        content=content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/{artifact_id}")
async def delete_artifact(
    artifact_id: str,
    auth: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    artifact = (
        db.query(Artifact)
        .filter(Artifact.id == artifact_id, Artifact.user_id == auth.user_id)
        .first()
    )
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")

    db.delete(artifact)
    db.commit()
    return {"message": "Artifact deleted"}
