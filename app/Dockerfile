# Use an official Python runtime as a base image
FROM python:3.12-alpine

# Sets the current working directory to be `/app`
WORKDIR /app

# Prevents Python from writing pyc and pycache files to disc
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Install ffmpeg and other required packages
RUN apk update && \
    apk add --no-cache \
    postgresql-dev \
    postgresql-libs \
    gcc \
    python3-dev \
    musl-dev \
    jpeg-dev \
    zlib-dev \
    libffi-dev \
    ffmpeg

# install dependencies
RUN pip install --upgrade pip
COPY ./requirements.txt .
RUN pip install -r requirements.txt

COPY . .


# Expose the Django app port (default is 8000)
EXPOSE 8000

# Run the Django app using Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "socialNetwork.wsgi:application"]