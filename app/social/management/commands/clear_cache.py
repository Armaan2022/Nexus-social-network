# filepath: /c:/Users/prodb/Documents/GitHub/w25-project-forestgreen/your_app/management/commands/clear_cache.py
from django.core.management.base import BaseCommand
from django.core.cache import cache

class Command(BaseCommand):
    help = 'Clear the cache'

    def handle(self, *args, **kwargs):
        cache.clear()
        self.stdout.write(self.style.SUCCESS('Successfully cleared the cache'))