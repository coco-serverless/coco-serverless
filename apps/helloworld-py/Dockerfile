# Adapted from https://github.com/knative/docs/tree/main/code-samples/serving/hello-world/helloworld-python
FROM python:3.10-slim

# Allow statements and log messages to immediately appear in the Knative logs
ENV PYTHONUNBUFFERED True

# Copy local code to the container image.
ENV APP_HOME /app
WORKDIR $APP_HOME
COPY . ./

# Install production dependencies.
RUN pip install Flask

# Run the web service on container startup. 
CMD ["python", "app.py"]
