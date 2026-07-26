import math
from datetime import datetime, timedelta
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from database import rewards, events, tasks, assignments
from models.reward import RewardData
from utils.auth import get_current_user

router = APIRouter(prefix="/rewards", tags=["rewards"])


class AddXpBody(BaseModel):
    amount: int = 0
    reason: str = ""

ACHIEVEMENTS = [
    {"id": "first_task", "name": "First Step", "desc": "Complete your first task", "icon": "footsteps"},
    {"id": "task_10", "name": "Task Master", "desc": "Complete 10 tasks", "icon": "checkbox"},
    {"id": "task_50", "name": "Task Legend", "desc": "Complete 50 tasks", "icon": "trophy"},
    {"id": "streak_3", "name": "Getting Started", "desc": "3-day daily streak", "icon": "flame"},
    {"id": "streak_7", "name": "Week Warrior", "desc": "7-day daily streak", "icon": "flame"},
    {"id": "streak_30", "name": "Monthly Champion", "desc": "30-day daily streak", "icon": "flame"},
    {"id": "attendance_100", "name": "Perfect Week", "desc": "100% attendance for a week", "icon": "checkmark-done"},
    {"id": "attendance_5", "name": "Attendance Star", "desc": "Attend 5 classes in a row", "icon": "star"},
    {"id": "early_bird", "name": "Early Bird", "desc": "Complete a task before 9am", "icon": "sunny"},
    {"id": "note_taker", "name": "Note Taker", "desc": "Create 5 notes", "icon": "document-text"},
    {"id": "level_5", "name": "Rising Star", "desc": "Reach level 5", "icon": "rocket"},
    {"id": "level_10", "name": "Expert", "desc": "Reach level 10", "icon": "diamond"},
    {"id": "week_goal", "name": "Goal Getter", "desc": "Complete weekly goal", "icon": "flag"},
    {"id": "month_goal", "name": "Monthly Master", "desc": "Complete monthly goal", "icon": "ribbon"},
    {"id": "all_done", "name": "Clean Slate", "desc": "Complete all tasks and assignments", "icon": "sparkles"},
    {"id": "scholar", "name": "Scholar", "desc": "90%+ attendance for a month", "icon": "school"},
    {"id": "productivity_king", "name": "Productivity King", "desc": "Earn 500+ XP", "icon": "trophy"},
    {"id": "night_owl", "name": "Night Owl", "desc": "Complete a task after 10pm", "icon": "moon"},
    {"id": "exam_ready", "name": "Exam Ready", "desc": "Create notes for 3+ subjects", "icon": "book"},
    {"id": "all_subjects", "name": "Well-Rounded", "desc": "Attend 3+ different subjects", "icon": "globe"},
]

BADGE_TIERS = [
    {"id": "task_champion_bronze", "name": "Task Champion (Bronze)", "icon": "medal", "color": "#CD7F32"},
    {"id": "task_champion_silver", "name": "Task Champion (Silver)", "icon": "medal", "color": "#C0C0C0"},
    {"id": "task_champion_gold", "name": "Task Champion (Gold)", "icon": "medal", "color": "#FFD700"},
    {"id": "attendance_hero_bronze", "name": "Attendance Hero (Bronze)", "icon": "shield-checkmark", "color": "#CD7F32"},
    {"id": "attendance_hero_silver", "name": "Attendance Hero (Silver)", "icon": "shield-checkmark", "color": "#C0C0C0"},
    {"id": "attendance_hero_gold", "name": "Attendance Hero (Gold)", "icon": "shield-checkmark", "color": "#FFD700"},
    {"id": "streak_king_bronze", "name": "Streak King (Bronze)", "icon": "flame", "color": "#CD7F32"},
    {"id": "streak_king_silver", "name": "Streak King (Silver)", "icon": "flame", "color": "#C0C0C0"},
    {"id": "streak_king_gold", "name": "Streak King (Gold)", "icon": "flame", "color": "#FFD700"},
    {"id": "study_star", "name": "Study Star", "icon": "book", "color": "#42A5F5"},
]


def _get_or_create_rewards(user_id: str) -> dict:
    doc = rewards.find_one({"owner_id": user_id})
    if not doc:
        now = datetime.now().isoformat()
        doc = {
            "owner_id": user_id,
            "xp": 0,
            "level": 1,
            "daily_streak": 0,
            "attendance_streak": 0,
            "task_streak": 0,
            "last_active_date": "",
            "last_attendance_date": "",
            "last_task_date": "",
            "achievements": [],
            "badges": [],
            "weekly_goals": {"tasks": 5, "attendance_pct": 80, "study_hours": 5.0},
            "monthly_goals": {"tasks": 20, "attendance_pct": 80, "study_hours": 20.0},
            "weekly_progress": {"tasks_completed": 0, "attendance_pct": 0.0, "study_hours": 0.0},
            "monthly_progress": {"tasks_completed": 0, "attendance_pct": 0.0, "study_hours": 0.0},
            "created_at": now,
            "updated_at": now,
        }
        result = rewards.insert_one(doc)
        doc["_id"] = result.inserted_id
    return doc


