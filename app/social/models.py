import uuid
from django.db import models
from datetime import datetime
from django.utils import timezone
from django.contrib.auth.models import User
import os
from django.conf import settings
from urllib.parse import quote
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from moviepy.video.io.VideoFileClip import VideoFileClip
from django.db.utils import OperationalError, ProgrammingError
from django.contrib.auth.hashers import make_password, check_password
import base64
from django.utils.html import strip_tags
import logging

logger = logging.getLogger(__name__)

def get_default_profile_image():
    """Return the path to the default profile image"""
    return f'https://{settings.CURRENT_DOMAIN}/static/images/default-profile.png'


# Got this from Chat GPT
def clean_url(url):
    """Remove duplicate media prefixes and path segments from URLs"""
    if not url:
        return url
    
    # Step 1: Handle duplicate domain/media prefixes
    if '/media/' in url:
        import re
        matches = re.findall(r'https?://[^/]+/media/', url)
        
        if len(matches) > 1:
            first_prefix_end = url.find('/media/') + len('/media/')
            media_content = url[first_prefix_end:]
            
            # Remove any additional domain/media/ prefixes
            media_content = re.sub(r'https?://[^/]+/media/', '', media_content)
            
            # Reconstruct the URL with just one prefix
            url = url[:first_prefix_end] + media_content
    
    # Step 2: Remove duplicate path segments after /media/
    if '/media/' in url:
        import re
        
        # Find the part after /media/
        media_path = url.split('/media/')[1]
        
        # Check for duplicate path segments like "images/images/"
        segments = media_path.split('/')
        clean_segments = []
        
        for i, segment in enumerate(segments):
            # Skip if this segment is identical to the next one
            if i < len(segments) - 1 and segment == segments[i+1]:
                continue
            clean_segments.append(segment)
        
        # Rebuild the URL
        prefix = url.split('/media/')[0] + '/media/'
        cleaned_path = '/'.join(clean_segments)
        url = prefix + cleaned_path
    
    return url
    
# Node model to store information about the nodes in the network
class Node(models.Model):
    team_name = models.CharField(max_length=100)
    host = models.URLField(max_length=500)
    username = models.CharField(max_length=255)
    password = models.CharField(max_length=255)  # Hashed password
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.team_name

class Author(models.Model):

    # Null allowed for adding remote authors wihtout needing a password for them
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)  # Link to Django User
    display_name = models.CharField(max_length=5000, blank=True, null=True)    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(default="Name", max_length=200, null=True)
    title = models.CharField(default="Title", max_length=200, null=True)
    description = models.CharField(default="Description", max_length=200, null=True)
    profile_image = models.ImageField(max_length=5000, upload_to='images/', blank=True, null=False)
    profile_image_url = models.URLField(max_length=5000, blank=True, null=False, default=get_default_profile_image)
    bio = models.TextField(blank=True, null=True)
    fqid = models.URLField(max_length=5000, blank=True, unique=True)  # Fully Qualified ID
    fqid_encoded = models.CharField(max_length=5000, blank=True)  # Fully Qualified ID Encoded
    host = models.URLField(default=f"http://{settings.CURRENT_DOMAIN}/api/")  # API Host
    github = models.URLField(blank=True, null=True)
    profile_url = models.URLField(max_length=5000,blank=True, null=True)

    # New Field: Admin Approval
    is_approved = models.BooleanField(default=False)  # Default to False (pending approval) 

    def save(self, *args, **kwargs):

        # Check if user exists before accessing is_superuser
        if hasattr(self, 'user') and self.user is not None:
            if self.user.is_superuser:
                self.is_approved = True
                pass

        if not self.profile_url:
            self.profile_url = f"{self.host}authors/{self.id}/".replace('api/', '')

        if not self.fqid:
            current_domain = settings.CURRENT_DOMAIN  # Ensure CURRENT_DOMAIN is set in settings.py
            fqid = f"http://{current_domain}/api/authors/{self.id}"
            self.fqid = fqid

        if self.profile_image_url:
            self.profile_image_url = clean_url(self.profile_image_url)

        
        if not self.fqid_encoded:
            self.fqid_encoded = quote(self.fqid)

        super().save(*args, **kwargs)
    
    def get_details_dict(self):
        return {
            'id': str(self.id),
            'display_name': self.display_name,
            'host': self.host,
            'fqid': self.fqid,
            'github': self.github,
            'profile_url': self.profile_url,
            'is_approved': self.is_approved
        }

    def get_absolute_url(self):
        return f"{self.host}/authors/{self.id}/"

    def __str__(self):
        return f"{self.display_name} ({self.id} - {self.host})" or "Unnamed Author"


