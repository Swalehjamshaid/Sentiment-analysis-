
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import SuggestedReply

router = APIRouter(prefix='/replies', tags=['replies'])

@router.get('/{review_id}')
async def get_reply(review_id: int, db: Session = Depends(get_db)):
    sr = db.query(SuggestedReply).filter(SuggestedReply.review_id == review_id).first()
    if not sr:
        raise HTTPException(status_code=404, detail='Not found')
    return {'suggested_text': sr.suggested_text, 'user_edited_text': sr.user_edited_text, 'status': sr.status}

@router.post('/{review_id}')
async def update_reply(review_id: int, text: str, db: Session = Depends(get_db)):
    if len(text) > 500:
        raise HTTPException(status_code=400, detail='Max 500 chars')
    sr = db.query(SuggestedReply).filter(SuggestedReply.review_id == review_id).first()
    if not sr:
        raise HTTPException(status_code=404, detail='Not found')
    sr.user_edited_text = text
    db.commit()
    return {'message': 'Updated'}
