import uuid
import re
import os
import base64
import uuid
import json
import requests
import markdown
import logging
from rest_framework.request import Request
from urllib.parse import unquote, urlparse
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import logout
from django.http import JsonResponse
from django.utils import timezone
from django.conf import settings
from django.contrib import messages
from django.db.models import Q
from rest_framework import viewsets, generics, status
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.views import APIView
from rest_framework.generics import RetrieveAPIView
from rest_framework.pagination import PageNumberPagination
from .models import Author, Follow, FollowRequest, Post, Like, Comment, InboxItem, Node, SiteSetting
from .serializers import AuthorSerializer, PostSerializer, SingleAuthorSerializer, SinglePostSerializer, SingleCommentSerializer, SingleLikeSerializer, MultiLikeSerializer, SingleFollowRequestSerializer, SinglePostDeSerializer, SingleCommentDeSerializer, MultiCommentSerializer, get_default_profile_image
from .forms import AuthorForm, PostForm
from django.contrib.contenttypes.models import ContentType
from rest_framework.permissions import IsAuthenticated
from django.http import HttpResponse
from rest_framework.authentication import SessionAuthentication, BasicAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from requests.adapters import HTTPAdapter

#from urllib3.util.retry import Retry

from .utils import Inbox, get_object_by_fqid, send_post_to_remote_followers, send_like_to_remote_nodes, send_comment_to_remote_nodes
from django.http import HttpResponseForbidden, HttpResponse

class SrcPagination(PageNumberPagination):
    page_size = 100 
    page_size_query_param = 'size'
    max_page_size = 1000


logger = logging.getLogger(__name__)

class CustomPageNumberPagination(PageNumberPagination):
    """ Adds custom size query param to Paginator"""
    page_size_query_param = 'size'  

class AuthorViewSet(viewsets.ViewSet):
    """
    API endpoint to retrieve author details with a consistent URL.
    """

    permission_classes = [AllowAny]  # Allow public access

    def retrieve(self, request, pk=None):
        author = get_object_or_404(Author, id=pk)
        serializer = AuthorSerializer(author)
        return Response(serializer.data)




class AuthorListView(generics.ListAPIView):
    """
    API endpoint to retrieve all authors on this node. These are only the authors that are hosted on our node.
    Requirements: GET [local, remote]: retrieve all profiles on the node (paginated)
    """
    #authentication_classes = [BasicAuthentication, SessionAuthentication]
    #permission_classes = [IsAuthenticated]
    authentication_classes = []  # Empty list to override global settings
    permission_classes = [AllowAny]  # Explicitly allow anyone
    queryset = Author.objects.all().filter(is_approved=True).exclude(user__username__icontains="API")
    serializer_class = AuthorSerializer
    pagination_class = CustomPageNumberPagination 

    def get(self, request, *args, **kwargs):
        """Gets authors and paginates them."""
        authors = self.get_queryset()
        page = self.paginate_queryset(authors)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        else:
            # If pagination is not applied or no query paramters are passed , then manually format the response
            serializer = self.get_serializer(authors, many=True)
            return Response({
            "type": "authors",
            "authors": serializer.data
            })
        
    def get_paginated_response(self, data):
        """Modifies paginated response to include type field and autors."""
        return Response({
            "type": "authors",
            "authors": data
        })
     

class AuthorDetailView(RetrieveAPIView):
    queryset = Author.objects.all()
    serializer_class = AuthorSerializer
    lookup_field = 'id'

    def get(self, request, *args, **kwargs):
        author = self.get_object()
        serializer = self.get_serializer(author)
        return Response(serializer.data)
    
def are_friends(author1, author2):
    """
    Check if two authors are friends (i.e., they are mutually following each other).
    """
    return Follow.objects.filter(user=author1, following=author2).exists() and \
           Follow.objects.filter(user=author2, following=author1).exists()


class PostViewSet(viewsets.ModelViewSet):
    queryset = Post.objects.all()
    serializer_class = SinglePostSerializer
    lookup_field = 'id'
    permission_classes = [AllowAny]
    
