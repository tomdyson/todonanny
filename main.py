import json
import os
import re
import time
from pathlib import Path
from typing import List
from uuid import UUID

import llm
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import database

# Get the directory where main.py is located
BASE_DIR = Path(__file__).resolve().parent

# Load environment variables from .env file
load_dotenv(BASE_DIR / ".env", override=True)

# Initialize FastAPI app
app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Serve index.html at root - this needs to be before static file mounting
@app.get("/")
async def read_root():
    return FileResponse("index.html")


# Mount the dist directory for CSS files
app.mount("/dist", StaticFiles(directory="dist"), name="dist")

# Serve static files (like paris-figure.jpg)
app.mount("/static", StaticFiles(directory="."), name="static")

# Update image src in index.html to use /static prefix
# <img src="/static/paris-figure.jpg" ...>


# Pydantic models for request/response
class TaskRequest(BaseModel):
    description: str
    start_time: str


class Task(BaseModel):
    start_time: str
    end_time: str
    description: str


class TaskResponse(BaseModel):
    tasks: List[Task]
    list_id: str


class TaskUpdateRequest(BaseModel):
    completed: bool


class TaskWithCompletion(BaseModel):
    start_time: str
    end_time: str
    description: str
    completed: bool = False


class ReplanRequest(BaseModel):
    list_id: str
    tweak_feedback: str
    tasks: List[TaskWithCompletion]


# Get environment variables
MODEL_NAME = os.getenv("LLM_MODEL", "gpt-3.5-turbo")
API_KEY = os.getenv("LLM_API_KEY")


