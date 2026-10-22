from datetime import timedelta
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import delete, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from interviews.repository import digest, now
from interviews.tables import RateBucket
from .schemas import Review, ReviewHistory, ReviewSummary
from .tables import CvReview


class CvRepository:
    # Shared private-analysis persistence; defaults preserve the CV contract.
    record_type = CvReview
    summary_type = ReviewSummary
    view_type = Review
    history_type = ReviewHistory
    rate_namespace = "cv"
    label = "CV review"

    def __init__(self, engine):
        self.engine = engine

    def _owned(self, db, review_id, owner, lock=False):
        query = select(self.record_type).where(self.record_type.id == review_id,
            self.record_type.owner_hash == digest(owner), self.record_type.expires_at > now())
        row = db.scalar(query.with_for_update() if lock else query)
        if row is None:
            raise HTTPException(404, f"{self.label} not found or expired.")
        return row

    @classmethod
    def _view(cls,row):
        return cls.view_type(**{key:getattr(row,key) for key in cls.summary_type.model_fields}, analysis=row.analysis)

    @classmethod
    def _rate(cls, db, key, limit):
        statement = insert(RateBucket).values(key=key, window_start=now().replace(minute=0,second=0,microsecond=0), count=1)
        count = db.scalar(statement.on_conflict_do_update(index_elements=[RateBucket.key,RateBucket.window_start],
            set_={"count":RateBucket.count+1}).returning(RateBucket.count))
        if count > limit:
            raise HTTPException(429, f"{cls.label} limit reached. Try again later.", headers={"Retry-After":"3600"})

    def claim(self, review_id, owner, request_hash, job_role, source, characters, pages):
        with Session(self.engine) as db, db.begin():
            created = db.scalar(insert(self.record_type).values(id=review_id,owner_hash=digest(owner),request_hash=request_hash,
                job_role=job_role,source=source,status="failed",character_count=characters,page_count=pages,
                created_at=now(),expires_at=now()+timedelta(days=7)).on_conflict_do_nothing(
                    index_elements=[self.record_type.id]).returning(self.record_type.id))
            row = self._owned(db,review_id,owner,lock=True)
            if row.request_hash != request_hash:
                raise HTTPException(409, "This request ID belongs to different content. Start a new review for edited inputs.")
            if row.status == "finished":
                return self._view(row), None
            if row.status == "processing" and row.lease_until and row.lease_until > now():
                raise HTTPException(409, "This review is still processing. Wait, then retry the same action.", headers={"Retry-After":"3"})
            if created:
                self._rate(db,self.rate_namespace+":starts:"+digest(owner),10)
                self._rate(db,self.rate_namespace+":starts:global",100)
            self._rate(db,self.rate_namespace+":attempts:"+digest(owner),20)
            self._rate(db,self.rate_namespace+":attempts:global",200)
            row.status, row.fence, row.lease_until = "processing", uuid4(), now()+timedelta(seconds=100)
            return self._view(row), row.fence

    def complete(self, review_id, owner, fence, analysis):
        with Session(self.engine) as db, db.begin():
            row = self._owned(db,review_id,owner,lock=True)
            if row.fence != fence or row.status != "processing":
                raise HTTPException(409,"A newer request owns this review. Refresh its saved result.")
            row.analysis, row.status = analysis.model_dump(mode="json"), "finished"
            row.fence = row.lease_until = None
            return self._view(row)

    def release(self, review_id, owner, fence):
        with Session(self.engine) as db, db.begin():
            # Deletion while AI was working must not recreate personal data.
            row = db.scalar(select(self.record_type).where(self.record_type.id==review_id,
                self.record_type.owner_hash==digest(owner)).with_for_update())
            if row and row.fence == fence:
                row.status = "failed"; row.fence = row.lease_until = None

    def read(self, review_id, owner):
        with Session(self.engine) as db:
            return self._view(self._owned(db,review_id,owner))

    def history(self, owner, limit=10, cursor=None):
        with Session(self.engine) as db, db.begin():
            query = select(self.record_type).where(self.record_type.owner_hash==digest(owner),self.record_type.expires_at>now())
            if cursor:
                last = self._owned(db,cursor,owner)
                query = query.where(tuple_(self.record_type.created_at,self.record_type.id) < tuple_(last.created_at,last.id))
            rows = db.scalars(query.order_by(self.record_type.created_at.desc(),self.record_type.id.desc()).limit(limit+1)).all()
            return self.history_type(items=[self.summary_type(**self._view(row).model_dump(include=set(self.summary_type.model_fields)))
                for row in rows[:limit]], next_cursor=rows[limit-1].id if len(rows)>limit else None)

    def remove(self, review_id, owner):
        with Session(self.engine) as db, db.begin():
            db.delete(self._owned(db,review_id,owner,lock=True))

    def cleanup(self):
        with Session(self.engine) as db, db.begin():
            db.execute(delete(self.record_type).where(self.record_type.expires_at<=now()))
