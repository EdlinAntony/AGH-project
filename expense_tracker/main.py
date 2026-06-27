from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional

# ============================================
# DATABASE CONFIGURATION
# ============================================
SQLALCHEMY_DATABASE_URL = "sqlite:///./expense_tracker.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ============================================
# DATABASE MODELS
# ============================================
class Expense(Base):
    __tablename__ = "expenses"
    
    id = Column(Integer, primary_key=True, index=True)
    amount = Column(Float, nullable=False)
    category = Column(String(100), nullable=False)
    description = Column(String(500), default="")
    expense_type = Column(String(20), nullable=False)
    date = Column(String(20), default=lambda: datetime.now().strftime("%Y-%m-%d"))
    created_at = Column(DateTime, default=datetime.utcnow)

class Budget(Base):
    __tablename__ = "budgets"
    
    id = Column(Integer, primary_key=True, index=True)
    category = Column(String(100), unique=True, nullable=False)
    limit_amount = Column(Float, nullable=False)
    month = Column(String(7), default=lambda: datetime.now().strftime("%Y-%m"))
    created_at = Column(DateTime, default=datetime.utcnow)

# Create tables
Base.metadata.create_all(bind=engine)

# ============================================
# PYDANTIC SCHEMAS
# ============================================
class ExpenseCreate(BaseModel):
    amount: float = Field(..., gt=0)
    category: str
    description: Optional[str] = ""
    expense_type: str
    date: Optional[str] = None

class ExpenseResponse(ExpenseCreate):
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True

class BudgetCreate(BaseModel):
    category: str
    limit_amount: float = Field(..., gt=0)
    month: Optional[str] = None

class BudgetResponse(BudgetCreate):
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True

class BudgetStatus(BaseModel):
    category: str
    limit_amount: float
    total_spent: float
    remaining: float

# ============================================
# DATABASE SESSION
# ============================================
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ============================================
# FASTAPI APP
# ============================================
app = FastAPI(title="Expense Tracker API")

# ============================================
# EXPENSE ENDPOINTS
# ============================================
@app.post("/expenses/", response_model=ExpenseResponse, status_code=201)
def create_expense(expense: ExpenseCreate, db: Session = Depends(get_db)):
    expense_date = expense.date if expense.date else datetime.now().strftime("%Y-%m-%d")
    
    db_expense = Expense(
        amount=expense.amount,
        category=expense.category,
        description=expense.description or "",
        expense_type=expense.expense_type,
        date=expense_date
    )
    
    db.add(db_expense)
    db.commit()
    db.refresh(db_expense)
    return db_expense

@app.get("/expenses/", response_model=List[ExpenseResponse])
def get_expenses(
    skip: int = 0,
    limit: int = 100,
    expense_type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get all expenses - SIMPLIFIED"""
    try:
        query = db.query(Expense)
        
        if expense_type:
            query = query.filter(Expense.expense_type == expense_type)
        
        expenses = query.offset(skip).limit(limit).all()
        return expenses
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/expenses/{expense_id}", response_model=ExpenseResponse)
def get_expense(expense_id: int, db: Session = Depends(get_db)):
    expense = db.query(Expense).filter(Expense.id == expense_id).first()
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    return expense

@app.delete("/expenses/{expense_id}", status_code=204)
def delete_expense(expense_id: int, db: Session = Depends(get_db)):
    expense = db.query(Expense).filter(Expense.id == expense_id).first()
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    
    db.delete(expense)
    db.commit()
    return None

# ============================================
# BUDGET ENDPOINTS
# ============================================
@app.post("/budgets/", response_model=BudgetResponse, status_code=201)
def create_budget(budget: BudgetCreate, db: Session = Depends(get_db)):
    if not budget.month:
        budget.month = datetime.now().strftime("%Y-%m")
    
    existing = db.query(Budget).filter(
        Budget.category == budget.category,
        Budget.month == budget.month
    ).first()
    
    if existing:
        existing.limit_amount = budget.limit_amount
        db.commit()
        db.refresh(existing)
        return existing
    
    db_budget = Budget(
        category=budget.category,
        limit_amount=budget.limit_amount,
        month=budget.month
    )
    db.add(db_budget)
    db.commit()
    db.refresh(db_budget)
    return db_budget

@app.get("/budgets/status")
def get_budget_status(db: Session = Depends(get_db)):
    budgets = db.query(Budget).all()
    result = []
    
    for budget in budgets:
        total_spent = db.query(func.sum(Expense.amount)).filter(
            Expense.category == budget.category
        ).scalar() or 0.0
        
        result.append({
            "category": budget.category,
            "limit_amount": budget.limit_amount,
            "total_spent": round(total_spent, 2),
            "remaining": round(budget.limit_amount - total_spent, 2)
        })
    
    return result

# ============================================
# DASHBOARD
# ============================================
@app.get("/dashboard/summary")
def get_dashboard_summary(db: Session = Depends(get_db)):
    personal = db.query(func.sum(Expense.amount)).filter(
        Expense.expense_type == "personal"
    ).scalar() or 0.0
    
    business = db.query(func.sum(Expense.amount)).filter(
        Expense.expense_type == "business"
    ).scalar() or 0.0
    
    return {
        "total_expenses": round(personal + business, 2),
        "personal_expenses": round(personal, 2),
        "business_expenses": round(business, 2)
    }

@app.get("/")
def root():
    return {"status": "API is running", "docs": "/docs"}