def strip_markdown_code_blocks(text: str) -> str:
    """Remove markdown code blocks from text, leaving only the content."""
    # Remove markdown code blocks (```json ... ``` or ``` ... ```)
    text = re.sub(r"^```(?:json)?\s*\n?", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n?```\s*$", "", text, flags=re.MULTILINE)
    return text.strip()


# Update the system prompt to be more explicit about JSON format
SYSTEM_PROMPT = """You are a helpful daily planner assistant. Given a list of tasks, 
create a schedule for today starting at {start_time} (unless the user specifies a start time). 
Break down the tasks into  manageable chunks and assign realistic time slots. 
Don't add breaks before or after events that are already breaks, like lunch or going for a walk.
Only add breaks between tasks.

You must respond with a valid JSON array of objects. Each object must have exactly these fields:
- "start_time": string in "HH:MM" format
- "end_time": string in "HH:MM" format
- "description": string with the task description

Example format:
[
    {{"start_time": "09:00", "end_time": "09:45", "description": "Morning review"}},
    {{"start_time": "09:45", "end_time": "10:30", "description": "Email responses"}}
]

Keep responses concise and practical. Include short breaks between tasks. 
IMPORTANT: Respond ONLY with the JSON array, no additional text."""


# Initialize the database when the app starts
@app.on_event("startup")
async def startup_event():
    # Add a small delay to ensure volume is mounted
    time.sleep(2)
    print(
        f"Starting application with database path: {os.getenv('DB_PATH', 'tasks.db')}"
    )
    database.init_db()


@app.post("/api/plan", response_model=TaskResponse)
async def plan_day(request: TaskRequest):  # sourcery skip: invert-any-all
    try:
        # Initialize LLM model
        model = llm.get_model(MODEL_NAME)

        # Set API key if provided
        if API_KEY:
            model.key = API_KEY

        # Format system prompt with start time from request
        system = SYSTEM_PROMPT.format(start_time=request.start_time)

        # Get response from LLM
        response = model.prompt(request.description, system=system)

        # Add debug logging
        raw_response = response.text()
        print("Raw LLM response:", raw_response)  # Debug print

        # Strip markdown code blocks if present
        cleaned_response = strip_markdown_code_blocks(raw_response)

        # Parse JSON response
        try:
            tasks = json.loads(cleaned_response)
            # Validate the structure
            if not isinstance(tasks, list):
                raise ValueError("Response is not a JSON array")

            # Validate each task
            for task in tasks:
                if not all(
                    k in task for k in ("start_time", "end_time", "description")
                ):
                    raise ValueError("Task missing required fields")

            # Save tasks and get unique ID
            list_id = database.create_task_list(tasks)

            # Add list_id to response
            return TaskResponse(tasks=tasks, list_id=list_id)
        except json.JSONDecodeError as e:
            print(f"JSON parsing error: {str(e)}")  # Debug print
            raise HTTPException(
                status_code=500,
                detail=f"Failed to parse LLM response as JSON: {str(e)}",
            )
        except ValueError as e:
            print(f"Validation error: {str(e)}")  # Debug print
            raise HTTPException(
                status_code=500, detail=f"Invalid response format: {str(e)}"
            )

    except Exception as e:
        print(f"General error: {str(e)}")  # Debug print
        raise HTTPException(
            status_code=500, detail=f"Error processing request: {str(e)}"
        )


# Add new endpoints for task list management
@app.get("/api/tasks/{list_id}")
async def get_tasks(list_id: str):
    try:
        UUID(list_id)  # Validate UUID format
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid list ID format")

    tasks = database.get_task_list(list_id)
    if tasks is None:
        raise HTTPException(status_code=404, detail="Task list not found")
    return {"tasks": tasks}


@app.put("/api/tasks/{list_id}/{task_index}")
async def update_task(list_id: str, task_index: int, request: TaskUpdateRequest):
    try:
        UUID(list_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid list ID format")

    if not database.update_task_status(list_id, task_index, request.completed):
        raise HTTPException(status_code=404, detail="Task not found")
    return {"success": True}


# Add a route for the task list view
@app.get("/tasks/{list_id}")
async def task_list_page(list_id: str):
    return FileResponse("index.html")


@app.post("/api/replan", response_model=TaskResponse)
async def replan_day(request: ReplanRequest):
    """Adjust an existing schedule based on user feedback.

    This endpoint takes feedback about the current schedule and re-generates it
    using the LLM. The new schedule replaces the existing one for the given list_id.
    Completion status is preserved by position (documented limitation).
    """
    try:
        # Validate list_id format
        try:
            UUID(request.list_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid list ID format")

        # Verify the list exists
        existing_tasks = database.get_task_list(request.list_id)
        if existing_tasks is None:
            raise HTTPException(status_code=404, detail="Task list not found")

        # Format current schedule as text for LLM context, including completion status
        current_schedule_text = "Current schedule:\n"
        for i, task in enumerate(request.tasks):
            status = "(completed)" if getattr(task, "completed", False) else "(pending)"
            current_schedule_text += (
                f"{i+1}. {task.start_time}-{task.end_time}: {task.description} {status}\n"
            )

        # Initialize LLM model
        model = llm.get_model(MODEL_NAME)
        if API_KEY:
            model.key = API_KEY

        # Create a system prompt that includes the current schedule
        replan_system_prompt = (
            "You are a helpful daily planner assistant. The user wants to adjust their existing schedule based on feedback.\n\n"
            + current_schedule_text
            + "\nUser feedback: "
            + request.tweak_feedback
            + "\n\nPlease adjust the schedule based on this feedback. Maintain the same time constraints and overall structure where possible, but make the requested adjustments.\n\n"
            + "Important: Tasks marked as (completed) in the current schedule are already done and should not be scheduled again. "
            + "When adjusting the schedule, preserve completed tasks and only reschedule or adjust pending tasks unless the user feedback explicitly says otherwise.\n\n"
            + "You must respond with a valid JSON array of objects. Each object must have exactly these fields:\n"
            + "- \"start_time\": string in \"HH:MM\" format\n"
            + "- \"end_time\": string in \"HH:MM\" format\n"
            + "- \"description\": string with the task description\n\n"
            + "Example format:\n"
            + "[{\"start_time\": \"09:00\", \"end_time\": \"09:45\", \"description\": \"Morning review\"}, {\"start_time\": \"09:45\", \"end_time\": \"10:30\", \"description\": \"Email responses\"}]\n\n"
            + "Keep responses concise and practical.\nIMPORTANT: Respond ONLY with the JSON array, no additional text."
        )

        # Get response from LLM. Provide the user's tweak feedback as the user message
        # (some LLM backends require at least one user message)
        response = model.prompt(request.tweak_feedback, system=replan_system_prompt)

        # Add debug logging
        raw_response = response.text()
        print("Raw LLM replan response:", raw_response)  # Debug print

        # Strip markdown code blocks if present
        cleaned_response = strip_markdown_code_blocks(raw_response)

        # Parse JSON response
        try:
            new_tasks = json.loads(cleaned_response)
            # Validate the structure
            if not isinstance(new_tasks, list):
                raise ValueError("Response is not a JSON array")

            # Validate each task
            for task in new_tasks:
                if not all(k in task for k in ("start_time", "end_time", "description")):
                    raise ValueError("Task missing required fields")

            # Update the task list with new tasks, preserving completion status by position
            tasks_to_save = []
            for i, task in enumerate(new_tasks):
                # Preserve completion status from the request by position
                completed = request.tasks[i].completed if i < len(request.tasks) else False
                task_with_completion = {
                    "start_time": task["start_time"],
                    "end_time": task["end_time"],
                    "description": task["description"],
                    "completed": completed,
                }
                tasks_to_save.append(task_with_completion)

            # Save updated tasks to database
            if not database.update_task_list(request.list_id, tasks_to_save):
                raise HTTPException(status_code=404, detail="Failed to update task list")

            # Return response tasks (without completed flag - frontend handles it)
            response_tasks = [
                Task(start_time=t["start_time"], end_time=t["end_time"], description=t["description"])
                for t in new_tasks
            ]
            return TaskResponse(tasks=response_tasks, list_id=request.list_id)

        except json.JSONDecodeError as e:
            print(f"JSON parsing error: {str(e)}")  # Debug print
            raise HTTPException(
                status_code=500,
                detail=f"Failed to parse LLM response as JSON: {str(e)}",
            )
        except ValueError as e:
            print(f"Validation error: {str(e)}")  # Debug print
            raise HTTPException(
                status_code=500, detail=f"Invalid response format: {str(e)}"
            )
    except HTTPException:
        raise
    except Exception as e:
        print(f"General error in replan: {str(e)}")  # Debug print
        raise HTTPException(
            status_code=500, detail=f"Error processing replan request: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
