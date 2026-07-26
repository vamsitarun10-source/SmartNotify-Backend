import os
import json
import re
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from google import genai

_client = None
_executor = ThreadPoolExecutor(max_workers=2)


def _get_client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    return _client


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    return json.loads(text)


def _parse_time(text: str) -> str:
    m = re.search(r"(\d{1,2})\s*[:.]\s*(\d{2})\s*(am|pm)?", text, re.IGNORECASE)
    if m:
        hour, minute, period = int(m.group(1)), int(m.group(2)), (m.group(3) or "").lower()
        if period == "pm" and hour < 12:
            hour += 12
        elif period == "am" and hour == 12:
            hour = 0
        return f"{hour:02d}:{minute:02d}"
    m = re.search(r"(\d{1,2})\s*(am|pm)", text, re.IGNORECASE)
    if m:
        hour, period = int(m.group(1)), m.group(2).lower()
        if period == "pm" and hour < 12:
            hour += 12
        elif period == "am" and hour == 12:
            hour = 0
        return f"{hour:02d}:00"
    return ""


def _parse_date(text: str, today: str) -> str:
    base = datetime.strptime(today, "%Y-%m-%d")
    lower = text.lower()
    if "tomorrow" in lower:
        return (base + timedelta(days=1)).strftime("%Y-%m-%d")
    if "today" in lower:
        return today
    if "next week" in lower:
        return (base + timedelta(days=7)).strftime("%Y-%m-%d")
    weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    for i, day in enumerate(weekdays):
        if day in lower:
            days_ahead = (i - base.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            if re.search(rf"\bnext\s+{day}", lower):
                days_ahead += 7
            return (base + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    months_map = {
        "january":1,"february":2,"march":3,"april":4,"may":5,"june":6,
        "july":7,"august":8,"september":9,"october":10,"november":11,"december":12,
        "jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
        "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12
    }
    for name, num in months_map.items():
        m = re.search(rf"\b{name}\s+(\d{{1,2}})\b", lower)
        if m:
            day = int(m.group(1))
            year = base.year
            try:
                parsed = datetime(year, num, day)
                if parsed < base:
                    parsed = datetime(year + 1, num, day)
                return parsed.strftime("%Y-%m-%d")
            except ValueError:
                pass

    m = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if m:
        return m.group(1)
    return ""


def _parse_reminder(text: str) -> int:
    m = re.search(r"remind(?:\s+me)?\s+(\d+)\s*(min|minutes|hr|hours?)", text, re.IGNORECASE)
    if m:
        val = int(m.group(1))
        unit = m.group(2).lower()
        if unit.startswith("hr") or unit.startswith("hour"):
            return val * 60
        return val
    m = re.search(r"(\d+)\s*min(?:ute)?s?\s+before", text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return 15


def _parse_location(text: str) -> str:
    m = re.search(r"\b(?:in|at|room)\s+((?:room\s*)?[\w\s]+?)(?:\s*,|\s+remind|\s+notes|\s+tomorrow|\s+on\s+\w|\s*$)", text, re.IGNORECASE)
    if m:
        loc = m.group(1).strip()
        if re.match(r"^\d{1,2}(:\d{2})?\s*(am|pm)?$", loc, re.IGNORECASE):
            return ""
        return loc
    return ""


TEMPORAL_WORDS = r"\b(?:tomorrow|today|yesterday|monday|tuesday|wednesday|thursday|friday|saturday|sunday|next\s+\w+|this\s+(?:week|month|evening|morning|afternoon|night)|morning|afternoon|evening|night)\b"
MONTH_NAMES = r"\b(?:january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s*\d{0,2}\b"
TIME_PATTERN = r"\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM)?"
DATE_PATTERN = r"\d{4}-\d{2}-\d{2}"

def _fallback_parse(message: str, today: str) -> dict:
    lower = message.lower()
    time_str = _parse_time(message) or ""
    date_str = _parse_date(message, today) or today
    reminder = _parse_reminder(message)
    location = _parse_location(message)

    title = message

    title = re.sub(
        rf"(?:add|schedule|create|set|plan)\s+(?:a\s+|an\s+|my\s+)?",
        "", title, flags=re.IGNORECASE
    )
    title = re.sub(rf"{TEMPORAL_WORDS}", "", title, flags=re.IGNORECASE)
    title = re.sub(rf"{MONTH_NAMES}", "", title, flags=re.IGNORECASE)
    title = re.sub(
        rf"(?:on|at|by|from)\s+{TIME_PATTERN}(?:\s*(?:-|to)\s*{TIME_PATTERN})?",
        "", title, flags=re.IGNORECASE
    )
    title = re.sub(rf"(?:on|at|by|for)\s+{DATE_PATTERN}", "", title, flags=re.IGNORECASE)
    title = re.sub(rf"{TIME_PATTERN}", "", title, flags=re.IGNORECASE)
    title = re.sub(rf"{DATE_PATTERN}", "", title, flags=re.IGNORECASE)
    title = re.sub(
        r"remind(?:\s+me)?\s+\d+\s*(?:min|minutes|hr|hours?).*",
        "", title, flags=re.IGNORECASE
    )
    title = re.sub(
        r"remind\s+\d+\s*min(?:ute)?s?\s+before",
        "", title, flags=re.IGNORECASE
    )
    title = re.sub(
        r"\b(?:in|at|room)\s+(?:room\s*)?[\w\s]+?(?=\s*,|\s+remind|\s+notes|\s+tomorrow|\s+on\s+\w|\s*$)",
        "", title, flags=re.IGNORECASE
    )
    title = re.sub(r"\s+(?:on|at|from|to|in|and|by|for)$", "", title, flags=re.IGNORECASE)
    title = re.sub(r"^(?:on|at|from|to|in|and|by|for)\s+", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\bclass\b", " ", title, flags=re.IGNORECASE)
    title = re.sub(r"\s+", " ", title).strip(" ,.:-")
    if not title:
        title = message

    return {
        "title": title,
        "subject": "",
        "date": date_str,
        "time": time_str,
        "reminder_before": reminder,
        "location": location,
        "notes": "",
    }


def parse_event_from_text(message: str, today: str) -> dict:
    client = _get_client()
    sys = (
        "You are a class scheduler. Convert the user message into JSON with keys: "
        "title(str, MUST NOT contain temporal words like today/tomorrow/yesterday/day-names, MUST NOT contain time expressions like 10am/10:00, MUST NOT contain action words like add/create/schedule/class), "
        "subject(str, may be empty), date(YYYY-MM-DD using TODAY if relative), "
        "time(str: HH:MM 24h OR empty string if no time mentioned), reminder_before(int minutes before class, default 15), "
        "location(str, may be empty), notes(str, may be empty). Reply with ONLY JSON, no markdown."
        "Example: 'create physics class tomorrow at 9am' -> {\"title\":\"Physics\",\"subject\":\"\",\"date\":\"<tomorrow>\",\"time\":\"09:00\",\"reminder_before\":15,\"location\":\"\",\"notes\":\"\"}"
    )
    def _call():
        return client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[sys, f"TODAY={today}\nUSER: {message}"],
        )
    try:
        resp = _executor.submit(_call).result(timeout=3)
        return _extract_json(resp.text)
    except Exception:
        return _fallback_parse(message, today)


def _extract_title_after_keywords(text: str, keywords: list) -> str:
    for kw in keywords:
        if kw in ("before",):
            m = re.search(rf"\b{kw}\s+(?:my\s+|the\s+|a\s+|an\s+)?(.+?)(?:\s+(?:to|on|at|for|from|tomorrow|today|every|due)\b|$)", text, re.IGNORECASE)
        else:
            m = re.search(rf"\b{kw}\b\s+(?:my\s+|the\s+|a\s+|an\s+)?(.+?)(?:\s+(?:to|on|at|for|from|tomorrow|today|every|due|class)\b|$)", text, re.IGNORECASE)
        if m:
            title = m.group(1).strip(" ,.:-")
            title = re.sub(r"\b(?:class|course|lecture|session)s?\b$", "", title, flags=re.IGNORECASE).strip()
            title = re.sub(r"\b(?:remind|me|minutes?|mins?|hours?|hrs?|before|after|at|the|a|an|my)\b", " ", title, flags=re.IGNORECASE)
            title = re.sub(r"\b\d+\b", "", title)
            title = re.sub(r"\s+", " ", title).strip()
            if title:
                return title
    return ""


def classify_intent_fallback(message: str) -> dict:
    lower = message.lower()

    greetings = [
        "hello", "hi", "hey", "good morning", "good afternoon", "good evening",
        "thanks", "thank you", "thanks!", "thank you!", "how are you", "how are you?",
        "what's up", "sup", "yo", "hii", "hii!", "helloo", "helloo!",
    ]
    clean = lower.strip(" .,!?")
    if clean in greetings or clean in [g.strip(".!?") for g in greetings]:
        return {"intent": "greeting", "title": None, "match_date": None, "new_reminder": None}

    if any(w in lower for w in ["delete", "remove", "cancel"]):
        title = _extract_title_after_keywords(lower, ["delete", "remove", "cancel"])
        return {"intent": "delete_event", "title": title, "match_date": None, "new_reminder": None}

    if any(w in lower for w in ["move", "change", "update", "edit", "reschedule"]):
        title = _extract_title_after_keywords(lower, ["move", "change", "update", "edit", "reschedule"])
        return {"intent": "update_event", "title": title, "match_date": None, "new_reminder": None}

    if "attendance" in lower:
        return {"intent": "attendance_query", "title": None, "match_date": None, "new_reminder": None}

    if any(w in lower for w in ["assignment", "assignments", "homework", "due", "pending work"]):
        return {"intent": "assignment_query", "title": None, "match_date": None, "new_reminder": None}

    if any(w in lower for w in ["exam", "exams", "test", "tests"]):
        return {"intent": "exam_query", "title": None, "match_date": None, "new_reminder": None}

    if any(w in lower for w in ["timetable", "my classes", "my class", "what classes", "my schedule", "today's schedule", "today classes", "show today", "do i have today"]):
        return {"intent": "timetable_query", "title": None, "match_date": None, "new_reminder": None}

    has_next_keywords = ["next class", "next event", "upcoming class", "what's next", "what is next", "my next class", "coming up"]
    if any(w in lower for w in has_next_keywords) or (lower.strip() in ("next",)):
        return {"intent": "next_class_query", "title": None, "match_date": None, "new_reminder": None}

    if any(w in lower for w in ["help", "what can you do", "commands", "how to use", "capabilities", "features", "guide me", "what you can do"]):
        return {"intent": "help", "title": None, "match_date": None, "new_reminder": None}

    if "reward" in lower or "xp" in lower or "streak" in lower or "points" in lower or "level" in lower:
        return {"intent": "rewards_query", "title": None, "match_date": None, "new_reminder": None}

    if any(w in lower for w in ["statistics", "stats", "study stats", "my stats", "productivity", "dashboard"]):
        return {"intent": "statistics_query", "title": None, "match_date": None, "new_reminder": None}

    if any(w in lower for w in ["remind", "reminder"]):
        if any(w in lower for w in ["change", "set", "update", "to", "before"]):
            before_match = re.search(r"\bbefore\s+(?:my\s+|the\s+|a\s+|an\s+)?(.+?)$", lower)
            if before_match:
                raw_title = before_match.group(1).strip(" ,.:-")
                raw_title = re.sub(r"\b(?:class|course|lecture|session)s?\b", " ", raw_title, flags=re.IGNORECASE)
                raw_title = re.sub(r"\s+", " ", raw_title).strip()
                title = raw_title
            else:
                title = _extract_title_after_keywords(lower, ["remind", "reminder", "before"])
            m = re.search(r"(\d+)\s*(?:min|minutes)", lower)
            new_reminder = int(m.group(1)) if m else None
            return {"intent": "reminder_management", "title": title, "match_date": None, "new_reminder": new_reminder}
        title = _extract_title_after_keywords(lower, ["remind", "reminder", "before"])
        return {"intent": "reminder_management", "title": title, "match_date": None, "new_reminder": None}

    add_keywords = ["add", "schedule", "create", "set", "plan", "new"]
    if any(w in lower.split() for w in add_keywords):
        return {"intent": "create_event", "title": None, "match_date": None, "new_reminder": None}

    has_date = any(w in lower for w in ["today", "tomorrow", "next week", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"])
    has_time = bool(re.search(r"\d{1,2}\s*(?::\d{2})?\s*(?:am|pm)", lower, re.IGNORECASE))
    if has_date or has_time:
        return {"intent": "create_event", "title": None, "match_date": None, "new_reminder": None}

    return {"intent": "unknown", "title": None, "match_date": None, "new_reminder": None}


def classify_intent(message: str, today: str, events_summary: str = "") -> dict:
    fallback = classify_intent_fallback(message)
    if fallback["intent"] in ("greeting", "help"):
        return fallback

    client = _get_client()
    sys = (
        "You are a smart class scheduler. Classify the user's message into an intent.\n\n"
        "INTENTS:\n"
        "- greeting: Simple greetings, hellos, thanks, or non-scheduler messages\n"
        "- help: Asking for help, available commands, how to use the assistant\n"
        "- create_event: Adding a new class/event/assignment\n"
        "- delete_event: Removing an event\n"
        "- update_event: Modifying an existing event (changing time, date, location)\n"
        "- attendance_query: Asking about attendance (overview, summary, worst subject, missed classes)\n"
        "- assignment_query: Asking about assignments (pending, due, upcoming)\n"
        "- exam_query: Asking about exams (nearest, upcoming)\n"
        "- timetable_query: Asking about schedule, timetable, today's/tomorrow's classes\n"
        "- next_class_query: Asking about next/upcoming class\n"
        "- statistics_query: Asking about study stats, productivity, dashboard data\n"
        "- rewards_query: Asking about XP, points, level, streak\n"
        "- reminder_management: Changing reminder time before an event\n"
        "- unknown: Message that doesn't match any intent\n\n"
        "Return ONLY JSON:\n"
        '{"intent":"...", "title":"event title keyword to match or null", '
        '"match_date":"YYYY-MM-DD or null", "new_reminder":int or null}\n\n'
        "RULES:\n"
        "- For create_event: title can be null (it will be parsed separately)\n"
        "- For update_event/delete_event/reminder_management: title should be the keyword to match (e.g. 'math', 'chemistry')\n"
        "- match_date helps narrow down when multiple events share a title\n"
        "- new_reminder is only for reminder_management intent"
    )
    contents = f"TODAY={today}\nUSER: {message}"
    if events_summary:
        contents += f"\nEXISTING_EVENTS: {events_summary}"
    def _call():
        return client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[sys, contents],
        )
    try:
        resp = _executor.submit(_call).result(timeout=3)
        result = _extract_json(resp.text)
        if result.get("intent") in ("create_event",) and fallback["intent"] not in ("unknown",):
            return fallback
        if fallback["intent"] not in ("unknown",) and fallback["intent"] != result.get("intent"):
            return fallback
        return result
    except Exception:
        return fallback