class SiteSetting(models.Model):
    require_approval = models.BooleanField(default=True)

    def __str__(self):
        return "Site Settings"

def ensure_approval_setting():
    try:
        if not SiteSetting.objects.exists():
            SiteSetting.objects.create(require_approval=True)
    except (OperationalError, ProgrammingError):
        # Database isn't ready yet
        pass


class FollowRequest(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)  
    actor = models.ForeignKey(Author, on_delete=models.CASCADE, related_name='sent_follow_requests')
    object = models.ForeignKey(Author, on_delete=models.CASCADE, related_name='received_follow_requests')
    published = models.DateTimeField("date published", default=datetime.now)

    class Meta:
        ordering = ['-published']

    def save(self, *args, **kwargs):

        if self.published is None:
            self.published = datetime.now()
        super().save(*args, **kwargs)

# user must first accept a follow request for their follow to be added to the Follow table
class Follow(models.Model):
    user = models.ForeignKey(Author, on_delete=models.CASCADE, related_name='following')  # Avoid conflict
    following = models.ForeignKey(Author, on_delete=models.CASCADE, related_name='followers')  # Avoid conflict
    published = models.DateTimeField("date published", default=datetime.now)

    class Meta:
        ordering = ['-published']

def validate_video_duration(value):
    """ Ensure video duration is no longer than 4 seconds """
    try:
        temp_file_path = value.temporary_file_path() if hasattr(value, 'temporary_file_path') else f"/tmp/{value.name}"
        
        with open(temp_file_path, 'wb+') as temp_file:
            for chunk in value.chunks():
                temp_file.write(chunk)

        video = VideoFileClip(temp_file_path)
        if video.duration > 4:
            video.close()
            os.remove(temp_file_path)
            raise ValidationError("Video must be 4 seconds or less.")
        
        video.close()
        os.remove(temp_file_path)
    except Exception:
        raise ValidationError("Invalid video file.")

class Post(models.Model):

    CONTENT_TYPE_CHOICES = [
        ('text/plain', 'Plain Text'),
        ('text/markdown', 'Markdown'),
        ('image/png;base64', 'PNG Image'),
        ('image/jpeg;base64', 'JPEG Image'),
        ('application/base64', 'Base64 Image'),
        ('video/mp4', 'MP4 Video'),
        ('video/avi', 'AVI Video'),
        ('video/mov', 'MOV Video'),

        # For bisque group only
        ('image/png', 'PNG Image'),
    ]
    VISIBILITY_CHOICES = [
        ('PUBLIC', 'Public'),
        ('FRIENDS', 'Friends Only'),
        ('UNLISTED', 'Unlisted'),
        ('DELETED', 'Deleted'),
    ]

    # The author of the post (linked to the Author model) 
    author = models.ForeignKey(Author, on_delete=models.CASCADE, related_name='posts')
    title = models.CharField(max_length=200, blank=True, null=True)
    post_url = models.URLField(max_length=200, blank=True, null=True)
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    post_api_url = models.URLField(max_length=200, blank=True, null=True)
    description = models.CharField(max_length=200, blank=True, null=True, default='No Description')
    contentType = models.CharField(max_length=20, choices=CONTENT_TYPE_CHOICES, default='text/plain')
    content = models.TextField()
    published = models.DateTimeField(default=timezone.now)
    visibility = models.CharField(max_length=20, choices=VISIBILITY_CHOICES, default='PUBLIC')
    likes = GenericRelation('Like', related_query_name='likes')
    #comments = GenericRelation('Comment', related_query_name='post_comments')
    inbox = GenericRelation('InboxItem', related_query_name='inbox_items')
    video = models.FileField(
        upload_to='videos/',
        blank=True, null=True,
        validators=[validate_video_duration]
    )
    fqid = models.URLField(max_length=255, blank=True, unique=True)
    fqid_encoded = models.CharField(max_length=255, blank=True)

    def save(self, *args, **kwargs):

        # For bisque group only
        if self.contentType == 'image/png':
            self.contentType = 'image/png;base64'

        if not self.fqid:
            current_domain = settings.CURRENT_DOMAIN  # Ensure CURRENT_DOMAIN is set in settings.py
            fqid = f"http://{current_domain}/api/authors/{self.author.id}/posts/{self.id}"
            self.fqid = fqid
            
        if not self.fqid_encoded:
            self.fqid_encoded = quote(self.fqid)

        if not self.post_url:
            self.post_url = f"{self.author.host}posts/{self.id}/"

        if not self.post_api_url:
            current_domain = settings.CURRENT_DOMAIN  # Ensure CURRENT_DOMAIN is set in settings.py
            post_api_url = f"http://{current_domain}/api/authors/{self.author.id}/posts/{self.id}"
            self.post_api_url = post_api_url

        super().save(*args, **kwargs)


    
    def get_shareable_link(self):
        if self.visibility in ["PUBLIC", "UNLISTED"]:
            return f"{self.author.host}post/{str(self.id)}/"
        return None
    
    class Meta:
        ordering = ['-published']

  