class PostDetailView(APIView):
    """
    Retrieve, update, or delete a specific post by its UUID for a specific author.
    """
    permission_classes = [AllowAny]
    
    def get(self, request, author_serial, post_serial):
        """
        GET [local, remote]: Retrieve a specific post by its UUID for a specific author.
        - Public posts: accessible to anyone.
        - Friends-only posts: only accessible to authenticated friends.
        """
        author = get_object_or_404(Author, id=author_serial)
        post = get_object_or_404(Post, author=author, id=post_serial)
        
        # Check visibility
        if post.visibility == "FRIENDS":
            if not request.user.is_authenticated:
                return Response({"error": "Authentication required for friends-only posts"}, status=status.HTTP_403_FORBIDDEN)
    
            # Allow the author to see their own post, regardless of visibility
            if post.author == request.user.author:
                # Author is allowed to see the post
                pass
            else:
                # Use the are_friends function to check if the requester is a friend of the author
                if not are_friends(request.user.author, post.author):
                    return Response({"error": "You are not authorized to view this post"}, status=status.HTTP_403_FORBIDDEN)
            
        serializer = SinglePostSerializer(post)
        return Response(serializer.data)
    
    def put(self, request, author_serial, post_serial):
        """
        PUT [local]: Update a post.
        - Only the author of the post can update it.
        - Must be authenticated locally as the author.
        """
        if not request.user.is_authenticated:
            return Response({"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)
        author = get_object_or_404(Author, id=author_serial)
        post = get_object_or_404(Post, author=author, id=post_serial)

        # Check if the requester is the author of the post
        if post.author != request.user.author:
            return Response({"error": "You are not authorized to update this post"}, status=status.HTTP_403_FORBIDDEN)

        serializer = SinglePostSerializer(post, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, author_serial, post_serial):
        """
        DELETE [local]: Remove a post.
        - Only the author of the post can delete it.
        - Must be authenticated locally as the author.
        """
        if not request.user.is_authenticated:
            return Response({"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)
        
        author = get_object_or_404(Author, id=author_serial)
        post = Post.objects.get(author=author, id=post_serial)
        
        # Check if the requester is the author of the post
        if post.author != request.user.author:
            return Response({"error": "You are not authorized to delete this post"}, status=status.HTTP_403_FORBIDDEN)

        post.visibility = "DELETED"
        post.save()
        return Response({"message": "Post deleted successfully"}, status=status.HTTP_204_NO_CONTENT)
    
    
        
@login_required
def post_login_redirect(request):
    # if not request.user.author.is_approved:
    #     return redirect('waiting_approval')  # Redirect to the waiting page
    # return redirect('stream')  # Redirect to the normal stream page
    if request.user.is_authenticated:
        if not request.user.author.is_approved:
            return redirect('waiting_approval')  # Create a template for this
        return redirect('stream')  # Normal redirect
    return redirect('account_login')


@login_required
@user_passes_test(lambda u: u.is_superuser)  # Only allow admins
def manage_accounts(request):
    approval_setting = SiteSetting.objects.first()
    pending_authors = Author.objects.filter(is_approved=False)
    return render(request, 'accounts.html', {'approval_setting': approval_setting, 'pending_authors': pending_authors})

@login_required
@user_passes_test(lambda u: u.is_superuser)
def toggle_approval(request):
    if request.method == 'POST':
        approval_setting = SiteSetting.objects.first()
        approval_setting.require_approval = 'require_approval' in request.POST
        approval_setting.save()
    return redirect('manage_accounts')

@login_required
@user_passes_test(lambda u: u.is_superuser)
def approve_user(request, author_id):
    author = get_object_or_404(Author, id=author_id)
    author.is_approved = True
    author.save()
    return redirect('manage_accounts')



@login_required
def stream(request):
    posts = Post.objects.all()  # Fetch all posts ordered by published date

    # Query to find mutual followers (friends) of the author
    author = Author.objects.get(user=request.user)
    authors_following = Follow.objects.filter(user=author).values_list('following', flat=True)
    authors_followers = Follow.objects.filter(following=author).values_list('user', flat=True)
    mutual_followers_list = list(set(authors_following).intersection(set(authors_followers)))
    
    author = Author.objects.get(user=request.user)
    # Query to get all posts that are public, and friends-only/unlisted for friends only
    combined_posts = Post.objects.filter(
        Q(visibility='PUBLIC') |
        Q(visibility='FRIENDS', author__in=mutual_followers_list) |
        Q(visibility='UNLISTED', author__in=authors_following)
    )
    # Sort by most recent post publiction
    posts = combined_posts.order_by('-published')


    return render(request, 'stream.html', {'posts': posts, 'author': author})


@login_required
def my_posts(request):
    author = Author.objects.get(user=request.user)
    # Query to get all posts that belong to the logged-in user
    posts = Post.objects.filter(author=request.user.author)

    # If needed, apply any filtering based on visibility (e.g., 'PUBLIC' posts only)
    posts = posts.filter(Q(visibility='PUBLIC') | Q(visibility='FRIENDS') | Q(visibility='UNLISTED'))

    # Sort the posts by the most recent
    posts = posts.order_by('-published')

    # Generate a UUID for each post and add it to the context
    posts_with_uuids = []
    for post in posts:
        # You can add additional processing here if needed
        id = get_id(post)  # Custom function to get UUID
        posts_with_uuids.append((post, id))
        post.like_count = Like.objects.filter(
            content_type=ContentType.objects.get_for_model(post)
        ).count()

    # Render the template with the posts and their UUIDs
    return render(request, 'my_posts.html', {'posts': posts_with_uuids, 'author': author})


@login_required
def mailbox(request):
    # Get the logged-in author's pending follow requests (requests where this author is the recipient)
    author = Author.objects.get(user=request.user)

    inbox_items = InboxItem.objects.filter(recipient=author).exclude(visibility='DELETED').order_by('-published')

    likes = []
    follow_requests = []
    posts = []
    comments = []

    # Categorize the inbox items based on their model type
    for item in inbox_items:

        if item.content_type.model == 'like':
            likes.append(item.content_object)
        elif item.content_type.model == 'followrequest':
            follow_requests.append(item.content_object)
        elif item.content_type.model == 'post':
            posts.append(item.content_object)
        elif item.content_type.model == 'comment':
            comments.append(item.content_object)

    context = {
        'likes': likes,
        'follow_requests': follow_requests,
        'posts': posts,
        'comments': comments,
        'author': author
    }
    return render(request, 'mailbox.html', context)

@login_required
def toggle_follow(request, author_id):
    """Handle toggling follow states: send request, cancel request, or unfollow."""
    if request.method == 'POST':
        current_author = request.user.author
        target_author = get_object_or_404(Author, id=author_id)

        if current_author == target_author:
            messages.error(request, "You cannot follow yourself.")
            return redirect('author_profile', id=author_id)

        # Check if already following
        if Follow.objects.filter(user=current_author, following=target_author).exists():
            Follow.objects.filter(user=current_author, following=target_author).delete()
            messages.success(request, "You have unfollowed this author.")
        # Check if request is pending
        elif FollowRequest.objects.filter(actor=current_author, object=target_author).exists():
            FollowRequest.objects.filter(actor=current_author, object=target_author).delete()
            messages.success(request, "Follow request canceled.")
        else:
            follow_request = FollowRequest.objects.create(
                id=uuid.uuid4(),  # Matches UUIDField
                actor=current_author,
                object=target_author
            )

            InboxItem.objects.create(
                    recipient=follow_request.object,
                    sender=follow_request.actor,
                    content_type=ContentType.objects.get_for_model(follow_request),
                    object_id=follow_request.id
                )
            
            nodes = Node.objects.filter(is_active=True)
            for node in nodes:
                auth = (node.username, node.password)

                logger.info(f"Sending follow USERNAME: {node.username} PASSWORD: {node.password}")
                logger.info(f"Sending follow request to {node.host}")
                logger.info(f"object host {follow_request.object.host}")
                logger.info(f"node host {node.host}")

                if str(follow_request.object.host.rstrip('/') ) == str(node.host.rstrip('/') ):
                    try:
                        node_host = node.host.rstrip('/')  # Remove trailing slash if present

                        logger.info(f"sending follow request to node {node_host}")

                        # Properly handle None values
                        follow_data = {
                            "type": "follow",
                            "summary": f"{current_author.display_name} wants to follow {target_author.display_name}",
                            "actor": {
                                "type": "author",
                                "id": current_author.fqid,
                                "host": current_author.host,
                                "displayName": current_author.display_name,
                                "page": current_author.profile_url,
                                "github": current_author.github if current_author.github else "",  # Empty string, not "null"
                                "profileImage": current_author.profile_image_url if current_author.profile_image_url else ""
                            },
                            "object": {
                                "type": "author",
                                "id": target_author.fqid,
                                "host": target_author.host,
                                "displayName": target_author.display_name,
                                "page": target_author.profile_url,
                                "github": target_author.github if target_author.github else "",   # Empty string, not "null"
                                "profileImage": target_author.profile_image_url if target_author.profile_image_url else ""  # Empty string, not "null"
                            }
                        }

                        author_serial = target_author.fqid.rstrip('/')
                        author_serial = author_serial.split('/')[-1]


                        logger.info(f"follow data sent to {node_host}/authors/{author_serial}/inbox\n\n{follow_data}")

                        if node.team_name == "bisque":

                            # Send POST request to the node's inbox
                            response = requests.post(
                                f"{node_host}/authors/{author_serial}/inbox",
                                json=follow_data,
                                auth=auth,
                                timeout=10,
                                verify=False
                            )
                        else:
                        
                            # Send POST request to the node's inbox
                            response = requests.post(
                                f"{node_host}/authors/{author_serial}/inbox",
                                json=follow_data,
                                auth=auth,
                                timeout=10,
                                verify=False
                            )

                        messages.success(request, "Follow request sent!")

                        #if response.status_code == 200 or :

                        # Assumes sent follow request to remote nodes are accepted
                        Follow.objects.create(user=current_author, following=target_author)
                        follow_request.delete()

                    except requests.exceptions.RequestException as e:
                        logger.error(f"Error sending follow request to {node.host}: {e}")
                        messages.error(request, f"Error sending follow request to {node.host}")

        return redirect('author_profile', id=author_id)
    return redirect('author_profile', id=author_id)


@login_required
def delete_inbox_item(request, object_uuid):

    if request.method == 'POST':

        author_id = request.user.author.id
        author = get_object_or_404(Author, id=author_id)

        inbox_item = get_object_or_404(InboxItem, object_id=object_uuid, recipient=author)
        inbox_item.visibility = 'DELETED'
        inbox_item.save()

        return redirect('mailbox')
    
    else:
        return HttpResponse(status=405)


def custom_logout(request):
    logout(request)  # Log the user out
    return redirect('account_login')  # Redirect to login page


@login_required
def create_post(request):
    author = Author.objects.get(user=request.user)
    if request.method == 'POST':
        title = request.POST.get('title', '')
        content_type = request.POST.get('content_type', 'text/plain')
        visibility = request.POST.get('visibility', 'PUBLIC')
        content = ""
        video = None
        
        # Handle content creation based on content type
        if content_type in ["image/png;base64", "image/jpeg;base64", "application/base64"]:
            content = handle_image_upload(request, content_type)
            if not content:  # If no image is uploaded, redirect back to the form
                return redirect('create_post')
            
        elif content_type in ["video/mp4", "video/avi", "video/mov"]:
            video = request.FILES.get('video')
            if not video:
                messages.error(request, "Please upload a video.")
                return redirect('create_post')
        elif content_type == "text/markdown":
            content = markdown.markdown(request.POST.get('content', ''))
        else:
            content = request.POST.get('content', '')
        
        # Create and save the post
        post = Post(
            author=author,
            title=title,
            contentType=content_type,
            content=content,
            visibility=visibility,
            video=video,  # Save video file
            published=timezone.now(),
        )
        post.save()

        # After saving, generate the post URL using the id
        # Ex url: "id":"http://nodebbbb/api/authors/222/posts/249"
        scheme = request.scheme
        host = request.get_host()
        author_id = request.user.author.id
        post_id = post.id
        post_url = f"{scheme}://{host}/authors/{author_id}/posts/{post_id}"
        post_api_url = f"{scheme}://{host}/api/authors/{author_id}/posts/{post_id}"
        
        # Update the post with the generated URL
        post.post_url = post_url
        post.post_api_url = post_api_url
        post.save()

        # Add the post to the followers' inboxes
        Inbox(request.user).add_post_to_followers_inbox(post)

        # Sends post as body of POST request to foriegn nodes Inbox if applicable
        logger.info(f"Sending post to remote nodes")
        logger.info(f"post: {post}")
        logger.info(f"author: {author}")
        send_post_to_remote_followers(request, post, author)

        return redirect('my_posts')

    return render(request, 'create_post.html', {'author': author})

def get_id(post):
    # Generate a UUID based on the post's id (e.g., UUID version 5 using a namespace)
    return uuid.uuid5(uuid.NAMESPACE_DNS, str(post.id))

@login_required
def edit_post(request, post_id):
    # Get the post using the id from the URL
    post = get_object_or_404(Post, id=post_id)  # Use 'id' instead of 'fqid' here
    author = Author.objects.get(user=request.user)
    if request.method == 'POST':
        post.title = request.POST.get('title', post.title)
        post.contentType = request.POST.get('content_type', post.contentType)
        post.content = request.POST.get('content', post.content)
        post.visibility = request.POST.get('visibility', post.visibility)
        post.published = timezone.now()  # Update timestamp on edit
        post.save()

        # Add edited post to followers' inboxes
        Inbox(request.user).add_post_to_followers_inbox(post)

        # Sends post as body of POST request to foriegn nodes Inbox if applicable
        send_post_to_remote_followers(request, post, author)

        return redirect('my_posts')  # Redirect to the post list

    return render(request, 'edit_post.html', {'post': post, 'author': author})

@login_required
def delete_post(request, post_id):
    # Get the post using the id from the URL
    post = get_object_or_404(Post, id=post_id)  # Use 'id' instead of 'fqid' here
    author = Author.objects.get(user=request.user)
    if request.method == "POST":
        post.visibility = 'DELETED'  # Mark the post as deleted
        post.save()
    
        # Sends post as body of POST request to foriegn nodes Inbox if applicable
        send_post_to_remote_followers(request, post, author)

        return redirect('my_posts')  # Redirect to the post list

    return render(request, 'delete_post.html', {'post': post, 'author': author})


def handle_image_upload(request, content_type):
    """
    Helper function to handle image uploads.
    Returns the URL of the uploaded image or None if no image is uploaded.
    """
    image_file = request.FILES.get('image')
    if not image_file:
        messages.error(request, "Please upload an image.")
        return None
    
    # Validate file type based on content_type
    if content_type == "image/png;base64" and not image_file.name.lower().endswith('.png'):
        messages.error(request, "Please upload a PNG image.")
        return None
    elif content_type == "image/jpeg;base64" and not image_file.name.lower().endswith(('.jpeg', '.jpg')):
        messages.error(request, "Please upload a JPEG image.")
        return None
    elif content_type == "application/base64" and image_file.name.lower().endswith(('.png', '.jpeg', '.jpg')):
        messages.error(request, "Please upload a valid image file.")
        return None
    
    # Save the image to the media folder
    fs = FileSystemStorage(location=settings.MEDIA_ROOT)
    filename = fs.save(image_file.name, image_file)
    image_url = fs.url(filename)

    return image_url

@login_required
def view_profile(request):
    author=request.user.author
    if request.method == 'POST':
        form = AuthorForm(request.POST, request.FILES, instance=author)
        if form.is_valid():
            form.save()
            username = request.user.username
            messages.success(request, f'{username}, Your profile is updated' )
            return redirect('view_profile')
            
    else:
        form = AuthorForm(instance=author)

    posts = Post.objects.filter(author=request.user.author)

    # Posts
    posts = posts.filter(Q(visibility='PUBLIC') | Q(visibility='FRIENDS') | Q(visibility='UNLISTED'))

    # Sort the posts by the most recent
    posts = posts.order_by('-published')

    # Generate a UUID for each post and add it to the context
    posts_with_uuids = []
    for post in posts:
        # You can add additional processing here if needed
        id = get_id(post)  # Custom function to get UUID
        posts_with_uuids.append((post, id))
        post.like_count = Like.objects.filter(
            object_id=id
        ).count()
    context = {'form': form, 'author': author, 'posts': posts_with_uuids}
    return render(request, 'profile/view_profile.html', context)


@login_required
def like_item(request, item_uuid):
    if request.method == 'POST':
        try:
            # Try to get the item as a Post
            item = get_object_or_404(Post, id=item_uuid)
        except:
            # If not a Post, try to get the item as a Comment
            item = get_object_or_404(Comment, id=item_uuid)


        author = request.user.author
        content_type = ContentType.objects.get_for_model(item)

        already_liked = Like.objects.filter(author=author, content_type=content_type, object_id=item.id).exists()
        
        if not already_liked:
            like = Like(author=author, content_type=content_type, object_id=item.id)
            like.save()

            
            author_of_obj = like.content_object.author
            # Add the like to the author's inbox
            Inbox(author_of_obj).add_like_to_inbox(like)

            # Sends like to remote nodes if applicable
            logger.info(f"Sending like to remote nodes")
            send_like_to_remote_nodes(request=request, like=like, author=author_of_obj)



            logger.info("item.type == " + str(content_type.model))
            if content_type.model == 'comment':
                post_author = item.post.author
                if author_of_obj != post_author:
                    send_like_to_remote_nodes(request=request, like=like, author=post_author)
                
                

    return redirect(request.POST.get('original', 'stream'))


@login_required
def add_comment(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    
    if request.method == 'POST':
        author = request.user.author
        comment_text = request.POST.get('comment_text', '').strip()
        original_url = request.POST.get("original", "/my_posts")  # Default to /my_posts if not provided
        
       # Detect if the comment contains Markdown-like syntax
        markdown_patterns = [
            r"\*\*.*?\*\*",  # Bold (**bold**)
            r"\*.*?\*",  # Italics (*italic*)
            r"^#\s",  # Headings (# Heading)
            r"^- ",  # Unordered lists (- item)
            r"^\d+\. ",  # Ordered lists (1. item)
            r"\[.*?\]\(.*?\)",  # Links [text](url)
            r"`.*?`"  # Inline code (`code`)
        ]
        
        is_markdown = any(re.search(pattern, comment_text, re.MULTILINE) for pattern in markdown_patterns)
        if is_markdown:
            content_type="text/markdown"
        else:
            content_type="text/plain"

        logger.info(f"Comment author: {author}")
        
        # Store the raw Markdown/plain text, not converted HTML
        comment = Comment.objects.create(
            author=author, post=post, comment= comment_text, content_type=content_type)
        comment.save()

        logger.info(f"Comment created: {comment}")

        logger.info(f"Comment post author: {comment.post.author}")

        # Add the comment to the post author's inbox
        #Inbox(comment.post.author).add_comment_to_inbox(comment)

        post_author = comment.post.author

        send_comment_to_remote_nodes(request=request, comment=comment, post_author=post_author)


        return redirect(original_url)  # Redirect back to the original page
    
    
#@login_required
def single_post(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    
    # Handle both authenticated and anonymous users
    if request.user.is_authenticated:
        author = Author.objects.get(user=request.user)
    else:
        author = None  # Or a default/guest author
        
    post.like_count = Like.objects.filter(
        content_type=ContentType.objects.get_for_model(post)
    ).count()
    
    return render(request, 'single_post.html', {'post': post, 'author': author})

@login_required
def author_profile(request, id):
    author = get_object_or_404(Author, id=id)
    posts = Post.objects.filter(author=author, visibility="PUBLIC").order_by("-published")
    
    # Check follow status if user is authenticated
    is_following = False
    request_pending = False
    if request.user.is_authenticated:
        current_author = request.user.author
        is_following = Follow.objects.filter(user=current_author, following=author).exists()
        request_pending = FollowRequest.objects.filter(actor=current_author, object=author).exists()

    context = {
        "author": author,
        "posts": posts,
        "is_following": is_following,
        "request_pending": request_pending,
        "is_current_user": request.user.is_authenticated and request.user.author == author,
    }
    return render(request, "author_profile.html", context)

@login_required
def send_follow_request(request, author_id):
    """Handle sending a follow request."""
    target_author = get_object_or_404(Author, id=author_id)
    current_author = request.user.author
    
    if current_author == target_author:
        messages.error(request, "You cannot follow yourself.")
        return redirect('author_profile', id=author_id)
    
    if Follow.objects.filter(user=current_author, following=target_author).exists():
        messages.info(request, "You are already following this author.")
        return redirect('author_profile', id=author_id)
    
    if FollowRequest.objects.filter(actor=current_author, object=target_author).exists():
        messages.info(request, "Follow request already sent.")
        return redirect('author_profile', id=author_id)
    
    FollowRequest.objects.create(actor=current_author, object=target_author)
    messages.success(request, "Follow request sent!")
    return redirect('author_profile', id=author_id)


# Single Author API
@api_view(['GET', 'PUT'])
def author_serial(request, author_serial):
    """
    GET [local, remote]: retrieve AUTHOR_SERIAL's profile
    PUT [local]: update AUTHOR_SERIAL's profile
    """
    # GET returns the authors profile information
    if request.method == 'GET':
        author = get_object_or_404(Author, id=author_serial)
        serializer = SingleAuthorSerializer(author, context={'request': request})
        return Response(serializer.data)
    
    # PUT Updates the authors profile information
    elif request.method == 'PUT':
        author = get_object_or_404(Author, id=author_serial)
        serializer = SingleAuthorSerializer(author, data=request.data,partial= True, context={'request': request})

        # Valid update data
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        
        # Invalid update data
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    # Invalid method
    else:
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)


@api_view(['GET'])
def author_fqid(request, author_fqid):
    """
    GET [local]: retrieve AUTHOR_FQID's profile
    """
    
    # GET returns the authors profile information
    if request.method == 'GET':

        decoded_fqid = unquote(author_fqid)

        # Ensure request is not None
        if request is None:
            return Response({"error": "Invalid request object"}, status=status.HTTP_400_BAD_REQUEST)

        author = get_object_or_404(Author, fqid=decoded_fqid)

        serializer = SingleAuthorSerializer(author, context={'request': request})

        return Response(serializer.data)

    # Invalid method
    else:
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)


@login_required
def followers(request, author_id):
    # Get the Author instance for the given author_id (from URL)
    user_author = get_object_or_404(Author, id=author_id)
    # Get all Follow instances where this author is being followed.
    followers_qs = Follow.objects.filter(following=user_author)
    # Extract the authors who are following this user.
    follower_authors = [follow.user for follow in followers_qs]
    
    context = {
        'follower_authors': follower_authors,
        'author': user_author
    }
    
    return render(request, 'followers.html', context)


@login_required
def following(request, author_id):
    user_author = get_object_or_404(Author, id=author_id)

    follow_qs = Follow.objects.filter(user=user_author)
    
    # Build a list of dictionaries with both author and follow id
    following_data = [
        {'author': follow.following, 'follow_id': follow.id} for follow in follow_qs
    ]
    
    context = {
        'following_data': following_data,
        'author': user_author
    }
    return render(request, 'following.html', context)


# Followers API
@api_view(['GET'])
def followersAPI(request, author_serial):
    """
    GET [local, remote]: get a list of authors who are AUTHOR_SERIAL's followers

    api/authors/<uuid:author_serial>/followers/
    """
    # Get the Author instance for the given author_id (from URL)
    author = get_object_or_404(Author, id=author_serial)

    # Get all Follow instances where this author is being followed.
    followers_qs = Follow.objects.filter(following=author)
    
    # Extract the authors who are following this user.
    followers = [follow.user for follow in followers_qs]
    # Serialize the followers
    serializer = SingleAuthorSerializer(followers, many=True, context={'request': request})

    response_content = {
        'type': 'followers',
        'followers': serializer.data,
    }
    
    return Response(response_content)


@api_view(['GET','PUT','DELETE'])
@permission_classes([IsAuthenticated])  # Ensure the user is authenticated
def specific_follower_details(request, author_serial, foreign_author_fqid):
    """
    api/authors/<uuid:author_serial>/followers/<path:foreign_author_fqid>/

    DELETE [local]: remove FOREIGN_AUTHOR_FQID as a follower of AUTHOR_SERIAL (must be authenticated)
    PUT [local]: Add FOREIGN_AUTHOR_FQID as a follower of AUTHOR_SERIAL (must be authenticated)
    GET [local, remote] check if FOREIGN_AUTHOR_FQID is a follower of AUTHOR_SERIAL
        - Should return 404 if they're not
        - This is how you can check if follow request is accepted
    """

    # Get the Author instance for the given author_serial
    author = get_object_or_404(Author, id=author_serial)

    # Get the Foreign Author instance for the given foreign_author_fqid
    foreign_author = get_object_or_404(Author, fqid=foreign_author_fqid)
    
    if request.method == 'GET':
        # Check if foreign_author is a follower of author
        follow_result = Follow.objects.filter(user=foreign_author, following=author)

        # 404 if author is not following foreign author
        if follow_result.exists():
            serializer = SingleAuthorSerializer(foreign_author, context={'request': request})
            return Response(serializer.data)
        else:
            return Response(status=status.HTTP_404_NOT_FOUND)

        # TODO: Check if forgien authour is following author serial on remote server


    elif request.method == 'PUT':
        # Add foreign_author as a follower of author
        follow, created = Follow.objects.get_or_create(user=foreign_author, following=author)
        if created:
            return Response({"message": "FOREIGN_AUTHOR_FQID added as a follower of AUTHOR_SERIAL"}, status=status.HTTP_201_CREATED)
        else:
            return Response({"message": "FOREIGN_AUTHOR_FQID is already a follower of AUTHOR_SERIAL"}, status=status.HTTP_200_OK)

    elif request.method == 'DELETE':
        # Remove foreign_author as a follower of author
        follow_result = Follow.objects.filter(user=foreign_author, following=author)
        if follow_result.exists():
            follow_result.delete()
            return Response({"message": "FOREIGN_AUTHOR_FQID removed as a follower of AUTHOR_SERIAL"}, status=status.HTTP_204_NO_CONTENT)
        else:
            return Response({"error": "FOREIGN_AUTHOR_FQID is not a follower of AUTHOR_SERIAL"}, status=status.HTTP_404_NOT_FOUND)
            
    else:
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)



@api_view(['POST'])
@authentication_classes([BasicAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated])
#@permission_classes([AllowAny])
def send_inbox(request, author_serial):
    """
    POST [remote]: comment on a post by AUTHOR_SERIAL
    Body is a comment object

    api/authors/<uuid:author_serial>/inbox
    """

    print(f"Request Method: {request.method}")
    print(f"request data: {request.data}")
    print(f"Author Serial: {author_serial}")

    if request.method == "POST":
        #decoded_fqid = unquote(author_fqid)
        author = get_object_or_404(Author, id=author_serial)
        data = request.data.copy()

        # "if the type is "comment" then add that comment to AUTHOR_SERIAL's inbox"
        if data['type'] == 'comment':

            logger.info(f"Comment data send_inbox: {data}")
            serializer = SingleCommentSerializer(data=data, context={'request': request})

            if serializer.is_valid():
                comment = serializer.save()
                
                logger.info(f"Comment data send_inbox: Valid data")

                # Add the comment to the author's inbox
                InboxItem.objects.create(
                    recipient = author,
                    sender = comment.author,
                    content_type = ContentType.objects.get_for_model(comment),
                    object_id=comment.id
                )

                post = comment.post

                #logger.info(f"Sending post to remote nodes")
                #logger.info(f"post: {post}")
                #logger.info(f"author: {author}")
                #send_post_to_remote_followers(request, post, author)

                return Response({"message": "Comment added to Inbox"}, status=status.HTTP_201_CREATED)
            
            else:
                logger.error(f"Validation errors: {serializer.errors}")
                return Response({"error": "Invalid Comment type"}, status=status.HTTP_400_BAD_REQUEST)
        
        # "if the type is "Like" then add that like to AUTHOR_SERIAL's inbox"
        elif data['type'] == 'like':

            # Extract the object being liked from the like data
            object_fqid = data.get('object')
            if not object_fqid:
                return Response({"error": "Missing 'object' field in Like"}, status=status.HTTP_400_BAD_REQUEST)
            
            # Find the target object (Post or Comment)
            target_object, content_type = get_object_by_fqid(object_fqid)
            if not target_object:
                return Response({"error": f"Object with fqid '{object_fqid}' not found"}, status=status.HTTP_404_NOT_FOUND)
            
            # Add object info to the data
            data['object_id'] = target_object.id
            data['content_type'] = content_type.model

            serializer = SingleLikeSerializer(data=data)
            if serializer.is_valid():
                like = serializer.save()

                # Add the like to the author's inbox
                InboxItem.objects.create(
                    recipient=author,
                    sender=like.author,
                    content_type=ContentType.objects.get_for_model(like),
                    object_id=like.id
                )

                if like.content_type.model == 'post':
                    post = like.content_object
                else:
                    post = like.content_object.post


                #logger.info(f"Sending post to remote nodes")
                #logger.info(f"post: {post}")
                #logger.info(f"author: {author}")
                #send_post_to_remote_followers(request, post, author)

                return Response({"message": "Like added to Inbox"}, status=status.HTTP_201_CREATED)
            
            else:
                logger.error(f"Validation errors: {serializer.errors}")
                return Response({"error": "Invalid Like type"}, status=status.HTTP_400_BAD_REQUEST)
        
        # "if the type is "follow" then add that follow is added to AUTHOR_SERIAL's inbox to approve later"
        elif data['type'] == 'follow':
            serializer = SingleFollowRequestSerializer(data=data)
            if serializer.is_valid():
                follow_request = serializer.save()

                # Add the follow request to the author's inbox
                InboxItem.objects.create(
                    recipient=follow_request.object,
                    sender=follow_request.actor,
                    content_type=ContentType.objects.get_for_model(follow_request),
                    object_id=follow_request.id
                )
                return Response({"message": "Follow request added to Inbox"}, status=status.HTTP_201_CREATED)
            
            else:
                logger.error(f"Validation errors: {serializer.errors}")
                return Response({"error": "Invalid Follow type"}, status=status.HTTP_400_BAD_REQUEST)
        
        # "if the type is "post" then add that post to AUTHOR_SERIAL's inbox"
        elif data['type'] == 'post':

            logger.info(f"Post data send_inbox: {data}")
            serializer = SinglePostSerializer(data=data, context={'request': request})
            if serializer.is_valid():
                post = serializer.save()

                # Add the post to the author's inbox
                InboxItem.objects.create(
                    recipient=author,
                    sender=post.author,
                    content_type=ContentType.objects.get_for_model(post),
                    object_id=post.id
                )
                return Response({"message": "Post added to Inbox"}, status=status.HTTP_201_CREATED)
            
            else:
                logger.error(f"Post Validation errors: {serializer.errors}")
                return Response({"error": "Invalid Post type"}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({"error": "Invalid type"}, status=status.HTTP_400_BAD_REQUEST)
    else:
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)

@login_required
def accept_follow_request(request, request_id):
    # Using POST method for accept, so if it's not POST, you may want to handle that.
    if request.method == 'POST':
        follow_request = get_object_or_404(FollowRequest, id=request_id)
        
        # Create a Follow entry
        Follow.objects.create(user=follow_request.actor, following=follow_request.object)

        # Delete the request after approval
        follow_request.delete()

        return redirect('mailbox')
    else:
        return redirect('mailbox')

@login_required
def deny_follow_request(request, request_id):
    # Get the follow request or return 404 if not found
    follow_req = get_object_or_404(FollowRequest, id=request_id)
    
    # Simply delete the follow request to deny it
    follow_req.delete()
    
    return redirect('mailbox')

@login_required
def unfollow(request, follow_id):
    # Get the Follow instance by its primary key.
    follow_instance = get_object_or_404(Follow, id=follow_id)
    
    # Check that the logged-in user is the one following
    if follow_instance.user == request.user.author:
        follow_instance.delete()
    # Redirect back to the following page or mailbox
    return redirect('following', author_id=request.user.author.id)


# Done (simple testing only)
@api_view(['GET'])
def post_fqid(request, post_fqid):
    """
    GET [local] get the public post whose URL is POST_FQID
        - friends-only posts: must be authenticated

    api/posts/<path:post_fqid>
    """
    if request.method == 'GET':

        decoded_fqid = unquote(post_fqid)

        # Ensure request is not None
        if request is None:
            return Response({"error": "Invalid request object"}, status=status.HTTP_400_BAD_REQUEST)
        
        post = get_object_or_404(Post, fqid=decoded_fqid)

        if post.visibility == 'PUBLIC':
            serializer = SinglePostSerializer(post, context={'request': request})
            return Response(serializer.data)
            #return Response({"Public Post": "No available post."}, status=status.HTTP_404_NOT_FOUND)
        
        # Ensure verification for Friends only posts
        elif post.visibility == 'FRIENDS':
            if not request.user.is_authenticated:
                return Response({"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)
            
            if not are_friends(request.user.author, post.author):
                return Response({"error": "You are not authorized to view this post"}, status=status.HTTP_403_FORBIDDEN)
            
            serializer = SinglePostSerializer(post, context={'request': request})
            return Response(serializer.data)
           
        else:
            return Response({"error": "No available post."}, status=status.HTTP_404_NOT_FOUND)


#TODO: IMPLEMENT POST IMAGES Be aware that Posts can be images that need base64 decoding. posts can also hyperlink to images that are public
@api_view(['GET','POST'])
@authentication_classes([SessionAuthentication, BasicAuthentication])
@permission_classes([IsAuthenticated])
def recent_author_post(request, author_serial):
    """
    GET [local, remote] get the recent posts from author AUTHOR_SERIAL (paginated)
        - Not authenticated: only public posts.
        - Authenticated locally as author: all posts.
        - Authenticated locally as follower of author: public + unlisted posts.
        - Authenticated locally as friend of author: all posts.
        - Authenticated as remote node: This probably should not happen. Remember, the way remote node becomes aware of local posts is by local node pushing those posts to inbox, not by remote node pulling.
    
    POST [local] create a new post but generate a new ID
        - Authenticated locally as author


    api/authors/<uuid:author_serial>/posts/
    """
    if request.method == 'GET':
        author = get_object_or_404(Author, id=author_serial)
        
        authors_followers = Follow.objects.filter(following=author).values_list('user', flat=True)
        following = Follow.objects.filter(user=author).values_list('following', flat=True)
        friends = list(set(authors_followers).intersection(set(following)))

        # Authenticated locally as author: all posts.
        if request.user.is_authenticated and (request.user.author == author or request.user.author in friends):
            posts = Post.objects.filter(author=author).order_by('-published')
        
        # Authenticated locally as follower of author: public + unlisted posts.
        elif request.user.is_authenticated and request.user.author in authors_followers:
            posts = Post.objects.filter(Q(author=author) & (Q(visibility='PUBLIC') | Q(visibility='UNLISTED'))).order_by('-published')

        # Not authenticated: only public posts.
        else:
            posts = Post.objects.filter(author=author, visibility='PUBLIC').order_by('-published')

        # Apply pagination
        paginator = CustomPageNumberPagination()
        paginated_posts = paginator.paginate_queryset(posts, request)
        if paginated_posts is not None:
            serializer = SinglePostSerializer(paginated_posts, many=True, context={'request': request})
            return paginator.get_paginated_response(serializer.data)
        else:
            serializer = SinglePostSerializer(posts, many=True, context={'request': request})
            return Response(serializer.data)
        
    # POST [local] create a new post but generate a new ID
    elif request.method == 'POST':

        # Authenticated locally as author
        author = get_object_or_404(Author, id=author_serial)
        if request.user.is_authenticated and request.user.author == author:
            data = request.data
            content_type = data.get('contentType')
            content = data.get('content')
            title = data.get('title')
            visibility = data.get('visibility', 'PUBLIC')
                
            if content_type == 'text/markdown':
                html_content = markdown.markdown(content)
                # Save the HTML content in the database
                post = Post(
                    author=author,
                    title=title,
                    content=html_content,  # Save the HTML content
                    contentType=content_type,
                    visibility=visibility,
                )
                post.save()
                
            
            else:
                post = Post(
                    author=author,
                    title=title,
                    content=content,
                    contentType=content_type,
                    visibility=visibility,
                )
                post.save()

            serializer = SinglePostSerializer(post)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    else:
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)



# Got majority of this function from AI
@login_required
def search_authors(request):
    query = request.GET.get('q', '')
    selected_host = request.GET.get('host', '')
    
    # Get all available hosts for the dropdown
    nodes = Node.objects.filter(is_active=True)
    available_hosts = []

    # Include local host
    available_hosts.append({
        'value': 'http://' + str(settings.CURRENT_DOMAIN) + '/api/',
        'label': f'Local ({settings.CURRENT_DOMAIN}) aka the cool server'
    })

    # Add remote nodes with friendly names
    for node in nodes:
        available_hosts.append({
            'value': node.host,
            'label': f"{node.team_name or 'Unknown'} ({node.host.split('//')[1].split('/')[0]})"
        })

    local_authors = []
    remote_authors = []

    local_authors = Author.objects.all().exclude(user__username__icontains="API").exclude(user__username__icontains="test-") 
    
    # Search local authors
    if query:
        local_authors = local_authors.filter(
            Q(display_name__icontains=query) | 
            Q(user__username__icontains=query)
        ).exclude(id=request.user.author.id) # Exclude the current user

    if selected_host:
        local_authors = local_authors.filter(host=selected_host)
    
    # Search remote nodes
    #if query:
    # Get all active nodes
    nodes = Node.objects.filter(is_active=True)

    for node in nodes:
        node_host = node.host.rstrip('/')
        try:
            
            if node.team_name == "dodger-blue":
                node_url = node_host + f'/authors'
            else:
                node_url = node_host + f'/authors/'


            logger.info("node_url = " + node_url)
            auth = (node.username, node.password)

            if node.team_name == "dodger-blue" or node.team_name == "salmon":
                response = requests.get(
                node_url,
                #auth=auth,
                timeout=10,  # 10 second timeout
                verify=False  # Only if certificate verification is causing issues
                )
            elif node.team_name == "bisque":
                response = requests.get(
                node_url + "?size=100",
                #auth=auth,
                timeout=10,  # 10 second timeout
                verify=False  # Only if certificate verification is causing issues
                )
            else:
                response = requests.get(
                    node_url,
                    auth=auth,
                    timeout=10,  # 10 second timeout
                    verify=False  # Only if certificate verification is causing issues
                )
            
            if response.status_code == 200:
                try:

                    if response.content.strip():
                        logger.error(f"\n\nresponse: {response}\n\n")
                        
                        data = response.json()
                        logger.error(f"\n\nresponse data: {data}\n\n")
                        # Process the response data - adjust according to the API format
                        if 'authors' in data:
                            for author_data in data['authors']:
                                logger.error(f"\n\nauthor_data: {author_data}\n\n")
                                # Create or update remote author in local database
                                serializer = SingleAuthorSerializer(data=author_data)
                                if serializer.is_valid():
                                    remote_author = serializer.save()
                                    remote_authors.append(remote_author)
                                else:
                                    logger.error(f"\n\ninvalid author: {serializer.errors}\n\n")
                except ValueError as e:
                    logger.error(f"Invalid JSON response: {e}")
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error: {e}")
            # Gracefully handle the network error
            # Consider adding a flag to indicate the remote API is unavailable
        except requests.exceptions.Timeout:
            logger.error("Request timed out")
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error: {e}")


    # Combine local and remote results
    current_author_id = request.user.author.id 

    local_author_ids = {author.id for author in local_authors}
    unique_remote_authors = [author for author in remote_authors if author.id not in local_author_ids]
    all_authors = list(local_authors) + unique_remote_authors

    # If there's a search query, apply it to the final combined list
    if query:
        all_authors = [author for author in {author.id: author for author in all_authors}.values() 
                    if author.id != current_author_id and 
                    (query.lower() in (author.display_name or '').lower() or
                    query.lower() in (getattr(author, 'name', '') or '').lower() or
                    query.lower() in (getattr(author.user, 'username', '') or '').lower() if hasattr(author, 'user') and author.user else False)]
    else:
        # Original line without query filtering
        all_authors = [author for author in {author.id: author for author in all_authors}.values() 
                    if author.id != current_author_id]
    
    
    context = {
        'authors': local_authors,
        'query': query,
        'selected_host': selected_host,
        'available_hosts': available_hosts,
    }
    return render(request, 'search_authors.html', context)


# Image Posts
@api_view(['GET'])
@authentication_classes([])  # No authentication required
@permission_classes([AllowAny])
def public_post_image_serial(request, author_serial, post_serial):
    """
    GET [local, remote] get the public post converted to binary as an image.
    return 404 if not an image.
    This end point serves the image file directly from the filesystem.
    """
    # Fetch the post
    post = Post.objects.get(id=post_serial, author_id=author_serial)
        
    # Check if the post is an image
    if post.contentType not in ['image/png;base64', 'image/jpeg;base64', 'application/base64']:
        return Response({"error": "Post is not an image"}, status=status.HTTP_404_NOT_FOUND)
        
    # Get the file path from the content field
    file_path = post.content
    file_path = unquote(file_path)
    
    # Remove the leading '/media/' prefix
    if file_path.startswith('/media/'):
        file_path = file_path[len('/media/'):]
        
        
    # Construct the full path to the file
    full_path = os.path.join(settings.MEDIA_ROOT, file_path)
        
        
    # Check if the file exists
    if not os.path.exists(full_path):
        return Response({"error": "Image not found"}, status=status.HTTP_404_NOT_FOUND)
        
    # Determine the content type based on the file extension
    if post.contentType == 'image/png;base64':
        content_type = 'image/png'
    elif post.contentType == 'image/jpeg;base64':
        content_type = 'image/jpeg'
    else:
        content_type = 'application/octet-stream'  # Generic binary data
        
    # Open the file and read its content
    with open(full_path, 'rb') as image_file:
        image_data = image_file.read()


    # Return the image as a response
    return HttpResponse(image_data, content_type=content_type)
    
    
# NOTE: THis base 64 handeling is from GPT
@api_view(['GET'])
def public_post_image_fqid(request, post_fqid):
    """
    GET [local, remote] get the public post converted to base64.
    return 404 if not an image.
    This endpoint returns the image as base64 encoded data, regardless of how it's stored.

    api/posts/<path:post_fqid>/image/
    """
    # Decode URL
    post_fqid = unquote(post_fqid)
    
    # Fetch the post
    post = get_object_or_404(Post, fqid=post_fqid)
        
    # Check if the post is an image
    if post.contentType not in ['image/png;base64', 'image/jpeg;base64', 'application/base64']:
        return Response({"error": "Post is not an image"}, status=status.HTTP_404_NOT_FOUND)
    
    # Determine content type and mime type
    mime_type = None
    if post.contentType == 'image/png;base64':
        content_type = 'image/png'
        mime_type = 'image/png'
    elif post.contentType == 'image/jpeg;base64':
        content_type = 'image/jpeg'
        mime_type = 'image/jpeg'
    else:
        content_type = 'application/octet-stream'
        mime_type = 'application/octet-stream'
    
    # Get the image data as binary first
    try:    
        # Check if content is a filepath or base64 data
        if post.content.startswith('/media/') or post.content.startswith('media/'):
            # It's a file path
            file_path = post.content
            if file_path.startswith('/media/'):
                file_path = file_path[len('/media/'):]
            elif file_path.startswith('media/'):
                file_path = file_path[len('media/'):]
                
            full_path = os.path.join(settings.MEDIA_ROOT, file_path)
            
            if not os.path.exists(full_path):
                return Response({"error": "Image file not found"}, status=status.HTTP_404_NOT_FOUND)
                
            with open(full_path, 'rb') as image_file:
                image_data = image_file.read()
        
        elif post.content.startswith('data:'):
            # It's inline base64 data (data URI)
            try:
                # Format: data:image/png;base64,iVBORw0KGg...
                format_data, encoded_data = post.content.split(',', 1)
                
                # Return the existing base64 data without re-encoding
                return Response({
                    "base64_image": encoded_data,
                    "content_type": content_type,
                    "data_uri": post.content
                })
            except Exception as e:
                return Response({"error": f"Failed to decode base64 data: {str(e)}"}, 
                            status=status.HTTP_400_BAD_REQUEST)
        
        else:
            # Assume it's just base64 encoded data without the prefix
            try:
                # It's already base64, return it directly
                return Response({
                    "base64_image": post.content,
                    "content_type": content_type
                })
            except Exception as e:
                # If there's an error, try to decode and re-encode it
                image_data = base64.b64decode(post.content)
        
        # Convert binary image data to base64
        base64_data = base64.b64encode(image_data).decode('utf-8')
        
        # Create data URI
        data_uri = f"data:{mime_type};base64,{base64_data}"
        
        # Return both the base64 data and the full data URI
        return Response({
            "base64_image": base64_data,
            "content_type": content_type,
            "data_uri": data_uri
        })
    
    except Exception as e:
        logger.error(f"Error processing image: {e}")
        return Response({"error": f"Failed to process image: {str(e)}"}, 
                      status=status.HTTP_400_BAD_REQUEST)
    


# Done (simple testing only)
@api_view(['GET'])
def comments_on_post(request, author_serial, post_serial):
    """
    GET [local, remote]: the comments on the post
    Body is a comments object

    api/authors/<uuid:author_serial>/posts/<uuid:post_serial>/comments
    """
    if request.method == "GET":
        author = get_object_or_404(Author, id=author_serial)
        post = get_object_or_404(Post, id=post_serial, author=author)
        serializer = MultiCommentSerializer(post, context={'request': request})

        if serializer.data:
            return Response(serializer.data)
        else:
            return Response({"detail": "No comment found."}, status=status.HTTP_404_NOT_FOUND)
    else:
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)


# Done (simple testing only)
@api_view(['GET'])
@authentication_classes([SessionAuthentication, BasicAuthentication])
@permission_classes([IsAuthenticated])
def comments_on_post_fqid(request, post_fqid):
    """
    GET [local, remote]: the comments on the post (that our server knows about)
    Body is a comments object
    """
    if request.method == "GET":
        decoded_fqid = unquote(post_fqid)

        # Ensure request is not None
        if request is None:
            return Response({"error": "Invalid request object"}, status=status.HTTP_400_BAD_REQUEST)

        post = get_object_or_404(Post, fqid=decoded_fqid)
        comments = Comment.objects.filter(post=post).order_by('-published')
        serializer = MultiCommentSerializer(comments, many=True)
        return Response(serializer.data)
    else:
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)


# Done (simple testing only)
@api_view(['GET'])
def get_comment(request, author_serial, post_serial, remote_comment_fqid):
    """
    GET [local, remote] get the comment

    api/authors/<uuid:author_serial>/post/<uuid:post_serial>/comment/<path:remote_comment_fqid>
    """
    if request.method == "GET":
        author = get_object_or_404(Author, id=author_serial)
        post = get_object_or_404(Post, id=post_serial, author=author)
        comment = get_object_or_404(Comment, fqid=remote_comment_fqid, post=post)

        serializer = SingleCommentSerializer(comment, context={'request': request})

        if serializer.data:
            return Response(serializer.data)
        else:
            return Response({"detail": "No comment found."}, status=status.HTTP_404_NOT_FOUND)
    else:
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)


# Commented API Endpoints -----------------------------------------------------------------------------------------------

# GET Done (simple testing only)
# POST Done (simple testing only)
@api_view(['GET', 'POST'])
def comment_author_post_serial(request, author_serial):
    """
    GET [local, remote] get the list of comments author has made on:
        - [local] any post
        - [remote] public and unlisted posts
        - paginated

    POST [local] if you post an object of "type":"comment", it will add your comment to the post whose ID is in the post field
        - Then the node you posted it to is responsible for forwarding it to the correct inbox
    
    api/authors/<uuid:author_serial>/commented
    """
    if request.method == 'GET':  
        author = get_object_or_404(Author, id=author_serial)

        serializer = MultiCommentSerializer(author, context={'request': request})

        if serializer.data:
            return Response(serializer.data)
        else:
            return Response({"detail": "No comment found."}, status=status.HTTP_404_NOT_FOUND)
        
    elif request.method == 'POST':
        try:
            data = request.data
            logger.debug(f"Request data: {data}")
        except Exception as e:
            logger.error(f"Error processing request data: {e}")
            return Response({"error": "Invalid JSON data"}, status=status.HTTP_400_BAD_REQUEST)

        if data.get("type") == "comment":
            author = get_object_or_404(Author, id=author_serial)
            data['author'] = SingleAuthorSerializer(author).data  # Ensure the author is passed as a dictionary

            post_fqid = data.get('post')
            if post_fqid:
                post = get_object_or_404(Post, fqid=post_fqid)
                data['post_fqid'] = post.fqid  # Ensure the post fqid is passed as a string

                serializer = SingleCommentSerializer(data=data, context={'request': request})
                serializer.is_valid(raise_exception=True)
                comment = serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            else:
                return Response({"error": "Post fqid is missing"}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({"error": "Invalid type"}, status=status.HTTP_400_BAD_REQUEST)
    else:
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)


# Done (simple testing only)
@api_view(['GET'])
def comment_author_post_fqid(request, author_fqid):
    """
    GET [local] get the list of comments author has made on any post (that local node knows about)

    api/authors/<path:author_fqid>/commented
    """
    if request.method == 'GET':
        decoded_fqid = unquote(author_fqid)
        author = get_object_or_404(Author, fqid=decoded_fqid)
        comment = get_object_or_404(Comment, author=author)
        serializer = SingleCommentSerializer(comment, context={'request': request})

        if serializer.data:
            return Response(serializer.data)
        else:
            return Response({"detail": "No comment found."}, status=status.HTTP_404_NOT_FOUND)

    else:
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)


