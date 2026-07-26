from typing import Optional, List
from pydantic import BaseModel


class Achievement(BaseModel):
    id: str
    name: str
    description: str
    icon: str
    unlocked: bool = False


class RewardData(BaseModel):
    id: str = ""
    owner_id: str = ""
    xp: int = 0
    level: int = 1
    daily_streak: int = 0
    attendance_streak: int = 0
    task_streak: int = 0
    last_active_date: str = ""
    last_attendance_date: str = ""
    last_task_date: str = ""
    achievements: List[str] = []
    badges: List[str] = []
    weekly_goals: dict = {"tasks": 5, "attendance_pct": 80, "study_hours": 5.0}
    monthly_goals: dict = {"tasks": 20, "attendance_pct": 80, "study_hours": 20.0}
    weekly_progress: dict = {"tasks_completed": 0, "attendance_pct": 0.0, "study_hours": 0.0}
    monthly_progress: dict = {"tasks_completed": 0, "attendance_pct": 0.0, "study_hours": 0.0}
    created_at: str = ""
    updated_at: str = ""
