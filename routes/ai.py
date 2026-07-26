import re
from datetime import datetime, timedelta
from bson import ObjectId
from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field, ValidationError

from models.event import EventCreate, EventOut
from database import events, tasks, assignments, exams
from utils.limiter import limiter
from services.gemini import parse_event_from_text, classify_intent
from utils.auth import get_current_user


def _to_event_out(doc: dict) -> EventOut:
    return EventOut(
        id=str(doc["_id"]),
        owner_id=str(doc.get("owner_id", "")),
        title=doc["title"],
        subject=doc.get("subject", ""),
        date=doc["date"],
        time=doc["time"],
        reminder_before=doc.get("reminder_before", 15),
        location=doc.get("location", ""),
        notes=doc.get("notes", ""),
        completed=doc.get("completed", False),
        duration_minutes=doc.get("duration_minutes"),
    )


def _find_matching_event(owner_id: str, title_keyword: str, match_date: str = None) -> dict:
    clean = re.sub(r"\b(?:on|at|for|from|to|in|and|the|a|an|my|every|due)\b", " ", title_keyword, flags=re.IGNORECASE)
    words = [w for w in clean.split() if len(w) > 2]
    if not words:
        return None
    pattern = ".*".join(re.escape(w) for w in words)
    query = {"owner_id": owner_id, "title": {"$regex": pattern, "$options": "i"}}
    if match_date:
        query["date"] = match_date
    cursor = events.find(query).sort("date", 1).sort("time", 1)
    for doc in cursor:
        return doc
    return None


def _format_event_summary(doc: dict) -> str:
    return f"{doc['title']} on {doc['date']} at {doc['time']}"


def _get_stats_dashboard(user_id: str) -> dict:
    today = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now()
    all_events = list(events.find({"owner_id": user_id}))
    all_tasks = list(tasks.find({"owner_id": user_id}))
    all_assignments = list(assignments.find({"owner_id": user_id}))
    all_exams = list(exams.find({"owner_id": user_id}))
    total_events = len(all_events)
    attended = sum(1 for e in all_events if e.get("attended") is True)
    missed = sum(1 for e in all_events if e.get("attended") is False)
    attendance_pct = (attended / (attended + missed) * 100) if (attended + missed) > 0 else 0
    total_tasks = len(all_tasks)
    completed_tasks = sum(1 for t in all_tasks if t.get("completed", False))
    total_assignments = len(all_assignments)
    completed_assignments = sum(1 for a in all_assignments if a.get("completed", False))
    total_exams = len(all_exams)
    upcoming_exams = sum(1 for e in all_exams if not e.get("completed", False) and e.get("date", "") >= today)
    task_pct = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
    assign_pct = (completed_assignments / total_assignments * 100) if total_assignments > 0 else 0
    productivity = round(attendance_pct * 0.4 + task_pct * 0.3 + assign_pct * 0.3, 1)
    study_hours = round(attended * 1.5, 1)
    weekly_classes = []
    for i in range(7):
        d = (now - timedelta(days=6 - i)).strftime("%Y-%m-%d")
        weekly_classes.append(sum(1 for e in all_events if e.get("date") == d and e.get("attended") is True))
    month_start = now.replace(day=1).strftime("%Y-%m-%d")
    monthly_classes_attended = sum(1 for e in all_events if e.get("date", "") >= month_start and e.get("attended") is True)
    monthly_tasks_completed = sum(1 for t in all_tasks if t.get("completed", False) and t.get("created_at", "") >= month_start)
    return {
        "attendance": {"total": total_events, "attended": attended, "missed": missed, "percentage": round(attendance_pct, 1)},
        "tasks": {"total": total_tasks, "completed": completed_tasks, "pending": total_tasks - completed_tasks},
        "assignments": {"total": total_assignments, "completed": completed_assignments},
        "exams": {"total": total_exams, "upcoming": upcoming_exams},
        "productivity": productivity,
        "study_hours": study_hours,
        "weekly": {"classes": weekly_classes},
        "monthly": {"classes_attended": monthly_classes_attended, "tasks_completed": monthly_tasks_completed},
    }


# In-memory pending event state per user
_pending_events: dict[str, dict] = {}