# Done (simple testing only)
@api_view(['GET'])
def specific_author_comments(request, author_serial, comment_serial):
    """
    GET [local, remote] get this comment

    api/authors/<uuid:author_serial>/commented/<uuid:comment_serial>
    """
    if request.method == 'GET':
        author = get_object_or_404(Author, id=author_serial)
        comment = get_object_or_404(Comment, id=comment_serial, author=author)
        serializer = SingleCommentSerializer(comment, context={'request': request})

        if serializer.data:
            return Response(serializer.data)
        else:
            return Response({"detail": "No comment found."}, status=status.HTTP_404_NOT_FOUND)
    else:
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)


# Done (simple testing only)
@api_view(['GET'])
def specific_author_comment(request, comment_fqid):
    """
    GET [local, remote] get this comment

    api/commented/<path:comment_fqid>
    """
    if request.method == 'GET':
        decoded_fqid = unquote(comment_fqid)
        comment = get_object_or_404(Comment, fqid=decoded_fqid)
        serializer = SingleCommentSerializer(comment, context={'request': request})

        if serializer.data:
            return Response(serializer.data)
        else:
            return Response({"detail": "No comment found."}, status=status.HTTP_404_NOT_FOUND)

    else:
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)





# LikeS API Endpoints -----------------------------------------------------------------------------------------------

