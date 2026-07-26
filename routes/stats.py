import math
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends

from database import events, tasks, assignments, exams
from utils.auth import get_current_user

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/dashboard")
def get_dashboard(current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["_id"])
    today = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now()

    all_events = list(events.find({"owner_id": user_id}))
    all_tasks = list(tasks.find({"owner_id": user_id}))
    all_assignments = list(assignments.find({"owner_id": user_id}))
    all_exams = list(exams.find({"owner_id": user_id}))

    total_classes = len(all_events)
    attended = sum(1 for e in all_events if e.get("attended") is True)
    missed = sum(1 for e in all_events if e.get("attended") is False)
    unmarked = total_classes - attended - missed
    attendance_pct = (attended / (attended + missed) * 100) if (attended + missed) > 0 else 0
    can_skip = math.floor(attended * 4 / 3) - (attended + missed) if (attended + missed) > 0 else 0
    if can_skip < 0:
        can_skip = 0

    total_tasks = len(all_tasks)
    completed_tasks = sum(1 for t in all_tasks if t.get("completed", False))
    pending_tasks = total_tasks - completed_tasks

    total_assignments = len(all_assignments)
    completed_assignments = sum(1 for a in all_assignments if a.get("completed", False))

    total_exams = len(all_exams)
    completed_exams = sum(1 for e in all_exams if e.get("completed", False))
    upcoming_exams = sum(1 for e in all_exams if not e.get("completed", False) and e.get("date", "") >= today)

    weekly_classes = [0] * 7
    weekly_tasks_completed = [0] * 7
    for e in all_events:
        if not e.get("attended"):
            continue
        try:
            d = datetime.strptime(e["date"], "%Y-%m-%d")
            days_ago = (now.date() - d.date()).days
            if 0 <= days_ago < 7:
                weekly_classes[6 - days_ago] += 1
        except Exception:
            pass
    for t in all_tasks:
        if not t.get("completed"):
            continue
        try:
            created = t.get("created_at", "")
            if created:
                d = datetime.fromisoformat(created)
                days_ago = (now.date() - d.date()).days
                if 0 <= days_ago < 7:
                    weekly_tasks_completed[6 - days_ago] += 1
        except Exception:
            pass

    month_start = now.replace(day=1).strftime("%Y-%m-%d")
    monthly_classes_total = sum(1 for e in all_events if e.get("date", "") >= month_start)
    monthly_classes_attended = sum(1 for e in all_events if e.get("date", "") >= month_start and e.get("attended") is True)
    monthly_tasks_completed = sum(1 for t in all_tasks if t.get("completed", False) and t.get("created_at", "") >= month_start)
    monthly_assignments_completed = sum(1 for a in all_assignments if a.get("completed", False))

    study_hours = round(attended * 1.5, 1)

    task_pct = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
    assign_pct = (completed_assignments / total_assignments * 100) if total_assignments > 0 else 0
    productivity = round(attendance_pct * 0.4 + task_pct * 0.3 + assign_pct * 0.3, 1)

    return {
        "attendance": {
            "total": total_classes,
            "attended": attended,
            "missed": missed,
            "unmarked": unmarked,
            "percentage": round(attendance_pct, 1),
            "can_skip": can_skip,
        },
        "tasks": {
            "total": total_tasks,
            "completed": completed_tasks,
            "pending": pending_tasks,
        },
        "assignments": {
            "total": total_assignments,
            "completed": completed_assignments,
        },
        "exams": {
            "total": total_exams,
            "completed": completed_exams,
            "upcoming": upcoming_exams,
        },
        "productivity": productivity,
        "study_hours": study_hours,
        "weekly": {
            "classes": weekly_classes,
            "tasks": weekly_tasks_completed,
        },
        "monthly": {
            "classes_total": monthly_classes_total,
            "classes_attended": monthly_classes_attended,
            "tasks_completed": monthly_tasks_completed,
            "assignments_completed": monthly_assignments_completed,
        },
    }
