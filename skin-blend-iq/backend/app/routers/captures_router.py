from __future__ import annotations

import os
import statistics

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit, config
from ..auth import current_user, tenant_get
from ..colorscience import (
    classify_undertone,
    delta_e_2000,
    ita_degrees,
    lab_to_srgb,
    rgb_to_hsv,
    srgb_to_lab,
)
from ..colorscience.correction import apply_correction, fit_correction
from ..colorscience.quality import patch_statistics, score_image
from ..db import get_db
from ..models import (
    Case,
    CaptureSession,
    ColorMeasurement,
    ImageAsset,
    ReferenceCard,
    SkinPatch,
    User,
)
from ..serialize import to_dict

router = APIRouter(prefix="/v1", tags=["captures"])

MIN_TREATMENT_GRADE_IMAGES = 3
MIN_ACCEPTED_PATCHES = 3
MAX_PATCH_VARIATION_DE = 3.0

REJECT_REASONS = {
    "glare", "shadow", "hair", "redness", "scar_tissue", "bruising",
    "tattoo_ink", "background", "outlier", "other",
}


class CaptureIn(BaseModel):
    case_id: str
    zone_id: str | None = None
    mode: str = Field(default="calibrated", pattern="^(quick|calibrated|instrument)$")
    reference_card_id: str | None = None


class CardPatchesIn(BaseModel):
    # Rectangles over the card patches, in card order: {x, y, w, h}
    patches: list[dict]


class SkinPatchesIn(BaseModel):
    patches: list[dict]


class RejectIn(BaseModel):
    reason: str


class ManualMeasurementIn(BaseModel):
    lab: list[float] = Field(min_length=3, max_length=3)
    source_type: str = Field(default="manual", pattern="^(manual|instrument)$")
    uncertainty: float | None = None
    capture_id: str | None = None


def _image_dir() -> str:
    os.makedirs(config.UPLOAD_DIR, exist_ok=True)
    return config.UPLOAD_DIR


def _measurement_from_lab(
    tenant_id: str,
    lab: tuple[float, float, float],
    source_type: str,
    treatment_grade: bool,
    uncertainty: float | None,
    capture_id: str | None = None,
    detail: dict | None = None,
) -> ColorMeasurement:
    rgb = lab_to_srgb(lab)
    undertone, conf = classify_undertone(lab)
    ita = ita_degrees(lab)
    return ColorMeasurement(
        tenant_id=tenant_id,
        capture_id=capture_id,
        source_type=source_type,
        lab_l=round(lab[0], 3),
        lab_a=round(lab[1], 3),
        lab_b=round(lab[2], 3),
        rgb_display=[round(v, 1) for v in rgb],
        hsv=[round(v, 4) for v in rgb_to_hsv(rgb)],
        ita_degrees=round(ita, 3) if ita is not None else None,
        undertone=undertone,
        undertone_confidence=conf,
        delta_e_uncertainty=uncertainty,
        treatment_grade=treatment_grade,
        detail=detail,
    )


@router.get("/reference-cards")
def list_reference_cards(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(ReferenceCard)).scalars().all()
    return [to_dict(r) for r in rows]