# Done (simple testing only)
@api_view(['GET'])
def who_liked_this_post_serial(request, author_serial, post_serial):
    """
    "Who Liked This Post"
    GET [local, remote] a list of likes from other authors on AUTHOR_SERIAL's post POST_SERIAL
    Body is likes object

    api/authors/<uuid:author_serial>/posts/<uuid:post_serial>/likes
    """

    if request.method == 'GET':
        author = get_object_or_404(Author, id=author_serial)
        post = get_object_or_404(Post, id=post_serial, author=author)
        serializer = SinglePostSerializer(post, context={'request': request})

        if serializer.data:
            return Response(serializer.data)
        else:
            return Response({"detail": "No likes found."}, status=status.HTTP_404_NOT_FOUND)
    else:
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)


# Done (simple testing only)
@api_view(['GET'])
def who_liked_this_post_fqid(request, post_fqid):
    """
    "Who Liked This Post"
    GET [local] a list of likes from other authors on AUTHOR_SERIAL's post POST_SERIAL
    Body is likes object

    api/posts/<path:post_fqid>/likes
    """
    if request.method == 'GET':
        decoded_fqid = unquote(post_fqid)

        post = get_object_or_404(Post, fqid=decoded_fqid)

        serializer = MultiLikeSerializer(post, context={'request': request})

        if serializer.data:
            return Response(serializer.data)
        else:
            return Response({"detail": "No likes found."}, status=status.HTTP_404_NOT_FOUND)
    else:
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)


