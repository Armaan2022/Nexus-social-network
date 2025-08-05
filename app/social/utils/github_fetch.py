import requests
from django.utils.timezone import now
from social.models import Author, Post

GITHUB_API_URL = "https://api.github.com/users/{username}/events/public"

def fetch_github_activity():
    """Fetch GitHub activity for all authors who have a GitHub profile."""
    authors = Author.objects.exclude(github__isnull=True).exclude(github="")

    for author in authors:
        username = author.github.rstrip("/").split("/")[-1]  # Extract GitHub username
        url = GITHUB_API_URL.format(username=username)

        response = requests.get(url, headers={"Accept": "application/vnd.github.v3+json"})

        if response.status_code == 200:
            events = response.json()

            for event in events[:5]:  # Fetch latest 5 events
                event_type = event.get("type")
                repo_name = event["repo"]["name"]
                event_link = event["repo"]["url"].replace("api.github.com/repos", "github.com")

                post_title = f"New {event_type} on {repo_name}"
                post_content = f"Check out the activity: [{repo_name}]({event_link})"

                # Check if this GitHub activity already exists
                if not Post.objects.filter(author=author, github_link=event_link).exists():
                    Post.objects.create(
                        author=author,
                        title=post_title,
                        description=f"Auto-posted from GitHub activity ({event_type}).",
                        content=post_content,
                        github_link=event_link,
                        visibility="PUBLIC",
                        published=now(),
                    )

        else:
            print(f"Failed to fetch GitHub activity for {author.display_name}: {response.status_code}")
