from datetime import datetime
from fastapi import APIRouter, Request, Form, File, UploadFile, Depends, HTTPException
from fastapi.responses import RedirectResponse, Response, FileResponse
from sqlalchemy import select, or_
from sqlalchemy.orm import Session, joinedload
from ..db import get_db
from ..models import User, Property, RepairCase, Evidence, Notice, PaymentRecord, AuditEvent
from ..deps import current_user, require_user
from ..services.legal import compute_deadline, render_notice, load_rules
from ..services.evidence import store_upload
from ..services.pdf import notice_pdf
from ..services.payments import create_hold, PaymentComplianceError
from ..services.audit import log
from ..config import settings

router = APIRouter()

def tmpl(request): return request.app.state.templates

def case_for_user(db, case_id, user):
    case = db.scalar(select(RepairCase).options(joinedload(RepairCase.property).joinedload(Property.tenant), joinedload(RepairCase.property).joinedload(Property.landlord)).where(RepairCase.id==case_id))
    if not case or user.id not in {case.property.tenant_id, case.property.landlord_id}:
        raise HTTPException(404, "Case not found")
    return case

@router.get("/")
def home(request: Request, db: Session=Depends(get_db)):
    return tmpl(request).TemplateResponse(request, "home.html", {"user":current_user(request, db)})

@router.get("/dashboard")
def dashboard(request: Request, db: Session=Depends(get_db)):
    user = require_user(request, db)
    props = db.scalars(select(Property).where(or_(Property.tenant_id==user.id, Property.landlord_id==user.id))).all()
    prop_ids = [p.id for p in props]
    cases = db.scalars(select(RepairCase).where(RepairCase.property_id.in_(prop_ids)).order_by(RepairCase.created_at.desc())).all() if prop_ids else []
    return tmpl(request).TemplateResponse(request, "dashboard.html", {"user":user,"properties":props,"cases":cases})

@router.get("/properties/new")
def property_page(request: Request, db: Session=Depends(get_db)):
    user = require_user(request, db)
    others = db.scalars(select(User).where(User.role != user.role).order_by(User.full_name)).all()
    return tmpl(request).TemplateResponse(request, "property_new.html", {"user":user,"others":others})

@router.post("/properties/new")
def property_create(request: Request, address: str=Form(...), counterpart_id: int=Form(...), jurisdiction: str=Form("DEMO"), db: Session=Depends(get_db)):
    user = require_user(request, db); other = db.get(User, counterpart_id)
    if not other or other.role == user.role: raise HTTPException(400,"Choose the opposite party role")
    tenant_id = user.id if user.role=="tenant" else other.id
    landlord_id = user.id if user.role=="landlord" else other.id
    p=Property(address=address.strip(), jurisdiction=jurisdiction.strip() or "DEMO", tenant_id=tenant_id, landlord_id=landlord_id)
    db.add(p); db.commit(); return RedirectResponse("/dashboard",303)

@router.get("/cases/new")
def case_page(request: Request, db: Session=Depends(get_db)):
    user=require_user(request, db)
    props=db.scalars(select(Property).where(Property.tenant_id==user.id)).all()
    return tmpl(request).TemplateResponse(request,"case_new.html",{"user":user,"properties":props})

@router.post("/cases/new")
def case_create(request: Request, property_id:int=Form(...), title:str=Form(...), description:str=Form(...), category:str=Form("general"), severity:str=Form("standard"), db:Session=Depends(get_db)):
    user=require_user(request,db); p=db.get(Property,property_id)
    if not p or p.tenant_id!=user.id: raise HTTPException(403,"Only the tenant can open a repair case for this property")
    if severity not in {"emergency","urgent","standard"}: severity="standard"
    c=RepairCase(property_id=p.id,created_by_id=user.id,title=title.strip(),description=description.strip(),category=category.strip(),severity=severity)
    db.add(c); db.flush(); c.deadline_at=compute_deadline(severity,c.created_at); log(db,"case.created",user.id,c.id,f"severity={severity}"); db.commit()
    return RedirectResponse(f"/cases/{c.id}",303)

