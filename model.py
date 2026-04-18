from datetime import datetime
from sqlalchemy import Column, String, DateTime, Integer
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

class Appointment(Base):
    __tablename__ = "appointments"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    client_name = Column(String, nullable=False)
    contact_no  = Column(String, nullable=False)
    date_time   = Column(DateTime, nullable=False)
    case_type   = Column(String, nullable=False)

    def __repr__(self):
        return f"<Appointment {self.client_name} – {self.case_type} @ {self.date_time}>"