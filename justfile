# Run FastAPI development server
run:
    uvicorn main:app --reload

# Install dependencies
install:
    pip install -r requirements.txt

# Format code with black
format:
    black .

# Run linting
lint:
    pylint main.py

# Run tests
test:
    pytest

# Help
help:
    just --list
