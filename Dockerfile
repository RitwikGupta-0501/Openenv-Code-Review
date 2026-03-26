# Use a lightweight Python image
FROM python:3.12-slim

# Hugging Face requires the container to run as a non-root user (UID 1000)
RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH"

# Set the base working directory
WORKDIR /home/user/app

# Install uv (The blazing fast package manager)
RUN pip install --no-cache-dir uv

# Copy all your project files into the container
COPY --chown=user:user . .

# Sync the dependencies
RUN uv sync

# Hugging Face Spaces strictly routes traffic to port 7860
EXPOSE 7860

# Launch the FastAPI app directly
CMD ["uv", "run", "uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "7860"]
