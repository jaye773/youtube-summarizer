# --- START OF FILE Dockerfile ---

# Use an official lightweight Python image
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file first to leverage Docker's build cache
COPY requirements.txt .

# Install the Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
COPY . .

# Expose the port the app runs on
EXPOSE 5001

# Command to run the application using Gunicorn
# This is a production-ready server, more robust than Flask's built-in server
CMD ["gunicorn", "--bind", "0.0.0.0:5001", "app:app"]