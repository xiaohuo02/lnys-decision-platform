# -*- coding: utf-8 -*-
"""backend/dependencies/db.py — DB Session 依赖注入"""
from typing import Annotated, Generator
from fastapi import Depends
from sqlalchemy.orm import Session
from backend.database import get_db

DbSession = Annotated[Session, Depends(get_db)]
