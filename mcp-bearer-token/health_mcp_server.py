import os
import sqlite3
from datetime import datetime
from typing import Annotated, Optional

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, APIRouter
from pydantic import BaseModel, Field

# Assuming FastMCP is imported correctly from the starter
from mcp.server.fastmcp import FastMCP

# Load environment variables
load_dotenv()

# Environment variable validation
AUTH_TOKEN = os.getenv("AUTH_TOKEN")
if not AUTH_TOKEN:
    raise ValueError("AUTH_TOKEN environment variable not set. Please set it in your .env file or system environment.")

MY_NUMBER = os.getenv("MY_NUMBER")
if not MY_NUMBER:
    raise ValueError("MY_NUMBER environment variable not set. Please set it in your .env file or system environment.")

# SQLite DB setup
DB_FILE = "health_data.db"
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS reminders (
    user_id TEXT,
    reminder_type TEXT,
    reminder_time TEXT,
    created_at TIMESTAMP,
    PRIMARY KEY (user_id, reminder_type)
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS progress (
    user_id TEXT,
    category TEXT,
    value INTEGER,
    last_updated TIMESTAMP
)
""")
conn.commit()

# Initialize FastAPI and FastMCP
app = FastAPI()
mcp = FastMCP("Health Wellness Bot")
mcp_router = APIRouter(prefix="/mcp")

# Register tools with FastMCP
# Validation tool
@mcp.tool(description="Validate the MCP connection")
async def validate() -> str:
    return MY_NUMBER  # Returns phone in {country_code}{number} format

# Set reminder tool
class SetReminderInput(BaseModel):
    reminder_type: Annotated[str, Field(description="Type of reminder, e.g., 'hydration', 'exercise'")]
    reminder_time: Annotated[str, Field(description="Time/frequency, e.g., 'every 2 hours'")]

@mcp.tool(description="Set a personalized health reminder")
async def set_reminder(
    input: SetReminderInput,
    puch_user_id: Annotated[Optional[str], Header(description="Unique Puch user ID")] = None
) -> str:
    if not puch_user_id:
        raise HTTPException(status_code=400, detail="puch_user_id required")
    cursor.execute("""
    INSERT OR REPLACE INTO reminders (user_id, reminder_type, reminder_time, created_at)
    VALUES (?, ?, ?, ?)
    """, (puch_user_id, input.reminder_type, input.reminder_time, datetime.now()))
    conn.commit()
    return f"Reminder set for {input.reminder_type} at {input.reminder_time}!"

# Get reminders tool
@mcp.tool(description="Get user's active reminders and progress updates")
async def get_reminders(
    puch_user_id: Annotated[Optional[str], Header(description="Unique Puch user ID")] = None
) -> str:
    if not puch_user_id:
        raise HTTPException(status_code=400, detail="puch_user_id required")
    cursor.execute("SELECT * FROM reminders WHERE user_id = ?", (puch_user_id,))
    reminders = cursor.fetchall()
    if not reminders:
        return "No active reminders. Set one with 'set_reminder'!"
    output = "Your reminders:\n"
    for rem in reminders:
        output += f"- {rem[1]} at {rem[2]} (set on {rem[3]})\n"
    time_since = datetime.now() - datetime.fromisoformat(reminders[0][3])
    output += f"Progress update: You've been on track for {time_since.days} days!"
    return output

# Wellness tip tool
@mcp.tool(description="Get personalized wellness advice")
async def get_wellness_tip(
    category: Annotated[str, Field(description="Category, e.g., 'nutrition', 'stress', 'workout'")]
) -> str:
    tips = {
        "nutrition": "Eat balanced meals with veggies, proteins, and whole grains. Try adding spinach to your salad for iron!",
        "stress": "Practice deep breathing: Inhale for 4 seconds, hold for 4, exhale for 4. Repeat 5 times.",
        "workout": "Quick home workout: 10 push-ups, 20 squats, 30-second plank. No equipment needed!"
    }
    return tips.get(category, "Tip not found for that category.")

# Track progress tool
class TrackProgressInput(BaseModel):
    category: Annotated[str, Field(description="Category to track, e.g., 'steps', 'water'")]
    value: Annotated[int, Field(description="Value to add, e.g., 8 glasses")]

@mcp.tool(description="Track and update health progress")
async def track_progress(
    input: TrackProgressInput,
    puch_user_id: Annotated[Optional[str], Header(description="Unique Puch user ID")] = None
) -> str:
    if not puch_user_id:
        raise HTTPException(status_code=400, detail="puch_user_id required")
    cursor.execute("""
    INSERT OR REPLACE INTO progress (user_id, category, value, last_updated)
    VALUES (?, ?, ?, ?)
    """, (puch_user_id, input.category, input.value, datetime.now()))
    conn.commit()
    return f"Progress updated: {input.value} for {input.category}. Great job!"

# Bearer token authentication middleware
@app.middleware("http")
async def add_auth(request, call_next):
    if request.url.path.startswith("/mcp") and request.headers.get("authorization") != f"Bearer {AUTH_TOKEN}":
        raise HTTPException(status_code=401, detail="Invalid token")
    response = await call_next(request)
    return response

# Include the MCP router (assuming FastMCP integrates tools into the router)
app.include_router(mcp_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8086)