@router.get("/cases/{case_id}")
def case_detail(case_id:int, request:Request, db:Session=Depends(get_db)):
    user=require_user(request,db); c=case_for_user(db,case_id,user)
    notices=db.scalars(select(Notice).where(Notice.case_id==case_id).order_by(Notice.created_at.desc())).all()
    payments=db.scalars(select(PaymentRecord).where(PaymentRecord.case_id==case_id).order_by(PaymentRecord.created_at.desc())).all()
    audits=db.scalars(select(AuditEvent).where(AuditEvent.case_id==case_id).order_by(AuditEvent.created_at.desc())).all()
    rules=load_rules()
    return tmpl(request).TemplateResponse(request,"case_detail.html",{"user":user,"case":c,"notices":notices,"payments":payments,"audits":audits,"rules":rules})

@router.post("/cases/{case_id}/evidence")
async def evidence_upload(case_id:int, request:Request, file:UploadFile=File(...), note:str=Form(""), latitude:float|None=Form(None), longitude:float|None=Form(None), captured_at:str=Form(""), db:Session=Depends(get_db)):
    user=require_user(request,db); c=case_for_user(db,case_id,user)
    try: storage,digest,_=await store_upload(file)
    except ValueError as e: raise HTTPException(400,str(e))
    captured=None
    if captured_at:
        try: captured=datetime.fromisoformat(captured_at.replace("Z","+00:00"))
        except ValueError: pass
    e=Evidence(case_id=c.id,uploaded_by_id=user.id,original_name=file.filename or "evidence",storage_name=storage,mime_type=file.content_type or "application/octet-stream",sha256=digest,latitude=latitude,longitude=longitude,note=note,captured_at=captured)
    db.add(e); log(db,"evidence.uploaded",user.id,c.id,f"sha256={digest}"); db.commit(); return RedirectResponse(f"/cases/{case_id}",303)

@router.get("/evidence/{evidence_id}/file")
def evidence_file(evidence_id:int, request:Request, db:Session=Depends(get_db)):
    user=require_user(request,db); e=db.get(Evidence,evidence_id)
    if not e: raise HTTPException(404)
    case_for_user(db,e.case_id,user)
    return FileResponse(settings.upload_path/e.storage_name, media_type=e.mime_type, filename=e.original_name)

@router.post("/cases/{case_id}/complete")
def complete_case(case_id:int, request:Request, db:Session=Depends(get_db)):
    user=require_user(request,db); c=case_for_user(db,case_id,user)
    c.status="completed"; c.completed_at=datetime.now().astimezone(); log(db,"case.completed",user.id,c.id,"Marked complete by participant"); db.commit(); return RedirectResponse(f"/cases/{case_id}",303)

@router.post("/cases/{case_id}/notice")
def generate_notice(case_id:int, request:Request, db:Session=Depends(get_db)):
    user=require_user(request,db); c=case_for_user(db,case_id,user); body,version,_=render_notice(c)
    n=Notice(case_id=c.id,generated_by_id=user.id,body=body,ruleset_version=version)
    db.add(n); log(db,"notice.generated",user.id,c.id,version); db.commit(); return RedirectResponse(f"/cases/{case_id}",303)

@router.get("/notices/{notice_id}.pdf")
def notice_download(notice_id:int, request:Request, db:Session=Depends(get_db)):
    user=require_user(request,db); n=db.get(Notice,notice_id)
    if not n: raise HTTPException(404)
    case_for_user(db,n.case_id,user)
    return Response(notice_pdf("Repair Request Follow-Up Notice",n.body),media_type="application/pdf",headers={"Content-Disposition":f'attachment; filename="notice-{notice_id}.pdf"'})

@router.post("/cases/{case_id}/payment")
def payment_demo(case_id:int, request:Request, amount:float=Form(...), currency:str=Form("USD"), db:Session=Depends(get_db)):
    user=require_user(request,db); c=case_for_user(db,case_id,user)
    if user.id!=c.property.tenant_id: raise HTTPException(403,"Only the tenant can create a rent-funds record")
    cents=round(amount*100)
    try: result=create_hold(cents,currency.upper(),case_id)
    except (ValueError,PaymentComplianceError) as e: raise HTTPException(400,str(e))
    p=PaymentRecord(case_id=c.id,payer_id=user.id,amount_cents=cents,currency=currency.upper(),status=result.status,provider=result.provider,external_reference=result.external_reference,is_real_funds=result.is_real_funds)
    db.add(p); log(db,"payment.record_created",user.id,c.id,f"provider={result.provider}; real_funds={result.is_real_funds}"); db.commit(); return RedirectResponse(f"/cases/{case_id}",303)
