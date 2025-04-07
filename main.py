from fastapi import FastAPI, HTTPException, Depends, status,Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict,HttpUrl
from sqlalchemy import create_engine, Column, String, Integer, DateTime
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from fastapi.responses import RedirectResponse
from datetime import datetime, timezone
import secrets
import string
from urllib.parse import urlparse
from typing import Optional
import os

# =================DATABASE SETUP======================
# Constructs the database connection URL using SQLite and absolute path to 'shortener.db'
# Absolute path ensures the database file can be found regardless of working directory
SQLALCHEMY_DATABASE_URL = f"sqlite:///{os.path.abspath('shortener.db')}"  # Changed to absolute path

# Creates the database engine - the main entry point for SQLAlchemy
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,  
    connect_args={"check_same_thread": False},    
    pool_pre_ping=True,    
    echo=True  
)

#   ======================SESSION FACTORY FOR DATABASE OPERATIONS ==================
# - autocommit=False: Requires explicit commits for data persistence
# - autoflush=False: Gives manual control over when changes are sent to database  
# - bind=engine: Connects sessions to our SQLite database engine
SessionLocal = sessionmaker(
    autocommit=False, 
    autoflush=False,   
    bind=engine        
)

# ==================Base class for SQLAlchemy ORM models that provides the foundation for database table mappings=====================
Base = declarative_base()

# =================CREATION OF TABLES DEFINED IN SQLALCHEMY MODELS=============
def create_tables():
    Base.metadata.create_all(bind=engine)

# Database model for URL shortening service with tracking fields
class URL(Base):
    __tablename__ = "urls" 

    id = Column(Integer, primary_key=True, index=True) 
    url = Column(String(2048), index=True)  
    short_code = Column(String(12), unique=True, index=True) 
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))  
    updated_at = Column(DateTime, 
                      default=lambda: datetime.now(timezone.utc),
                      onupdate=lambda: datetime.now(timezone.utc))  
    access_count = Column(Integer, default=0)  

# VALIDATION SCHEMAS AND FASTAPI CONFIGURATION FOR URL SHORTENER SERVICE
class URLCreate(BaseModel):
    url: str

    #@field_validator('url')
    def validate_url(cls, v):
        try:
            result = urlparse(v)
            if not all([result.scheme, result.netloc]):
                raise ValueError("URL must include scheme (http/https) and domain")
            if result.scheme not in ['http', 'https']:
                raise ValueError("Only http and https URLs are allowed")
            return v
        except Exception as e:
            raise ValueError(str(e))

class URLInfo(BaseModel):
    id: int
    url: str
    shortCode: str
    createdAt: str
    updatedAt: str
    accessCount: int

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={
            datetime: lambda v: v.isoformat() + "Z"
        },
        alias_generator=lambda x: x
    )

class ErrorResponse(BaseModel):
    detail: str

# FASTAPI APPLICATION INITIALIZATION WITH CUSTOM ERROR RESPONSES
app = FastAPI(
    title="URL Shortener",
    version="1.0.0",
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse}
    }
)

# =============DATABASE SESSION MANAGEMENT=========
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

#=============RANDOM CODE GENERATION USING SECRET MODULE
def generate_short_code(length: int = 6) -> str:
    chars = string.ascii_letters + string.digits
    return ''.join(secrets.choice(chars) for _ in range(length))

# Debug endpoint to check all URLs in database
@app.get("/debug/all-urls", include_in_schema=False)
def debug_all_urls(db: Session = Depends(get_db)):
    urls = db.query(URL).all()
    return {
        "count": len(urls),
        "urls": [{
            "short_code": url.short_code,
            "url": url.url
        } for url in urls]
    }

#Ensures that the upcoming url is valid url
class UpdateURLRequest(BaseModel):
    url: str  # Ensures it's a valid URL

