from .models import *
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import User
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.apps import AppConfig



@receiver(post_save, sender=User)
def create_user_author(sender, instance, created, **kwargs):
    try:
        # Check if author already exists
        instance.author
    except:
        # Create SiteSetting if it doesn't exist
        approval_setting = SiteSetting.objects.first()
        if not approval_setting:
            approval_setting = SiteSetting.objects.create(require_approval=True)
        
        is_approved = not approval_setting.require_approval
        if instance.is_superuser:
            is_approved = True
            
        # Create author if it doesn't exist
        Author.objects.create(
            user=instance,
            display_name=instance.username,
            name=instance.username,
            is_approved=is_approved
        )

        
@receiver(post_save, sender=User)
def save_user_author(sender, instance, **kwargs):
    instance.author.save


@receiver(post_delete, sender=Like)
@receiver(post_delete, sender=FollowRequest)
@receiver(post_delete, sender=Post)
@receiver(post_delete, sender=Comment)
def delete_related_inbox_items(sender, instance, **kwargs):
    """
    Simulates cascade on delete for InboxItems GenericForeignKey
    """
    content_type = ContentType.objects.get_for_model(instance)
    InboxItem.objects.filter(content_type=content_type, object_id=instance.id).delete()