@router.post("/captures", status_code=201)
def create_capture(body: CaptureIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    tenant_get(db, Case, body.case_id, user.tenant_id, "case")
    if body.mode == "calibrated" and not body.reference_card_id:
        raise HTTPException(status_code=422, detail="Calibrated capture requires a reference card")
    if body.reference_card_id and db.get(ReferenceCard, body.reference_card_id) is None:
        raise HTTPException(status_code=404, detail="reference card not found")
    cap = CaptureSession(tenant_id=user.tenant_id, created_by=user.id, **body.model_dump())
    db.add(cap)
    db.flush()
    audit.record(db, user.tenant_id, "capture.created", "capture_session", cap.id, user.id,
                 {"mode": body.mode})
    db.commit()
    return to_dict(cap)


@router.get("/captures/{capture_id}")
def get_capture(capture_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    cap = tenant_get(db, CaptureSession, capture_id, user.tenant_id, "capture")
    images = db.execute(
        select(ImageAsset).where(ImageAsset.capture_id == cap.id)
    ).scalars().all()
    out = to_dict(cap)
    out["images"] = []
    for img in images:
        d = to_dict(img, exclude=("stored_path",))
        patches = db.execute(select(SkinPatch).where(SkinPatch.image_id == img.id)).scalars().all()
        d["skin_patches"] = [to_dict(p) for p in patches]
        out["images"].append(d)
    return out


@router.post("/captures/{capture_id}/images", status_code=201)
async def upload_image(
    capture_id: str,
    file: UploadFile = File(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    cap = tenant_get(db, CaptureSession, capture_id, user.tenant_id, "capture")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="Empty file")
    try:
        quality = score_image(data)
    except Exception:
        raise HTTPException(status_code=422, detail="Not a readable image")

    img = ImageAsset(
        tenant_id=user.tenant_id,
        capture_id=cap.id,
        filename=file.filename or "capture.png",
        stored_path="",
        width=quality["width"],
        height=quality["height"],
        quality=quality,
        grade=quality["grade"],
    )
    db.add(img)
    db.flush()
    path = os.path.join(_image_dir(), f"{img.id}.png")
    from PIL import Image
    from io import BytesIO

    Image.open(BytesIO(data)).convert("RGB").save(path, "PNG")
    img.stored_path = path
    db.add(img)
    audit.record(db, user.tenant_id, "capture.image_uploaded", "image_asset", img.id, user.id,
                 {"grade": quality["grade"], "failures": quality["failures"]})
    db.commit()
    return to_dict(img, exclude=("stored_path",))


@router.get("/images/{image_id}/file")
def image_file(image_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    img = tenant_get(db, ImageAsset, image_id, user.tenant_id, "image")
    if not img.stored_path or not os.path.exists(img.stored_path):
        raise HTTPException(status_code=404, detail="image file missing")
    return FileResponse(img.stored_path, media_type="image/png")


@router.post("/images/{image_id}/card-patches")
def mark_card_patches(
    image_id: str, body: CardPatchesIn, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    """Mark the reference-card patches; fits and stores the color correction."""
    img = tenant_get(db, ImageAsset, image_id, user.tenant_id, "image")
    cap = tenant_get(db, CaptureSession, img.capture_id, user.tenant_id, "capture")
    if not cap.reference_card_id:
        raise HTTPException(status_code=422, detail="Capture session has no reference card")
    card = db.get(ReferenceCard, cap.reference_card_id)
    if len(body.patches) != len(card.patches):
        raise HTTPException(
            status_code=422,
            detail=f"Card '{card.name}' has {len(card.patches)} patches; got {len(body.patches)}",
        )
    with open(img.stored_path, "rb") as f:
        data = f.read()
    stats = patch_statistics(data, body.patches)
    if any(s["pixel_count"] == 0 for s in stats):
        raise HTTPException(status_code=422, detail="A card patch rectangle is outside the image")
    observed = [s["median_rgb"] for s in stats]
    reference = [p["lab"] for p in card.patches]
    fit = fit_correction(observed, reference)
    img.card_patches = body.patches
    img.correction_matrix = fit["matrix"]
    img.correction_residual = fit["residual_delta_e00"]
    img.correction_passed = fit["passed"]
    db.add(img)
    audit.record(db, user.tenant_id, "capture.correction_fitted", "image_asset", img.id, user.id,
                 {"residual_delta_e00": fit["residual_delta_e00"], "passed": fit["passed"]})
    db.commit()
    return {
        "image_id": img.id,
        "residual_delta_e00": fit["residual_delta_e00"],
        "passed": fit["passed"],
    }


@router.post("/images/{image_id}/skin-patches", status_code=201)
def add_skin_patches(
    image_id: str, body: SkinPatchesIn, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    img = tenant_get(db, ImageAsset, image_id, user.tenant_id, "image")
    if not body.patches:
        raise HTTPException(status_code=422, detail="No patches provided")
    with open(img.stored_path, "rb") as f:
        data = f.read()
    stats = patch_statistics(data, body.patches)
    created = []
    for geom, s in zip(body.patches, stats):
        if s["pixel_count"] == 0:
            raise HTTPException(status_code=422, detail="Patch rectangle outside the image")
        rgb = s["median_rgb"]
        corrected = apply_correction(rgb, img.correction_matrix) if img.correction_matrix else rgb
        lab = srgb_to_lab(tuple(corrected))
        patch = SkinPatch(
            tenant_id=user.tenant_id,
            image_id=img.id,
            geometry={k: geom[k] for k in ("x", "y", "w", "h")},
            pixel_count=s["pixel_count"],
            median_rgb=rgb,
            corrected_rgb=corrected,
            lab=[round(v, 3) for v in lab],
            spread=s["spread"],
        )
        db.add(patch)
        db.flush()
        created.append(to_dict(patch))
    audit.record(db, user.tenant_id, "capture.patches_added", "image_asset", img.id, user.id,
                 {"count": len(created)})
    db.commit()
    return created


@router.post("/patches/{patch_id}/reject")
def reject_patch(
    patch_id: str, body: RejectIn, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    if body.reason not in REJECT_REASONS:
        raise HTTPException(status_code=422, detail=f"reason must be one of {sorted(REJECT_REASONS)}")
    patch = tenant_get(db, SkinPatch, patch_id, user.tenant_id, "patch")
    patch.rejected = True
    patch.reject_reason = body.reason
    db.add(patch)
    audit.record(db, user.tenant_id, "capture.patch_rejected", "skin_patch", patch.id, user.id,
                 {"reason": body.reason})
    db.commit()
    return to_dict(patch)


@router.post("/captures/{capture_id}/analyze")
def analyze_capture(capture_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Compute the representative target color across accepted patches.

    Treatment-grade requires: calibrated mode, >=3 pass-grade images all
    with a passing card correction, >=3 accepted patches, and patch
    variation within tolerance (spec sections 6-7).
    """
    cap = tenant_get(db, CaptureSession, capture_id, user.tenant_id, "capture")
    images = db.execute(select(ImageAsset).where(ImageAsset.capture_id == cap.id)).scalars().all()
    if not images:
        raise HTTPException(status_code=422, detail="No images uploaded")

    patches: list[SkinPatch] = []
    for img in images:
        patches += db.execute(
            select(SkinPatch).where(SkinPatch.image_id == img.id, SkinPatch.rejected == False)  # noqa: E712
        ).scalars().all()
    if not patches:
        raise HTTPException(status_code=422, detail="No accepted skin patches")

    labs = [tuple(p.lab) for p in patches]
    median_lab = tuple(statistics.median(v[i] for v in labs) for i in range(3))
    variation = [delta_e_2000(lab, median_lab) for lab in labs]
    uncertainty = round(statistics.median(variation) if len(variation) > 1 else 0.5, 3)
    excessive_variation = max(variation) > MAX_PATCH_VARIATION_DE if len(variation) > 1 else False

    gates = {
        "mode_calibrated": cap.mode in ("calibrated", "instrument"),
        "enough_pass_images": sum(1 for i in images if i.grade == "pass") >= MIN_TREATMENT_GRADE_IMAGES,
        "all_corrections_passed": all(bool(i.correction_passed) for i in images if i.grade == "pass")
        and any(i.correction_passed for i in images),
        "enough_patches": len(patches) >= MIN_ACCEPTED_PATCHES,
        "variation_ok": not excessive_variation,
    }
    if cap.mode == "instrument":
        gates["all_corrections_passed"] = True
        gates["enough_pass_images"] = True
    treatment_grade = all(gates.values())

    m = _measurement_from_lab(
        user.tenant_id,
        median_lab,
        source_type="capture",
        treatment_grade=treatment_grade,
        uncertainty=uncertainty,
        capture_id=cap.id,
        detail={
            "gates": gates,
            "patch_count": len(patches),
            "max_patch_delta_e00": round(max(variation), 3) if variation else 0.0,
            "image_grades": [i.grade for i in images],
            "correction_residuals": [i.correction_residual for i in images],
        },
    )
    db.add(m)
    db.flush()
    cap.status = "analyzed"
    db.add(cap)
    audit.record(db, user.tenant_id, "capture.analyzed", "color_measurement", m.id, user.id,
                 {"treatment_grade": treatment_grade, "gates": gates})
    db.commit()
    out = to_dict(m)
    out["warnings"] = [] if treatment_grade else [
        f"Not treatment-grade: failed gates {[k for k, v in gates.items() if not v]}"
    ]
    return out


@router.post("/measurements/manual", status_code=201)
def manual_measurement(
    body: ManualMeasurementIn, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    """Quick-mode or instrument L*a*b* entry.

    Manual entries are never treatment-grade; instrument entries are
    (calibrated instruments bypass camera correction).
    """
    m = _measurement_from_lab(
        user.tenant_id,
        tuple(body.lab),
        source_type=body.source_type,
        treatment_grade=body.source_type == "instrument",
        uncertainty=body.uncertainty,
        capture_id=body.capture_id,
    )
    db.add(m)
    db.flush()
    audit.record(db, user.tenant_id, "measurement.manual", "color_measurement", m.id, user.id,
                 {"source_type": body.source_type})
    db.commit()
    return to_dict(m)


@router.get("/measurements/{measurement_id}")
def get_measurement(measurement_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    m = tenant_get(db, ColorMeasurement, measurement_id, user.tenant_id, "measurement")
    return to_dict(m)
