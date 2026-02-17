from sqlalchemy.orm import declarative_base, relationship
    from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text, UniqueConstraint, Index
    from datetime import datetime

    Base = declarative_base()

    class User(Base):
        __tablename__ = "users"
        id = Column(Integer, primary_key=True)
        full_name = Column(String(100), nullable=False)
        email = Column(String(255), unique=True, index=True, nullable=False)
        password_hash = Column(String(255), nullable=False)
        status = Column(String(20), default="pending")
        profile_pic_url = Column(String(255))
        created_at = Column(DateTime, default=datetime.utcnow)
        last_login = Column(DateTime)
        failed_attempts = Column(Integer, default=0)
        locked_until = Column(DateTime)
        twofa_secret = Column(String(32))
        companies = relationship("Company", back_populates="owner")

    class VerificationToken(Base):
        __tablename__ = "verification_tokens"
        id = Column(Integer, primary_key=True)
        user_id = Column(Integer, ForeignKey("users.id"))
        token = Column(String(255), index=True)
        expires_at = Column(DateTime)
        used = Column(Boolean, default=False)

    class ResetToken(Base):
        __tablename__ = "reset_tokens"
        id = Column(Integer, primary_key=True)
        user_id = Column(Integer, ForeignKey("users.id"))
        token = Column(String(255), index=True)
        expires_at = Column(DateTime)
        used = Column(Boolean, default=False)

    class LoginAttempt(Base):
        __tablename__ = "login_attempts"
        id = Column(Integer, primary_key=True)
        user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
        ip = Column(String(45))
        attempted_at = Column(DateTime, default=datetime.utcnow)
        success = Column(Boolean, default=False)

    class Company(Base):
        __tablename__ = "companies"
        id = Column(Integer, primary_key=True)
        owner_id = Column(Integer, ForeignKey("users.id"))
        name = Column(String(255), nullable=False)
        place_id = Column(String(128))
        maps_link = Column(String(512))
        city = Column(String(128))
        status = Column(String(20), default="active")
        logo_url = Column(String(255))
        created_at = Column(DateTime, default=datetime.utcnow)
        owner = relationship("User", back_populates="companies")
        reviews = relationship("Review", back_populates="company")
        __table_args__ = (
            Index('idx_company_owner_status', 'owner_id', 'status'),
        )

    class Review(Base):
        __tablename__ = "reviews"
        id = Column(Integer, primary_key=True)
        company_id = Column(Integer, ForeignKey("companies.id"))
        external_id = Column(String(128))
        text = Column(Text)
        rating = Column(Integer)
        review_at = Column(DateTime)
        reviewer_name = Column(String(255))
        reviewer_avatar = Column(String(255))
        sentiment = Column(String(20))
        sentiment_score = Column(Integer)  # 0..100
        keywords = Column(String(512))
        language = Column(String(10))
        fetch_at = Column(DateTime, default=datetime.utcnow)
        fetch_status = Column(String(20), default="Success")
        company = relationship("Company", back_populates="reviews")
        replies = relationship("Reply", back_populates="review")
        __table_args__ = (
            UniqueConstraint('company_id', 'external_id', name='uq_review_company_ext'),
        )

    class Reply(Base):
        __tablename__ = "replies"
        id = Column(Integer, primary_key=True)
        review_id = Column(Integer, ForeignKey("reviews.id"))
        suggested_text = Column(Text)
        edited_text = Column(Text)
        status = Column(String(20), default="Draft")
        suggested_at = Column(DateTime, default=datetime.utcnow)
        sent_at = Column(DateTime)
        review = relationship("Review", back_populates="replies")

    class Report(Base):
        __tablename__ = "reports"
        id = Column(Integer, primary_key=True)
        company_id = Column(Integer, ForeignKey("companies.id"))
        title = Column(String(255))
        path = Column(String(512))
        meta = Column(Text)
        generated_at = Column(DateTime, default=datetime.utcnow)

    class Notification(Base):
        __tablename__ = "notifications"
        id = Column(Integer, primary_key=True)
        user_id = Column(Integer, ForeignKey("users.id"))
        company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
        kind = Column(String(50))
        payload = Column(Text)
        created_at = Column(DateTime, default=datetime.utcnow)
        read = Column(Boolean, default=False)