def _parse_time_from_text(text: str) -> str:
    m = re.search(r"(\d{1,2})\s*[:.]\s*(\d{2})\s*(am|pm|AM|PM)?", text)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        period = (m.group(3) or "").lower()
        if period == "pm" and hour < 12: hour += 12
        elif period == "am" and hour == 12: hour = 0
        return f"{hour:02d}:{minute:02d}"
    m = re.search(r"(\d{1,2})\s*(am|pm|AM|PM)", text)
    if m:
        hour, period = int(m.group(1)), m.group(2).lower()
        if period == "pm" and hour < 12: hour += 12
        elif period == "am" and hour == 12: hour = 0
        return f"{hour:02d}:00"
    return ""

def _parse_duration_from_text(text: str) -> int:
    m = re.search(r"(\d+)\s*(?:min|minutes|mins?)", text, re.IGNORECASE)
    if m: return int(m.group(1))
    m = re.search(r"(\d+)\s*(?:hr|hour|hours?)", text, re.IGNORECASE)
    if m: return int(m.group(1)) * 60
    return 0


def _handle_pending_event(user_id: str, pending: dict, message: str, today: str) -> dict:
    replied_time = _parse_time_from_text(message)
    replied_duration = _parse_duration_from_text(message)
    title_raw = pending.get("title_raw", pending["title"])
    date_text = pending.get("date_text", "")

    asked_time = pending.get("asked_time", False)
    asked_duration = pending.get("asked_duration", False)

    if not asked_time:
        _pending_events[user_id]["asked_time"] = True
        return {"action": "none", "event": None, "events": None,
                "reply": f"Sure! What time should I schedule the {title_raw} class{date_text}?"}

    if replied_time:
        pending["time"] = replied_time

    title = _clean_title(pending["title"])
    date = pending.get("date") or today
    time_str = pending.get("time") or ""

    if not time_str:
        _pending_events[user_id]["asked_time"] = True
        return {"action": "none", "event": None, "events": None,
                "reply": f"Sure! What time should I schedule the {title} class{date_text}?"}

    if not asked_duration:
        _pending_events[user_id]["asked_duration"] = True
        if replied_duration:
            pending["duration"] = replied_duration
            _pending_events[user_id]["asked_duration"] = True
        else:
            return {"action": "none", "event": None, "events": None,
                    "reply": f"Got it! And how long should the {title} class be (in minutes)?"}

    if replied_duration:
        pending["duration"] = replied_duration

    # Check if user provided a duration value
    duration_min = pending.get("duration", 0) or 0
    if duration_min <= 0:
        _pending_events[user_id]["asked_duration"] = True
        return {"action": "none", "event": None, "events": None,
                "reply": f"How long should the {title} class be (in minutes)?"}

    existing_match = _find_matching_event(user_id, title, date)
    if existing_match:
        del _pending_events[user_id]
        return {"action": "none", "event": None, "events": None,
                "reply": f"A class '{title}' already exists on {date} at {existing_match['time']}. No changes needed."}
    doc = {
        "title": title, "owner_id": user_id,
        "subject": pending.get("subject", ""), "date": date, "time": time_str,
        "reminder_before": pending.get("reminder_before", 15),
        "location": pending.get("location", ""), "notes": pending.get("notes", ""),
        "duration_minutes": duration_min,
    }
    result = events.insert_one(doc)
    doc["_id"] = result.inserted_id
    saved = _to_event_out(doc)
    del _pending_events[user_id]
    dur_str = f" for {duration_min} minutes" if duration_min else ""
    return {"action": "created", "event": saved, "events": None,
            "reply": f"Done! Added '{saved.title}' on {saved.date} at {saved.time}{dur_str}. I'll remind you {saved.reminder_before} min before. 🔔"}


TEMPORAL_WORDS_TITLE = r"\b(?:on|at|for|from|to|in|and|the|a|an|my|every|due|tomorrow|today|yesterday|next|this|last|monday|tuesday|wednesday|thursday|friday|saturday|sunday|morning|afternoon|evening|night|week|month)\b"
JUNK_WORDS = r"\b(?:class|course|lecture|session|new|called|subject|exam|test|task|assignment)\b"

KNOWN_ABBREVIATIONS = {"DBMS", "AI", "ML", "IoT", "ECE", "CS", "IT", "CSE", "ECE", "EEE", "ME", "CE"}

