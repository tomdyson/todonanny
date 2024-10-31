# Build stage for Tailwind CSS
FROM node:20-slim AS css-builder
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY src/ src/
COPY index.html ./
COPY tailwind.config.js ./
RUN npx tailwindcss -i ./src/input.css -o ./dist/output.css --minify

# Final stage
FROM python:3.13-slim
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -u 1000 -m appuser

# Create data directory
RUN mkdir -p /app/data && \
    chown appuser:appuser /app/data

# Copy Python requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .
# Copy built CSS from css-builder stage
COPY --from=css-builder /app/dist/output.css dist/

# Set ownership of application files
RUN chown -R appuser:appuser /app

# Switch to appuser
USER appuser

# Set database path for production
ENV DB_PATH=/app/data/tasks.db

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]