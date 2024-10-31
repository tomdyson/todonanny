import json
import os
from datetime import datetime
from typing import List
from uuid import UUID

import llm
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import database

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


# Get environment variables
MODEL_NAME = os.getenv("LLM_MODEL", "gpt-3.5-turbo")
API_KEY = os.getenv("LLM_API_KEY")

# Update the system prompt to be more explicit about JSON format
SYSTEM_PROMPT = """You are a helpful daily planner assistant. Given a list of tasks, 
create a schedule for today starting at {start_time}. Break down the tasks into 
manageable chunks and assign realistic time slots.

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

        # Parse JSON response
        try:
            tasks = json.loads(raw_response)
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
async def update_task(list_id: str, task_index: int, completed: bool):
    try:
        UUID(list_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid list ID format")
    
    if not database.update_task_status(list_id, task_index, completed):
        raise HTTPException(status_code=404, detail="Task not found")
    return {"success": True}

# Add a route for the task list view
@app.get("/tasks/{list_id}")
async def task_list_page(list_id: str):
    return FileResponse("index.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
