from celery import shared_task
from social.utils.github_fetch import fetch_github_activity

@shared_task
def fetch_github_data():
    fetch_github_activity()
