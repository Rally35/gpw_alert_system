#!/bin/bash
# Script to start the GPW Alert System

echo "Starting GPW Alert System..."

# Make sure docker and docker-compose are installed
if ! command -v docker &> /dev/null; then
    echo "Docker is not installed. Please install Docker first."
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Build and start the containers
echo "Building and starting containers..."
docker-compose build && docker-compose up -d

# Wait for database to be ready
echo "Waiting for database to be ready..."
sleep 10

# Import historical data
echo "Importing historical data (this may take a while)..."
docker-compose logs -f historical_importer

echo "System started successfully!"
echo "Access the dashboard at http://localhost:8000"