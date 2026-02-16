
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import FetchJob, Company

router = APIRouter(prefix='/jobs', tags=['jobs'])

@router.post('/{company_id}')
async def set_job(company_id: int, schedule: str = 'daily', db: Session = Depends(get_db)):
    if schedule not in ('daily','weekly'):
        raise HTTPException(status_code=400, detail='Invalid schedule')
    c = db.query(Company).get(company_id)
    if not c:
        raise HTTPException(status_code=404, detail='Company not found')
    job = db.query(FetchJob).filter(FetchJob.company_id==company_id).first()
    if not job:
        job = FetchJob(company_id=company_id, schedule=schedule)
        db.add(job)
    else:
        job.schedule = schedule
    db.commit()
    return {'message':'Scheduled', 'schedule': schedule}
