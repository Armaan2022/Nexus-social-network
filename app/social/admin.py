from django.contrib import admin
from .models import Author, Comment, Like, Post, FollowRequest, Follow, SiteSetting, InboxItem, Node
from django import forms
from django.contrib import admin
from .models import Node

# Register your models here.
#admin.site.register(Author)
admin.site.register(Comment)
admin.site.register(Like)
#admin.site.register(Node)
admin.site.register(FollowRequest)
admin.site.register(InboxItem)


# Register your models here.
@admin.register(Follow)
class FollowAdmin(admin.ModelAdmin):
    list_display = ('user', 'following', 'published')

@admin.register(SiteSetting)
class SiteSettingAdmin(admin.ModelAdmin):
    list_display = ['require_approval']

@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'published', 'visibility')
    search_fields = ('title', 'author__display_name')
    list_filter = ('visibility', 'published')

@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    list_display = ('id', 'display_name', 'host', 'user', 'is_approved')
    list_filter = ('host', 'is_approved')
    search_fields = ('display_name', 'name', 'host', 'fqid')
    list_per_page = 50
    
    # Optional: Add custom filtering for hosts with many entries
    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)
        # Add custom host filtering if needed
        return queryset, use_distinct

@admin.register(Node)
class NodeAdmin(admin.ModelAdmin):
    list_display = ('team_name', 'host', 'username', 'password', 'is_active')
    search_fields = ('team_name', 'host')
    list_filter = ('is_active',)
    list_per_page = 50