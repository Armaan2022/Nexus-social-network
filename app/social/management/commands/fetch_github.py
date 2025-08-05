from django.core.management.base import BaseCommand
from social.utils.github_fetch import fetch_github_activity

class Command(BaseCommand):
    help = "Fetch public GitHub activity and create posts"

    def handle(self, *args, **kwargs):
        fetch_github_activity()
        self.stdout.write(self.style.SUCCESS(" Successfully fetched GitHub activity"))