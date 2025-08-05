from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.forms.models import ModelForm
from django.forms.widgets import FileInput
from django import forms
from .models import Author, Post, Node, get_default_profile_image
from django.conf import settings

class AuthorForm(ModelForm):
    class Meta:
        model = Author
        fields = '__all__'
        exclude = ['user']
        widgets = {
            'profileImage': FileInput(),
        }

    def save(self, commit=True):
        instance = super().save(commit=False)

        # Automatically set profile_image_url
        if instance.profile_image and hasattr(instance.profile_image, 'url'):
            current_domain = settings.CURRENT_DOMAIN
            instance.profile_image_url = f"https://{current_domain}/media/images/{instance.profile_image.name}".replace(' ', '_').replace("%20", "_")
        elif not instance.profile_image_url:
            # Set to default if no profile image is provided
            instance.profile_image_url = get_default_profile_image()

        if commit:
            instance.save()
        return instance
    


class PostForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = ['title', 'description', 'content', 'contentType', 'visibility']