def _normalize_title(title: str) -> str:
    words = title.split()
    result = []
    for w in words:
        upper = w.upper()
        if upper in KNOWN_ABBREVIATIONS:
            result.append(upper)
        else:
            result.append(w[0].upper() + w[1:].lower() if w else w)
    return " ".join(result)

def _clean_title(title: str) -> str:
    cleaned = re.sub(TEMPORAL_WORDS_TITLE, " ", title, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.:-;!?")
    cleaned = re.sub(JUNK_WORDS, " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.:-;!?")
    if not cleaned:
        return "Untitled"
    return _normalize_title(cleaned)


router = APIRouter(prefix="/ai", tags=["ai"])


class ChatBody(BaseModel):
    message: str = Field(..., max_length=5000)


@router.post("/chat", response_model=dict)
@limiter.limit("30/minute")
def chat(body: ChatBody, request: Request, current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["_id"])
    today = datetime.now().strftime("%Y-%m-%d")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    existing = list(events.find({"owner_id": user_id}).sort("date", 1).sort("time", 1))
    events_summary = ", ".join(
        [_format_event_summary(e) for e in existing[:20]]
    ) if existing else "none"

    intent_data = classify_intent(body.message, today, events_summary)
    intent = intent_data.get("intent", "create")
    match_title = intent_data.get("title")
    match_date = intent_data.get("match_date")
    new_reminder = intent_data.get("new_reminder")

    # If user has a pending event and this message looks like a reply (time/duration), handle it
    pending = _pending_events.get(user_id) if not intent or intent in ("create_event", "unknown") else None
    if pending:
        return _handle_pending_event(user_id, pending, body.message, today)

    # Clear stale pending events
    if _pending_events.get(user_id):
        del _pending_events[user_id]

    if intent == "greeting":
        return {"action": "none", "event": None, "events": None, "reply": "Hello! How can I help you today?"}

    if intent == "help":
        return {
            "action": "none", "event": None, "events": None,
            "reply": (
                "Here's what I can do for you:\n\n"
                "📅 **Create** — Add a new class or event\n"
                "🗑️ **Delete** — Remove a class\n"
                "✏️ **Update** — Change time, date, or location\n"
                "📋 **Timetable** — Show today's or tomorrow's schedule\n"
                "⏭️ **Next Class** — What's your next class\n"
                "📊 **Attendance** — Your attendance breakdown\n"
                "📝 **Assignments** — Pending and overdue assignments\n"
                "🎓 **Exams** — Upcoming exams with countdown\n"
                "📈 **Statistics** — Study hours, productivity, weekly stats\n"
                "🏆 **Rewards** — XP, points, level, streak\n"
                "⏰ **Reminders** — Change reminder time before a class\n\n"
                "Just type what you'd like to do in natural language!"
            ),
        }

    if intent == "next_class_query":
        upcoming = [
            e for e in existing
            if e["date"] > today or (e["date"] == today and e["time"] > datetime.now().strftime("%H:%M"))
        ]
        if upcoming:
            nxt = upcoming[0]
            reply = (
                f"Your next class is **{nxt['title']}**"
                f"{' (' + nxt['subject'] + ')' if nxt.get('subject') else ''}"
                f" on {nxt['date']} at {nxt['time']}"
                f"{', in ' + nxt['location'] if nxt.get('location') else ''}."
            )
        else:
            reply = "You have no upcoming classes."
        return {"action": "none", "event": None, "events": None, "reply": reply}

    if intent == "timetable_query":
        today_events = [e for e in existing if e["date"] == today]
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        tomorrow_events = [e for e in existing if e["date"] == tomorrow]

        parts = []
        if today_events:
            lines = [f"• **{_format_event_summary(e)}**" for e in today_events]
            parts.append(f"**Today's classes** ({len(today_events)}):\n" + "\n".join(lines))
        else:
            parts.append("**Today:** No classes today.")

        if tomorrow_events:
            day_name = (datetime.now() + timedelta(days=1)).strftime("%A")
            lines = [f"• **{_format_event_summary(e)}**" for e in tomorrow_events]
            parts.append(f"**{day_name}'s classes** ({len(tomorrow_events)}):\n" + "\n".join(lines))

        reply = "\n\n".join(parts) if parts else "You have no classes scheduled."
        events_out = [_to_event_out(e) for e in today_events + tomorrow_events]
        return {"action": "none", "event": None, "events": events_out, "reply": reply}

    if intent == "attendance_query":
        groups = {}
        for e in existing:
            title = e.get("title", "Unknown")
            if title not in groups:
                groups[title] = {"attended": 0, "missed": 0, "total": 0}
            groups[title]["total"] += 1
            if e.get("attended") is True:
                groups[title]["attended"] += 1
            elif e.get("attended") is False:
                groups[title]["missed"] += 1

        subjects_with_data = []
        for title, data in groups.items():
            marked = data["attended"] + data["missed"]
            if marked > 0:
                pct = round(data["attended"] / marked * 100, 1)
                subjects_with_data.append({"title": title, "attended": data["attended"], "missed": data["missed"], "total": data["total"], "pct": pct})
        subjects_with_data.sort(key=lambda x: x["pct"])

        if subjects_with_data:
            total_attended = sum(s["attended"] for s in subjects_with_data)
            total_missed = sum(s["missed"] for s in subjects_with_data)
            overall_pct = round(total_attended / max(total_attended + total_missed, 1) * 100)
            parts = [f"**Overall attendance:** {overall_pct}%\n"]
            for s in subjects_with_data:
                icon = "🟢" if s["pct"] >= 85 else "🟡" if s["pct"] >= 70 else "🔴"
                parts.append(f"{icon} **{s['title']}**: {s['attended']}/{s['attended']+s['missed']} ({s['pct']}%)")
            reply = "\n".join(parts)
        else:
            reply = "No attendance data yet. Mark your classes to start tracking."
        return {"action": "none", "event": None, "events": None, "reply": reply}

    if intent == "assignment_query":
        pending = list(assignments.find({"owner_id": user_id, "completed": False}).sort("due_date", 1))
        if pending:
            overdue = [a for a in pending if a.get("due_date", "") < today]
            due_soon = [a for a in pending if today <= a.get("due_date", "") <= (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")]
            future_pending = [a for a in pending if a.get("due_date", "") > (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")]
            parts = [f"You have **{len(pending)} pending assignment{'s' if len(pending) != 1 else ''}**:\n"]
            if overdue:
                overdue_lines = [f"• 🔴 {a['title']} (was due {a['due_date']})" for a in overdue[:5]]
                parts.append(f"**Overdue** ({len(overdue)}):\n" + "\n".join(overdue_lines))
            if due_soon:
                soon_lines = [f"• 🟡 {a['title']} (due {a['due_date']})" for a in due_soon[:5]]
                parts.append(f"**Due this week** ({len(due_soon)}):\n" + "\n".join(soon_lines))
            if future_pending:
                future_lines = [f"• {a['title']} (due {a['due_date']})" for a in future_pending[:3]]
                parts.append(f"**Upcoming** ({len(future_pending)}):\n" + "\n".join(future_lines))
            reply = "\n\n".join(parts)
        else:
            reply = "You have no pending assignments. All caught up! 🎉"
        return {"action": "none", "event": None, "events": None, "reply": reply}

    if intent == "exam_query":
        upcoming_exams = list(exams.find({
            "owner_id": user_id, "completed": False, "date": {"$gte": today}
        }).sort("date", 1).sort("time", 1))
        if upcoming_exams:
            nearest = upcoming_exams[0]
            exam_date = datetime.strptime(nearest["date"], "%Y-%m-%d")
            days_until = (exam_date - datetime.now()).days
            countdown = f"in {days_until} day{'s' if days_until != 1 else ''}" if days_until > 0 else "today"
            reply = (
                f"Your nearest exam is **{nearest['title']}**"
                f"{' (' + nearest['subject'] + ')' if nearest.get('subject') else ''}"
                f" — {nearest['date']} at {nearest['time']}"
                f"{', ' + nearest['location'] if nearest.get('location') else ''}"
                f" ({nearest.get('exam_type', 'exam')})."
                f"\n\nThat's **{countdown}**."
            )
            if len(upcoming_exams) > 1:
                more = upcoming_exams[1]
                reply += f"\n\nAfter that: **{more['title']}** on {more['date']}."
        else:
            reply = "You have no upcoming exams. Great news!"
        return {"action": "none", "event": None, "events": None, "reply": reply}

    if intent == "statistics_query":
        stats_data = _get_stats_dashboard(user_id)
        parts = [
            f"📊 **Your Study Dashboard**\n",
            f"📚 **Attendance:** {stats_data['attendance']['percentage']}% "
            f"({stats_data['attendance']['attended']} attended, {stats_data['attendance']['missed']} missed)",
        ]
        if stats_data['study_hours']:
            parts.append(f"⏱️ **Study Hours:** {stats_data['study_hours']}h estimated")
        parts.append(f"📝 **Tasks:** {stats_data['tasks']['completed']}/{stats_data['tasks']['total']} completed")
        parts.append(f"📋 **Assignments:** {stats_data['assignments']['completed']}/{stats_data['assignments']['total']} completed")
        if stats_data['exams']['upcoming']:
            parts.append(f"🎓 **Upcoming Exams:** {stats_data['exams']['upcoming']}")
        parts.append(f"⭐ **Productivity Score:** {stats_data['productivity']}/100")
        if stats_data['weekly']['classes']:
            this_week = sum(stats_data['weekly']['classes'])
            parts.append(f"📅 **This Week:** {this_week} classes attended")
        if stats_data['monthly']['classes_attended']:
            parts.append(f"🗓️ **This Month:** {stats_data['monthly']['classes_attended']} classes, "
                        f"{stats_data['monthly']['tasks_completed']} tasks done")
        reply = "\n".join(parts)
        return {"action": "none", "event": None, "events": None, "reply": reply}

    if intent == "rewards_query":
        return {"action": "none", "event": None, "events": None, "reply": "You can check your rewards, XP, and level on the Rewards tab! 🏆"}

    if intent == "delete_event":
        if not match_title:
            return {"action": "none", "event": None, "events": None, "reply": "Which class would you like to delete? Please mention the class name."}
        doc = _find_matching_event(user_id, match_title, match_date)
        if not doc:
            return {"action": "none", "event": None, "events": None, "reply": f"I couldn't find a class matching '{match_title}'{' on ' + match_date if match_date else ''}."}
        deleted = _to_event_out(doc)
        events.delete_one({"_id": doc["_id"]})
        return {
            "action": "deleted",
            "event": deleted,
            "events": None,
            "reply": f"Deleted '{deleted.title}' on {deleted.date} at {deleted.time}.",
        }

    if intent == "reminder_management":
        if not match_title:
            return {"action": "none", "event": None, "events": None, "reply": "Which class would you like to set a reminder for? Please mention the class name and the minutes (e.g., 'Remind me 30 min before Math')."}
        doc = _find_matching_event(user_id, match_title, match_date)
        if not doc:
            return {"action": "none", "event": None, "events": None, "reply": f"I couldn't find a class matching '{match_title}'. Please check your schedule."}
        reminder_minutes = new_reminder if new_reminder else 15
        events.update_one({"_id": doc["_id"]}, {"$set": {"reminder_before": reminder_minutes}})
        updated = events.find_one({"_id": doc["_id"]})
        return {
            "action": "updated",
            "event": _to_event_out(updated),
            "events": None,
            "reply": f"Updated reminder for '{updated['title']}' to {reminder_minutes} minutes before class. 🔔",
        }

    if intent == "update_event":
        parsed = parse_event_from_text(body.message, today)
        doc = None
        if match_title:
            doc = _find_matching_event(user_id, match_title, match_date)
        else:
            title_from_parse = (parsed.get("title") or "").strip()
            if title_from_parse:
                doc = _find_matching_event(user_id, title_from_parse)
        if not doc:
            return {"action": "none", "event": None, "events": None, "reply": f"I couldn't find a class matching '{match_title or parsed.get('title', '')}'. Please check your schedule and try again."}

        update_fields = {}
        new_date = parsed.get("date")
        new_time = parsed.get("time")
        new_location = parsed.get("location", "")
        new_reminder_val = parsed.get("reminder_before")
        if new_date and new_date != today:
            update_fields["date"] = new_date
        if new_time and new_time != "09:00":
            update_fields["time"] = new_time
        if new_location:
            update_fields["location"] = new_location
        if new_reminder_val and new_reminder_val != 15:
            update_fields["reminder_before"] = int(new_reminder_val)
        if not update_fields:
            return {"action": "none", "event": None, "events": None, "reply": f"I found '{doc['title']}' but couldn't determine what to change. Please specify the new time or date."}
        events.update_one({"_id": doc["_id"]}, {"$set": update_fields})
        updated = events.find_one({"_id": doc["_id"]})
        changes = []
        if "time" in update_fields:
            changes.append(f"time to {updated['time']}")
        if "date" in update_fields:
            changes.append(f"date to {updated['date']}")
        if "location" in update_fields:
            changes.append(f"location to {updated['location']}")
        if "reminder_before" in update_fields:
            changes.append(f"reminder to {updated['reminder_before']} min")
        return {
            "action": "updated",
            "event": _to_event_out(updated),
            "events": None,
            "reply": f"Updated '{updated['title']}': {', '.join(changes)}.",
        }

    if intent == "create_event":
        # Fresh create event — parse normally
        parsed = parse_event_from_text(body.message, today)
        parsed_title = _clean_title(parsed.get("title") or "")
        parsed_date = parsed.get("date") or today
        parsed_time = parsed.get("time") or ""
        parsed_duration = _parse_duration_from_text(body.message) or parsed.get("duration_minutes") or 0

        # Check original message for explicit time — don't trust Gemini defaults
        has_raw_time = _parse_time_from_text(body.message)
        user_mentioned_time = bool(has_raw_time)

        # If no time specified by user, store pending and ask
        if not user_mentioned_time:
            title = parsed_title or "Untitled"
            date_str = parsed_date
            raw_title = title
            date_text = ""
            if date_str and date_str == (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"):
                date_text = " tomorrow"
            elif date_str and date_str != datetime.now().strftime("%Y-%m-%d"):
                date_text = f" on {date_str}"
            _pending_events[user_id] = {
                "title": title, "title_raw": raw_title,
                "subject": parsed.get("subject", ""), "date": date_str,
                "reminder_before": int(parsed.get("reminder_before") or 15),
                "location": parsed.get("location", ""), "notes": parsed.get("notes", ""),
                "date_text": date_text, "asked_time": True,
                "duration": parsed_duration,
            }
            return {"action": "none", "event": None, "events": None,
                    "reply": f"Sure! What time should I schedule the {title} class{date_text}?"}

        try:
            event_in = EventCreate(
                title=parsed_title or "Untitled",
                subject=(parsed.get("subject") or "").strip(),
                date=parsed_date,
                time=parsed_time,
                reminder_before=int(parsed.get("reminder_before") or 15),
                location=(parsed.get("location") or "").strip(),
                notes=(parsed.get("notes") or "").strip(),
                duration_minutes=parsed_duration or None,
            )
        except ValidationError:
            return {
                "action": "none", "event": None, "events": None,
                "reply": "I couldn't understand the date or time. Try something like \"Add Math class tomorrow at 10am\".",
            }

        title = event_in.title
        date = event_in.date
        existing_match = _find_matching_event(user_id, title, date)
        if existing_match:
            update_fields = {}
            if event_in.time != existing_match.get("time"):
                update_fields["time"] = event_in.time
            if event_in.location and event_in.location != existing_match.get("location"):
                update_fields["location"] = event_in.location
            if event_in.reminder_before != existing_match.get("reminder_before", 15):
                update_fields["reminder_before"] = event_in.reminder_before
            if update_fields:
                events.update_one({"_id": existing_match["_id"]}, {"$set": update_fields})
                updated = events.find_one({"_id": existing_match["_id"]})
                changes = []
                if "time" in update_fields:
                    changes.append(f"time to {updated['time']}")
                if "location" in update_fields:
                    changes.append(f"location to {updated['location']}")
                if "reminder_before" in update_fields:
                    changes.append(f"reminder to {updated['reminder_before']} min")
                return {
                    "action": "updated", "event": _to_event_out(updated), "events": None,
                    "reply": f"A class '{title}' already exists on {date}. Updated: {', '.join(changes)}.",
                }
            return {
                "action": "none", "event": None, "events": None,
                "reply": f"A class '{title}' already exists on {date} at {existing_match['time']}. No changes needed.",
            }
        doc = event_in.dict()
        doc["title"] = title
        doc["owner_id"] = user_id
        result = events.insert_one(doc)
        doc["_id"] = result.inserted_id
        saved = _to_event_out(doc)
        return {
            "action": "created", "event": saved, "events": None,
            "reply": f"Added '{saved.title}' on {saved.date} at {saved.time}. I'll remind you {saved.reminder_before} min before. 🔔",
        }

    return {"action": "none", "event": None, "events": None, "reply": "I'm not sure what you mean. Try asking me to add, update, delete, or check your classes."}