def _compute_streaks(user_id: str, doc: dict):
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    now = datetime.now()

    # Daily streak
    if doc.get("last_active_date") == today:
        pass
    elif doc.get("last_active_date") == yesterday:
        doc["daily_streak"] = doc.get("daily_streak", 0) + 1
        doc["last_active_date"] = today
    else:
        doc["daily_streak"] = 1
        doc["last_active_date"] = today

    # Attendance streak
    today_attended = list(events.find({
        "owner_id": user_id, "date": today, "attended": True
    }))
    if today_attended:
        if doc.get("last_attendance_date") == yesterday:
            doc["attendance_streak"] = doc.get("attendance_streak", 0) + 1
        elif doc.get("last_attendance_date") != today:
            doc["attendance_streak"] = 1
        doc["last_attendance_date"] = today

    # Task streak
    today_tasks = list(tasks.find({
        "owner_id": user_id, "completed": True,
        "created_at": {"$regex": f"^{today}"}
    }))
    if today_tasks:
        if doc.get("last_task_date") == yesterday:
            doc["task_streak"] = doc.get("task_streak", 0) + 1
        elif doc.get("last_task_date") != today:
            doc["task_streak"] = 1
        doc["last_task_date"] = today


def _compute_progress(user_id: str, doc: dict):
    today = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now()
    start_of_week = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
    month_start = now.replace(day=1).strftime("%Y-%m-%d")
    end_of_week = (now + timedelta(days=6 - now.weekday())).strftime("%Y-%m-%d")

    # Weekly progress
    week_tasks_completed = sum(1 for t in tasks.find({"owner_id": user_id, "completed": True})
                               if t.get("created_at", "")[:10] >= start_of_week)
    week_events = list(events.find({"owner_id": user_id, "date": {"$gte": start_of_week, "$lte": end_of_week}}))
    week_attended = sum(1 for e in week_events if e.get("attended") is True)
    week_marked = sum(1 for e in week_events if e.get("attended") is not None)
    week_pct = round(week_attended / max(week_marked, 1) * 100, 1)
    week_study = round(week_attended * 1.5, 1)

    doc["weekly_progress"] = {
        "tasks_completed": week_tasks_completed,
        "attendance_pct": week_pct,
        "study_hours": week_study,
    }

    # Monthly progress
    month_tasks_completed = sum(1 for t in tasks.find({"owner_id": user_id, "completed": True})
                                if t.get("created_at", "")[:10] >= month_start)
    month_events = list(events.find({"owner_id": user_id, "date": {"$gte": month_start}}))
    month_attended = sum(1 for e in month_events if e.get("attended") is True)
    month_marked = sum(1 for e in month_events if e.get("attended") is not None)
    month_pct = round(month_attended / max(month_marked, 1) * 100, 1)
    month_study = round(month_attended * 1.5, 1)

    doc["monthly_progress"] = {
        "tasks_completed": month_tasks_completed,
        "attendance_pct": month_pct,
        "study_hours": month_study,
    }


