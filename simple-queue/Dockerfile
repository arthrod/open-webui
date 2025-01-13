# Use a slim Python image as the base
FROM python:3.13-slim

# Install necessary dependencies
RUN apt-get update && apt-get upgrade -y && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages
RUN pip3 install --upgrade flask gunicorn

# Create the /app directory
RUN mkdir -p /app
COPY /main.py /simple_queue.py /app/

WORKDIR /app

# Expose the port for the queue service
EXPOSE 8000

# Command to start the queue service with Gunicorn
CMD [ "gunicorn", "-w", "1", "-b", "0.0.0.0:8000", "main:app" ]