# Done (simple testing only)
@api_view(['GET'])
def who_liked_this_comment(request, author_serial, post_serial, comment_fqid):
    """
    "Who Liked This Comment"
    GET [local, remote] a list of likes from other authors on AUTHOR_SERIAL's post POST_SERIAL comment COMMENT_FQID
    Body is likes object

    api/authors/<uuid:author_serial>/posts/<uuid:post_serial>/comments/<path:comment_fqid>/likes
    """
    if request.method == 'GET':

        decoded_fqid = unquote(comment_fqid)

        comment = get_object_or_404(Comment, fqid=decoded_fqid)

        serializer = MultiLikeSerializer(comment, context={'request': request})

        if serializer.data:
            return Response(serializer.data)
        else:
            return Response({"detail": "No likes found."}, status=status.HTTP_404_NOT_FOUND)
    else:
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)



# LikeD API Endpoints -----------------------------------------------------------------------------------------------

# Done (simple testing only)
@api_view(['GET'])
def things_liked_by_author_serial(request, author_serial):
    """
    "Things Liked By Author"
    GET [local, remote] a list of likes by AUTHOR_SERIAL
    Body is likes object

    api/authors/<uuid:author_serial>/liked
    """
    if request.method == 'GET':
        author = get_object_or_404(Author, id=author_serial)
        likes = Like.objects.filter(author=author)
        paginator = SrcPagination()
        page = paginator.paginate_queryset(likes, request)
        serializer = SingleLikeSerializer(page, many=True, context={'request': request})

        if serializer.data:
            paginated_response = paginator.get_paginated_response(serializer.data)
            return Response({
                "type": "likes",
                "page": request.build_absolute_uri(),
                "id": request.build_absolute_uri(),
                "page_number": paginated_response.data.get('page', 1),
                "size": paginated_response.data.get('page_size', 10),
                "count": paginated_response.data.get('count', 0),
                "src": paginated_response.data.get('results', [])
            })
        else:
            return Response({"detail": "No likes found."}, status=status.HTTP_404_NOT_FOUND)
    else:
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)


