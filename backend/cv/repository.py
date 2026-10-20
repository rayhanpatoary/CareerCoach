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
    def __init__(self, engine):
        self.engine = engine

    def _owned(self, db, review_id, owner, lock=False):
        query = select(CvReview).where(CvReview.id == review_id,
            CvReview.owner_hash == digest(owner), CvReview.expires_at > now())
        row = db.scalar(query.with_for_update() if lock else query)
        if row is None:
            raise HTTPException(404, "CV review not found or expired.")
        return row

    @staticmethod
    def _view(row):
        return Review(**{key:getattr(row,key) for key in ReviewSummary.model_fields}, analysis=row.analysis)

    @staticmethod
    def _rate(db, key, limit):
        statement = insert(RateBucket).values(key=key, window_start=now().replace(minute=0,second=0,microsecond=0), count=1)
        count = db.scalar(statement.on_conflict_do_update(index_elements=[RateBucket.key,RateBucket.window_start],
            set_={"count":RateBucket.count+1}).returning(RateBucket.count))
        if count > limit:
            raise HTTPException(429, "CV review limit reached. Try again later.", headers={"Retry-After":"3600"})

    def claim(self, review_id, owner, request_hash, job_role, source, characters, pages):
        with Session(self.engine) as db, db.begin():
            created = db.scalar(insert(CvReview).values(id=review_id,owner_hash=digest(owner),request_hash=request_hash,
                job_role=job_role,source=source,status="failed",character_count=characters,page_count=pages,
                created_at=now(),expires_at=now()+timedelta(days=7)).on_conflict_do_nothing(
                    index_elements=[CvReview.id]).returning(CvReview.id))
            row = self._owned(db,review_id,owner,lock=True)
            if row.request_hash != request_hash:
                raise HTTPException(409, "This request ID belongs to different content. Start a new review for edited inputs.")
            if row.status == "finished":
                return self._view(row), None
            if row.status == "processing" and row.lease_until and row.lease_until > now():
                raise HTTPException(409, "This review is still processing. Wait, then retry the same action.", headers={"Retry-After":"3"})
            if created:
                self._rate(db,"cv:starts:"+digest(owner),10)
                self._rate(db,"cv:starts:global",100)
            self._rate(db,"cv:attempts:"+digest(owner),20)
            self._rate(db,"cv:attempts:global",200)
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
            row = db.scalar(select(CvReview).where(CvReview.id==review_id,
                CvReview.owner_hash==digest(owner)).with_for_update())
            if row and row.fence == fence:
                row.status = "failed"; row.fence = row.lease_until = None

    def read(self, review_id, owner):
        with Session(self.engine) as db:
            return self._view(self._owned(db,review_id,owner))

    def history(self, owner, limit=10, cursor=None):
        with Session(self.engine) as db, db.begin():
            query = select(CvReview).where(CvReview.owner_hash==digest(owner),CvReview.expires_at>now())
            if cursor:
                last = self._owned(db,cursor,owner)
                query = query.where(tuple_(CvReview.created_at,CvReview.id) < tuple_(last.created_at,last.id))
            rows = db.scalars(query.order_by(CvReview.created_at.desc(),CvReview.id.desc()).limit(limit+1)).all()
            return ReviewHistory(items=[ReviewSummary(**self._view(row).model_dump(include=set(ReviewSummary.model_fields)))
                for row in rows[:limit]], next_cursor=rows[limit-1].id if len(rows)>limit else None)

    def remove(self, review_id, owner):
        with Session(self.engine) as db, db.begin():
            db.delete(self._owned(db,review_id,owner,lock=True))

    def cleanup(self):
        with Session(self.engine) as db, db.begin():
            db.execute(delete(CvReview).where(CvReview.expires_at<=now()))
