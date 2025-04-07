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