# Done (simple testing only)
@api_view(['GET'])
def get_single_like_serial(request, author_serial, like_serial):
    """
    GET [local, remote] a single like
    Body is like object

    api/authors/<uuid:author_serial>/liked/<uuid:like_serial>
    """
    if request.method == 'GET':
        author = get_object_or_404(Author, id=author_serial)
        likes = Like.objects.filter(author=author, id=like_serial)
        serializer = SingleLikeSerializer(likes, many=True)
        
        if serializer.data:
            return Response(serializer.data[0])
        else:
            return Response({"detail": "No likes found."}, status=status.HTTP_404_NOT_FOUND)
    
    else:
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)


# Done (simple testing only)
@api_view(['GET'])
def things_liked_by_author_fqid(request, author_fqid):
    """
    "Things Liked By Author"
    GET [local] a list of likes by AUTHOR_FQID
    Body is likes object

    api/authors/<path:author_fqid>/liked
    """
    if request.method == 'GET':

        decoded_fqid = unquote(author_fqid)

        author = get_object_or_404(Author, fqid=decoded_fqid)
        likes = Like.objects.filter(author=author)
        paginator = SrcPagination()
        page = paginator.paginate_queryset(likes, request)
        serializer = SingleLikeSerializer(page, many=True, context={'request': request})

        if serializer.data:
            paginated_response = paginator.get_paginated_response(serializer.data)
            return Response({
                "type": "likes",
                "page": request.build_absolute_uri(),
                "id": request.build_absolute_uri(),
                "page_number": paginated_response.data.get('page', 1),
                "size": paginated_response.data.get('page_size', 10),
                "count": paginated_response.data.get('count', 0),
                "src": paginated_response.data.get('results', [])
            })
        else:
            return Response({"detail": "No likes found."}, status=status.HTTP_404_NOT_FOUND)
    else:
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)


# Done (simple testing only)
@api_view(['GET'])
def get_single_like_fqid(request, like_fqid):
    """
    GET [local] a single like
    Body is like object

    api/liked/<path:like_fqid>
    """
    if request.method == 'GET':

        decoded_fqid = unquote(like_fqid)

        likes = Like.objects.filter(fqid=decoded_fqid)
        serializer = SingleLikeSerializer(likes, many=True)
        
        if serializer.data:
            return Response(serializer.data[0])
        else:
            return Response({"detail": "No likes found."}, status=status.HTTP_404_NOT_FOUND)
    
    else:
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)



def proxy_image(request, url):
    # Decode the URL if it's encoded
    from urllib.parse import unquote
    url = unquote(url)
    
    # Get the image from the remote server
    response = requests.get(url)
    
    # Return the image data with appropriate content type
    return HttpResponse(
        response.content,
        content_type=response.headers.get('Content-Type', 'image/jpeg')
    )
