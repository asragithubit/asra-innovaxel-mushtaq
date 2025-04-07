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


