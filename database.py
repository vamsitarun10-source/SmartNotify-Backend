import os

from pymongo import MongoClient, ASCENDING

# load_dotenv() is called in main.py — no need to call it here

client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"))
db = client[os.getenv("DATABASE_NAME", "classreminder")]
users = db.users
events = db.events
timetable = db.timetable
tasks = db.tasks
assignments = db.assignments
exams = db.exams
calendar_events = db.calendar_events
notes = db.notes
rewards = db.rewards

# Create indexes (ensureIndex is idempotent — only creates if missing)
events.create_index([("owner_id", ASCENDING)])
events.create_index([("owner_id", ASCENDING), ("date", ASCENDING), ("time", ASCENDING)])
timetable.create_index([("owner_id", ASCENDING)])
timetable.create_index([("owner_id", ASCENDING), ("day_of_week", ASCENDING)])
tasks.create_index([("owner_id", ASCENDING)])
tasks.create_index([("owner_id", ASCENDING), ("due_date", ASCENDING)])
assignments.create_index([("owner_id", ASCENDING)])
assignments.create_index([("owner_id", ASCENDING), ("due_date", ASCENDING)])
exams.create_index([("owner_id", ASCENDING)])
exams.create_index([("owner_id", ASCENDING), ("date", ASCENDING), ("time", ASCENDING)])
calendar_events.create_index([("owner_id", ASCENDING)])
calendar_events.create_index([("owner_id", ASCENDING), ("date", ASCENDING)])
notes.create_index([("owner_id", ASCENDING)])
rewards.create_index([("owner_id", ASCENDING)], unique=True)
users.create_index([("email", ASCENDING)], unique=True)
