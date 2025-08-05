from django.urls import path, include
from django.views.generic.base import RedirectView, TemplateView
from . import views
from rest_framework.routers import DefaultRouter
from .views import PostViewSet, AuthorViewSet, AuthorListView, PostDetailView, author_profile

router = DefaultRouter()
router.register(r'posts', PostViewSet)
router.register(r'authors', AuthorViewSet, basename="author")


urlpatterns = [

    path('proxy-image/<path:url>/', views.proxy_image, name='proxy_image'),

    path('redirect/', views.post_login_redirect, name='post_login_redirect'),
    path('waiting-approval/', TemplateView.as_view(template_name="waiting_approval.html"), name='waiting_approval'),
    # path('accounts/', views.manage_accounts, name='manage_accounts'),
    path('accounts/', views.manage_accounts, name='manage_accounts'),
    path('toggle-approval/', views.toggle_approval, name='toggle_approval'),
    path('approve-user/<uuid:author_id>/', views.approve_user, name='approve_user'),
    
    path('dashboard/', views.stream, name='stream'),
    path('logout/', views.custom_logout, name='custom_logout'),
    path('', RedirectView.as_view(url='/accounts/login/')),  # Redirect root to login
    path('create-post/', views.create_post, name='create_post'),
    path('profile/', views.view_profile, name='view_profile'),  # View Profile
    path('authors/<uuid:id>/', author_profile, name='author_profile'), 
    # path('authors/<uuid:author_id>/follow/', views.send_follow_request, name='send_follow_request'),
    path('authors/<uuid:author_id>/toggle-follow/', views.toggle_follow, name='toggle_follow'),
    

    path("authors/<uuid:author_id>/followers/", views.followers, name="followers"),
    path("authors/<uuid:author_id>/following/", views.following, name="following"),
    #path('authors/<uuid:author_serial>/inbox', views.follow_request, name='follow_request'), # Send a follow request to AUTHOR_SERIAL
    path("mailbox/", views.mailbox, name="mailbox"),
    path("mailbox/approve/<uuid:request_id>/", views.accept_follow_request, name="accept_follow_request"),
    path("mailbox/deny/<uuid:request_id>/", views.deny_follow_request, name="deny_follow_request"),
    path("follow/unfollow/<int:follow_id>/", views.unfollow, name="unfollow"),
    path("mailbox/delete/<uuid:object_uuid>", views.delete_inbox_item, name="delete_inbox_item"),
    
    path('my_posts/', views.my_posts, name='my_posts'),
    path('posts/<str:post_id>/edit/', views.edit_post, name='edit_post'),
    path('posts/<str:post_id>/delete/', views.delete_post, name='delete_post'),

    path('like/<uuid:item_uuid>/', views.like_item, name='like_item'),
    path('post/<uuid:post_id>/', views.single_post, name='single_post'),
    path('post/<uuid:post_id>/comment', views.add_comment, name="add_comment"),
    
    
    path('search/', views.search_authors, name='search_authors'),
    
    # API Endpoints

    # Authors API urls
    path('api/authors/', AuthorListView.as_view(), name='get_authors'),
    
    # Single Author API
    path('api/authors/<uuid:author_serial>/', views.author_serial, name='author_serial'), # Retrieve or Update AUTHOR_SERIAL's profile


    # Followers API
    path('api/authors/<uuid:author_serial>/followers/', views.followersAPI, name="followersAPI"), # get a list of authors who are AUTHOR_SERIAL's followers
    path('api/authors/<uuid:author_serial>/followers/<path:foreign_author_fqid>/', views.specific_follower_details, name='specific_follower_details'), # get details of a specific follower


    # Inbox API
    path('api/authors/<uuid:author_serial>/inbox/', views.send_inbox, name='send_inbox'), # POST comment, like, post or follow to AUTHOR_SERIAL inbox
    path('api/authors/<uuid:author_serial>/inbox', views.send_inbox, name='send_inbox'), # POST comment, like, post or follow to AUTHOR_SERIAL inbox


    # Posts API
    path('api/authors/<uuid:author_serial>/posts/<uuid:post_serial>/', PostDetailView.as_view(), name='author-post-detail'), # post whose serial is POST_SERIAL
    path('api/authors/<uuid:author_serial>/posts/', views.recent_author_post, name='recent_author_post'), # Recent posts from author AUTHOR_SERIAL (paginated)
    
    # Image Posts
    path('api/authors/<uuid:author_serial>/posts/<uuid:post_serial>/image/', views.public_post_image_serial, name='public_post_image_serial'), # get the public post converted to binary as an image
    
    # Comments API
    path('api/authors/<uuid:author_serial>/posts/<uuid:post_serial>/comments', views.comments_on_post, name='comments_on_post'), # GET the comments on the post
    path('api/posts/<path:post_fqid>/comments', views.comments_on_post_fqid, name='comments_on_post_fqid'), # GET the comments on the post (that our server knows about)
    path('api/authors/<uuid:author_serial>/post/<uuid:post_serial>/comment/<path:remote_comment_fqid>', views.get_comment, name='get_comment'), # GET [local, remote] get the comment
    
    # Commented API
    path('api/authors/<uuid:author_serial>/commented', views.comment_author_post_serial, name='comment_author_post_serial'), # get the list of comments author has made on: [local] any post, [remote] public and unlisted posts, paginated
    path('api/authors/<path:author_fqid>/commented', views.comment_author_post_fqid, name='comment_author_post_fqid'), # GET [local] get the list of comments author has made on any post (that local node knows about)GET [local] get the list of comments author has made on any post (that local node knows about)
    path('api/authors/<uuid:author_serial>/commented/<uuid:comment_serial>', views.specific_author_comments, name='specific_post_comments'), # GET [local, remote] get this comment
    path('api/commented/<path:comment_fqid>', views.specific_author_comment, name='specific_author_comment'), # GET [local] get this comment
    
    # Done
    path('api/authors/<uuid:author_serial>/posts/<uuid:post_serial>/likes', views.who_liked_this_post_serial, name='who_liked_this_post_serial'), # GET [local, remote] a list of likes from other authors on AUTHOR_SERIAL's post POST_SERIAL
    path('api/posts/<path:post_fqid>/likes', views.who_liked_this_post_fqid, name='who_liked_this_post_fqid'), # GET [local] a list of likes from other authors on AUTHOR_SERIAL's post POST_SERIAL
    path('api/authors/<uuid:author_serial>/posts/<uuid:post_serial>/comments/<path:comment_fqid>/likes', views.who_liked_this_comment, name='who_liked_this_comment'), # GET [local, remote] a list of likes from other authors on AUTHOR_SERIAL's post POST_SERIAL comment COMMENT_FQID
    
    # Liked API
    path('api/authors/<uuid:author_serial>/liked', views.things_liked_by_author_serial, name='things_liked_by_author_serial'), # GET [local, remote] a list of likes by AUTHOR_SERIAL
    path('api/authors/<uuid:author_serial>/liked/<uuid:like_serial>', views.get_single_like_serial, name='get_single_like_serial'), # GET [local, remote] a single like
    path('api/authors/<path:author_fqid>/liked', views.things_liked_by_author_fqid, name='things_liked_by_author_fqid'), # GET [local] a list of likes by AUTHOR_FQID
    path('api/liked/<path:like_fqid>', views.get_single_like_fqid, name='get_single_like_fqid'), # GET [local] a single like   
    path('api/', include(router.urls)), 


    # Needs to be at bottom because path is greedy
    path('api/posts/<path:post_fqid>/image/', views.public_post_image_fqid, name='public_post_image_fqid'), # get the public post converted to binary as an image
    path('api/authors/<path:author_fqid>/', views.author_fqid, name='author_fqid'), # Retrieve AUTHOR_FQID's profile
    path('api/posts/<path:post_fqid>', views.post_fqid, name='post_fqid'), # post whose URL is POST_FQID
]   