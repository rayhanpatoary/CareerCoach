from datetime import datetime
from uuid import UUID
from sqlalchemy import CheckConstraint,DateTime,Integer,String,Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped,mapped_column
from interviews.tables import Base,SCHEMA


class JobFitRecord(Base):
    __tablename__="job_fit_analyses"
    __table_args__=(CheckConstraint("status IN ('processing','failed','finished')"),
        CheckConstraint("source IN ('pdf','text')"),{"schema":SCHEMA})
    id:Mapped[UUID]=mapped_column(Uuid,primary_key=True)
    owner_hash:Mapped[str]=mapped_column(String(64),index=True)
    request_hash:Mapped[str]=mapped_column(String(64))
    job_role:Mapped[str]=mapped_column(String(100))
    source:Mapped[str]=mapped_column(String(8))
    status:Mapped[str]=mapped_column(String(16))
    character_count:Mapped[int]=mapped_column(Integer)
    page_count:Mapped[int|None]=mapped_column(Integer)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True))
    expires_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),index=True)
    lease_until:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    fence:Mapped[UUID|None]=mapped_column(Uuid)
    analysis:Mapped[dict|None]=mapped_column(JSONB)