@app.post(
    "/shorten",
    response_model=URLInfo,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"description": "Invalid URL"},
        201: {"description": "Short URL created", "content": {"application/json": {"example": {
            "id": 1,
            "url": "https://example.com",
            "shortCode": "abc123",
            "createdAt": "2023-07-20T12:00:00Z",
            "updatedAt": "2023-07-20T12:00:00Z",
            "accessCount": 0
        }}}}
    }
)
def create_short_url(url: URLCreate, db: Session = Depends(get_db)):
    try:
        # Check URL starts with http:// or https://
        if not url.url.startswith(('http://', 'https://')):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="URL must start with http:// or https://"
            )
            
        # Existing URL check (case-insensitive)
        existing_url = db.query(URL).filter(URL.url.ilike(url.url)).first()
        if existing_url:
            return {
                "id": existing_url.id,
                "url": existing_url.url,
                "shortCode": existing_url.short_code,
                "createdAt": existing_url.created_at.isoformat() + "Z",
                "updatedAt": existing_url.updated_at.isoformat() + "Z",
                "accessCount": existing_url.access_count
            }

        # Generate short code
        short_code = generate_short_code()
        while db.query(URL).filter(URL.short_code.ilike(short_code)).first():
            short_code = generate_short_code()

        # Save to database
        db_url = URL(url=url.url, short_code=short_code)
        db.add(db_url)
        db.commit()
        db.refresh(db_url)

        return {
            "id": db_url.id,
            "url": db_url.url,
            "shortCode": db_url.short_code,
            "createdAt": db_url.created_at.isoformat() + "Z",
            "updatedAt": db_url.updated_at.isoformat() + "Z",
            "accessCount": 0
        }

    except Exception as e:
        db.rollback()  # Added to ensure transaction consistency
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    

@app.get("/shorten/{short_code}", response_model=URLInfo)
def get_original_url(short_code: str, db: Session = Depends(get_db)):
    short_code = short_code.strip()  # Added to handle whitespace
    db_url = db.query(URL).filter(URL.short_code.ilike(short_code)).first()  # Changed to case-insensitive
    
    if not db_url:
        # Added debug information
        available = [url.short_code for url in db.query(URL).limit(5).all()]
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Short URL not found. First 5 available codes: {available}"
        )
    
    db_url.access_count += 1
    db.commit()
    db.refresh(db_url)
    
    return {
        "id": db_url.id,
        "url": db_url.url,
        "shortCode": db_url.short_code,
        "createdAt": db_url.created_at.isoformat() + "Z",
        "updatedAt": db_url.updated_at.isoformat() + "Z",
        "accessCount": db_url.access_count
    }

#===================IMPLEMENTATION OF HTTP METHODS=============
@app.put("/shorten/{short_code}", response_model=URLInfo)
def update_short_url(
    short_code: str,
    request: UpdateURLRequest,
    db: Session = Depends(get_db)
):
    short_code = short_code.strip()  # Added to handle whitespace
    db_url = db.query(URL).filter(URL.short_code.ilike(short_code)).first()  # Changed to case-insensitive

    if not db_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Short URL not found"
        )

    try:
        db_url.short_code = request.url  # Fixed: was updating short_code instead of url
        db_url.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(db_url)

        return URLInfo(
            id=db_url.id,
            url=db_url.url,
            shortCode=db_url.short_code,
            createdAt=db_url.created_at.isoformat() + "Z",
            updatedAt=db_url.updated_at.isoformat() + "Z",
            accessCount=db_url.access_count
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    

@app.delete("/shorten/{short_code}", status_code=status.HTTP_204_NO_CONTENT)
def delete_short_url(short_code: str, db: Session = Depends(get_db)):
    print(f"Attempting to delete URL with short_code: {short_code}")  # Debugging line
    short_code = short_code.strip()  # Added to handle whitespace
    db_url = db.query(URL).filter(URL.short_code.ilike(short_code)).first()  # Changed to case-insensitive

    if not db_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Short URL not found"
        )

    try:
        db.delete(db_url)
        db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    
@app.get("/statistics/{short_code}", response_model=URLInfo)
def get_url_statistics(short_code: str, db: Session = Depends(get_db)):
    short_code = short_code.strip()  # Added to handle whitespace
    db_url = db.query(URL).filter(URL.short_code.ilike(short_code)).first()  # Changed to case-insensitive

    if not db_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Short URL not found"
        )
    
    return URLInfo(
        id=db_url.id,
        url=db_url.url,
        shortCode=db_url.short_code,
        createdAt=db_url.created_at.isoformat() + "Z",
        updatedAt=db_url.updated_at.isoformat() + "Z",
        accessCount=db_url.access_count
    )

# Run application
if _name_ == "_main_":
    create_tables()
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        server_header=False
    )