def _check_achievements(user_id: str, doc: dict):
    new_achievements = []
    unlocked = set(doc.get("achievements", []))

    total_tasks_completed = sum(1 for t in tasks.find({"owner_id": user_id, "completed": True}))
    total_assignments_completed = sum(1 for a in assignments.find({"owner_id": user_id, "completed": True}))
    total_notes = len(list({"owner_id": user_id}))

    checks = {
        "first_task": total_tasks_completed >= 1,
        "task_10": total_tasks_completed >= 10,
        "task_50": total_tasks_completed >= 50,
        "streak_3": doc.get("daily_streak", 0) >= 3,
        "streak_7": doc.get("daily_streak", 0) >= 7,
        "streak_30": doc.get("daily_streak", 0) >= 30,
        "level_5": doc.get("level", 1) >= 5,
        "level_10": doc.get("level", 1) >= 10,
        "productivity_king": doc.get("xp", 0) >= 500,
        "week_goal": doc.get("weekly_progress", {}).get("tasks_completed", 0) >= doc.get("weekly_goals", {}).get("tasks", 5),
        "month_goal": doc.get("monthly_progress", {}).get("tasks_completed", 0) >= doc.get("monthly_goals", {}).get("tasks", 20),
        "all_done": total_tasks_completed > 0 and total_assignments_completed > 0 and total_tasks_completed == sum(1 for t in tasks.find({"owner_id": user_id})) and total_assignments_completed == sum(1 for a in assignments.find({"owner_id": user_id})),
        "all_subjects": len(set(e.get("title", "") for e in events.find({"owner_id": user_id, "attended": True}))) >= 3,
    }

    for aid, condition in checks.items():
        if condition and aid not in unlocked:
            new_achievements.append(aid)
            unlocked.add(aid)

    doc["achievements"] = list(unlocked)

    # Badges
    badges = set(doc.get("badges", []))
    if total_tasks_completed >= 10 and "task_champion_bronze" not in badges:
        badges.add("task_champion_bronze")
    if total_tasks_completed >= 25 and "task_champion_silver" not in badges:
        badges.add("task_champion_silver")
    if total_tasks_completed >= 50 and "task_champion_gold" not in badges:
        badges.add("task_champion_gold")
    if doc.get("attendance_streak", 0) >= 3 and "attendance_hero_bronze" not in badges:
        badges.add("attendance_hero_bronze")
    if doc.get("attendance_streak", 0) >= 7 and "attendance_hero_silver" not in badges:
        badges.add("attendance_hero_silver")
    if doc.get("attendance_streak", 0) >= 14 and "attendance_hero_gold" not in badges:
        badges.add("attendance_hero_gold")
    if doc.get("daily_streak", 0) >= 3 and "streak_king_bronze" not in badges:
        badges.add("streak_king_bronze")
    if doc.get("daily_streak", 0) >= 7 and "streak_king_silver" not in badges:
        badges.add("streak_king_silver")
    if doc.get("daily_streak", 0) >= 14 and "streak_king_gold" not in badges:
        badges.add("streak_king_gold")
    doc["badges"] = list(badges)

    return new_achievements


@router.get("/", response_model=dict)
def get_rewards(current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["_id"])
    doc = _get_or_create_rewards(user_id)
    _compute_streaks(user_id, doc)
    _compute_progress(user_id, doc)
    new_achievements = _check_achievements(user_id, doc)

    # Compute level from XP
    doc["level"] = doc.get("xp", 0) // 100 + 1

    doc["updated_at"] = datetime.now().isoformat()
    rewards.update_one({"_id": doc["_id"]}, {"$set": {
        "daily_streak": doc["daily_streak"],
        "attendance_streak": doc["attendance_streak"],
        "task_streak": doc["task_streak"],
        "last_active_date": doc["last_active_date"],
        "last_attendance_date": doc["last_attendance_date"],
        "last_task_date": doc["last_task_date"],
        "weekly_progress": doc["weekly_progress"],
        "monthly_progress": doc["monthly_progress"],
        "achievements": doc["achievements"],
        "badges": doc["badges"],
        "level": doc["level"],
        "updated_at": doc["updated_at"],
    }})

    # Build response
    achievement_list = []
    for a in ACHIEVEMENTS:
        achievement_list.append({
            **a,
            "unlocked": a["id"] in doc.get("achievements", []),
        })

    badge_list = []
    for b in BADGE_TIERS:
        badge_list.append({
            **b,
            "unlocked": b["id"] in doc.get("badges", []),
        })

    return {
        "xp": doc.get("xp", 0),
        "level": doc.get("level", 1),
        "xp_to_next_level": ((doc.get("level", 1)) * 100) - doc.get("xp", 0),
        "daily_streak": doc.get("daily_streak", 0),
        "attendance_streak": doc.get("attendance_streak", 0),
        "task_streak": doc.get("task_streak", 0),
        "achievements": achievement_list,
        "badges": badge_list,
        "weekly_goals": doc.get("weekly_goals"),
        "monthly_goals": doc.get("monthly_goals"),
        "weekly_progress": doc.get("weekly_progress"),
        "monthly_progress": doc.get("monthly_progress"),
        "new_achievements": new_achievements,
    }


@router.post("/add-xp", response_model=dict)
def add_xp(body: AddXpBody, current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["_id"])
    doc = _get_or_create_rewards(user_id)
    doc["xp"] = doc.get("xp", 0) + body.amount
    doc["level"] = doc["xp"] // 100 + 1
    doc["updated_at"] = datetime.now().isoformat()
    rewards.update_one({"_id": doc["_id"]}, {"$set": {
        "xp": doc["xp"], "level": doc["level"], "updated_at": doc["updated_at"]
    }})
    return {"xp": doc["xp"], "level": doc["level"], "added": body.amount, "reason": body.reason}