class Comment(models.Model):
    CONTENT_TYPE_CHOICES = [
        ('text/plain', 'Plain Text'),
        ('text/markdown', 'Markdown'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False) 
    author = models.ForeignKey(Author, on_delete=models.CASCADE)
    comment = models.TextField()
    content_type = models.CharField(max_length=20, choices=CONTENT_TYPE_CHOICES)
    published = models.DateTimeField("date published", default=datetime.now)
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='post_comments') 
    fqid = models.URLField(max_length=255, blank=True, unique=True)  # Fully Qualified ID
    fqid_encoded = models.CharField(max_length=255, blank=True)  # Fully Qualified ID Encoded
    likes = GenericRelation('Like', related_query_name='comment_likes', related_name = 'comment_likes_set')
    inbox = GenericRelation('InboxItem', related_query_name='inbox_items')

    def __str__(self):
        return self.comment

    class Meta:
        ordering = ['-published']

    def save(self, *args, **kwargs):
        if not self.fqid:
            current_domain = settings.CURRENT_DOMAIN  # Ensure CURRENT_DOMAIN is set in settings.py
            fqid = f"http://{current_domain}/api/authors/{self.author.id}/posts/{self.post.id}/commented/{self.id}"
            self.fqid = fqid

        if not self.fqid_encoded:
            self.fqid_encoded = quote(self.fqid)
        super().save(*args, **kwargs)

class Like(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    published = models.DateTimeField("date published", default=datetime.now)
    author = models.ForeignKey(Author, on_delete=models.CASCADE)
    
    # Generic foreign key fields
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.UUIDField()
    content_object = GenericForeignKey('content_type', 'object_id')
    inbox = GenericRelation('InboxItem', related_query_name='inbox_items')
    fqid = models.URLField(max_length=255, blank=True, unique=True)
    fqid_encoded = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['-published']

    def save(self, *args, **kwargs):
        if not self.fqid:
            current_domain = settings.CURRENT_DOMAIN
            fqid = f"http://{current_domain}/api/authors/{self.author.id}/liked/{self.id}"
            self.fqid = fqid

        if not self.fqid_encoded:
            self.fqid_encoded = quote(self.fqid)
        super().save(*args, **kwargs)



class InboxItem(models.Model):

    VISIBILITY_CHOICES = [
        ('UNREAD', 'Unread'),
        ('READ', 'Read'),
        ('DELETED', 'Deleted'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(Author, on_delete=models.CASCADE, related_name='inbox_items')
    sender = models.ForeignKey(Author, on_delete=models.CASCADE, related_name='sent_items')
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.UUIDField()
    content_object = GenericForeignKey('content_type', 'object_id')
    published = models.DateTimeField("date published", default=datetime.now)
    visibility = models.CharField(max_length=20, choices=VISIBILITY_CHOICES, default='UNREAD')

    class Meta:
        ordering = ['-published']