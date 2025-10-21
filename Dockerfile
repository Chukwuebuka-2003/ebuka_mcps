FROM python:3.9-slim

WORKDIR /app

# Copy dependency file(s) and install packages
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy the rest of the code into the container
COPY . .

# Expose the port that your application listens on
EXPOSE 5000

# Run the main server script
CMD ["python", "rag_mcp_server.py"]
