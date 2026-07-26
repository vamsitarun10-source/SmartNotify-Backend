from datetime import datetime, timedelta
from fastapi import APIRouter, Depends

from database import events, tasks, assignments, exams, timetable, notes
from utils.auth import get_current_user

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/")
def get_dashboard(current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["_id"])
    today = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now()
    now_time = now.strftime("%H:%M")

    start_of_week = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
    end_of_week = (now + timedelta(days=6 - now.weekday())).strftime("%Y-%m-%d")
    week_later = (now + timedelta(days=7)).strftime("%Y-%m-%d")

    # Fetch all data
    all_events = list(events.find({"owner_id": user_id}))
    all_tasks = list(tasks.find({"owner_id": user_id}))
    all_assignments = list(assignments.find({"owner_id": user_id}))
    all_exams = list(exams.find({"owner_id": user_id}))
    all_timetable = list(timetable.find({"owner_id": user_id}))
    all_notes = list(notes.find({"owner_id": user_id}))

    # 1. Weekly Attendance
    week_events = [e for e in all_events if start_of_week <= e.get("date", "") <= end_of_week]
    attendance = {}
    for e in week_events:
        title = e.get("title", "Unknown")
        if title not in attendance:
            attendance[title] = {"attended": 0, "missed": 0, "unmarked": 0, "total": 0}
        attendance[title]["total"] += 1
        if e.get("attended") is True:
            attendance[title]["attended"] += 1
        elif e.get("attended") is False:
            attendance[title]["missed"] += 1
        else:
            attendance[title]["unmarked"] += 1

    total_attended = sum(a["attended"] for a in attendance.values())
    total_missed = sum(a["missed"] for a in attendance.values())
    total_marked = total_attended + total_missed
    overall_pct = round(total_attended / max(total_marked, 1) * 100, 1)

    # 2. Weekly Productivity
    week_tasks = [t for t in all_tasks if t.get("created_at", today)[:10] >= start_of_week]
    tasks_completed = sum(1 for t in week_tasks if t.get("completed"))
    tasks_total = len(week_tasks)
    week_assignments = [a for a in all_assignments if a.get("created_at", today)[:10] >= start_of_week]
    assign_completed = sum(1 for a in week_assignments if a.get("completed"))
    assign_total = len(week_assignments)

    # 3. This Week's Exams
    this_week_exams = [
        {"id": str(e["_id"]), "title": e["title"], "subject": e.get("subject", ""), "date": e["date"],
         "time": e["time"], "exam_type": e.get("exam_type", ""), "location": e.get("location", "")}
        for e in all_exams
        if not e.get("completed") and start_of_week <= e.get("date", "") <= end_of_week
    ]

    # 4. Upcoming Assignments
    upcoming_assignments = [
        {"id": str(a["_id"]), "title": a["title"], "subject": a.get("subject", ""), "due_date": a.get("due_date", ""),
         "priority": a.get("priority", "medium"), "attachment": a.get("attachment", "")}
        for a in all_assignments
        if not a.get("completed") and a.get("due_date", "") >= today and a.get("due_date", "") <= week_later
    ][:5]

    # 5. Recent Notes
    recent_notes = [
        {"id": str(n["_id"]), "title": n["title"], "subject": n.get("subject", ""), "note_type": n.get("note_type", "text"),
         "preview": (n.get("content", "")[:80] + "...") if len(n.get("content", "")) > 80 else n.get("content", "")}
        for n in sorted(all_notes, key=lambda x: x.get("updated_at", ""), reverse=True)[:5]
    ]

    # 6. Free Time Today
    day_of_week = now.weekday()
    today_tt = [t for t in all_timetable if t.get("day_of_week") == day_of_week]
    today_events_list = [e for e in all_events if e.get("date") == today]
    occupied_hours = set()
    for t in today_tt:
        try:
            occupied_hours.add(int(t.get("time", "09:00").split(":")[0]))
        except (ValueError, IndexError):
            pass
    for e in today_events_list:
        try:
            occupied_hours.add(int(e.get("time", "09:00").split(":")[0]))
        except (ValueError, IndexError):
            pass
    free_hours = [h for h in range(9, 18) if h not in occupied_hours]
    free_periods = [{"start": f"{h:02d}:00", "end": f"{h+1:02d}:00"} for h in free_hours]

    # 7. Study Hours
    study_hours = round(total_attended * 1.5, 1)

    # 8. AI Suggestions
    suggestions = []
    overdue_assignments = [a for a in all_assignments if not a.get("completed") and a.get("due_date", "") < today]
    if overdue_assignments:
        suggestions.append({"icon": "alert-circle", "text": f"You have {len(overdue_assignments)} overdue assignment{'s' if len(overdue_assignments) != 1 else ''}!", "color": "#EF5350"})

    upcoming_exams_near = [e for e in all_exams if not e.get("completed") and today <= e.get("date", "") <= (now + timedelta(days=3)).strftime("%Y-%m-%d")]
    if upcoming_exams_near:
        suggestions.append({"icon": "school", "text": f"{upcoming_exams_near[0]['title']} is coming up in {(datetime.strptime(upcoming_exams_near[0]['date'], '%Y-%m-%d').date() - now.date()).days} days", "color": "#FFA726"})

    if overall_pct < 75 and total_marked > 0:
        suggestions.append({"icon": "warning", "text": f"Attendance is {overall_pct}% — aim for 75%+", "color": "#EF5350"})

    pending_tasks_count = sum(1 for t in all_tasks if not t.get("completed"))
    if pending_tasks_count > 5:
        suggestions.append({"icon": "checkbox", "text": f"You have {pending_tasks_count} pending tasks — consider prioritizing", "color": "#42A5F5"})

    if not suggestions:
        suggestions.append({"icon": "checkmark-circle", "text": "You're on track! Keep up the great work.", "color": "#66BB6A"})

    return {
        "attendance": {
            "subjects": [{"name": k, "attended": v["attended"], "missed": v["missed"], "unmarked": v["unmarked"], "total": v["total"],
                          "pct": round(v["attended"] / max(v["attended"] + v["missed"], 1) * 100, 1)} for k, v in attendance.items()],
            "total_attended": total_attended,
            "total_missed": total_missed,
            "overall_pct": overall_pct,
        },
        "productivity": {
            "tasks_completed": tasks_completed,
            "tasks_total": tasks_total,
            "assignments_completed": assign_completed,
            "assignments_total": assign_total,
        },
        "exams_this_week": this_week_exams,
        "upcoming_assignments": upcoming_assignments,
        "recent_notes": recent_notes,
        "free_periods": free_periods,
        "free_periods_count": len(free_periods),
        "study_hours": study_hours,
        "suggestions": suggestions,
    }
