from rest_framework import serializers
from .models import Author, Post, FollowRequest, Comment, Like
from markdown import markdown
from django.conf import settings
from rest_framework.pagination import PageNumberPagination
from django.contrib.contenttypes.models import ContentType
import os
from django.core.files import File
from django.utils.html import strip_tags
from django.shortcuts import get_object_or_404
import logging
from django.contrib import messages
import base64
from django.conf import settings
from django.utils.html import strip_tags
from django.conf import settings

logger = logging.getLogger(__name__)

def get_default_profile_image():
    """Return the path to the default profile image"""
    return 'static/images/default-profile.png'

# Got this from Chat GPT
def clean_url(url):
    """Remove duplicate media prefixes from URLs"""
    if not url:
        return url
    
    # Handle any domain's media prefix
    if '/media/' in url:
        # Find all occurrences of "http(s)://domain/media/"
        import re
        matches = re.findall(r'https?://[^/]+/media/', url)
        
        # If we find multiple media prefixes
        if len(matches) > 1:
            # Keep only the first occurrence of domain/media/
            first_prefix_end = url.find('/media/') + len('/media/')
            media_content = url[first_prefix_end:]
            
            # Remove any additional domain/media/ prefixes
            media_content = re.sub(r'https?://[^/]+/media/', '', media_content)
            
            # Reconstruct the URL with just one prefix
            url = url[:first_prefix_end] + media_content
    
    return url

class ReadWriteSerializerField(serializers.Field):
    """Custom field that handles both read and write operations with different serializers"""
    
    def __init__(self, write_serializer=None, **kwargs):
        self.write_serializer = write_serializer
        kwargs['read_only'] = False
        kwargs['write_only'] = False
        super().__init__(**kwargs)
    
    def get_attribute(self, instance):
        # Return the instance itself so we can access it in to_representation
        return instance
    
    def to_representation(self, obj):
        """Use the parent serializer's get_fieldname method"""
        serializer = self.parent
        method_name = f"get_{self.field_name}"
        logger.debug(f"Attempting to call method: {method_name}")
        
        if hasattr(serializer, method_name):
            method = getattr(serializer, method_name)
            return method(obj)
        logger.debug(f"Method {method_name} not found on serializer {serializer}")
        return None
    
    def to_internal_value(self, data):
        """Used for POST/PUT requests - writing data"""
        # Different handling based on what was passed as write_serializer
        if self.write_serializer:
            # Case 1: It's a serializer class (not instantiated)
            if isinstance(self.write_serializer, type) and issubclass(self.write_serializer, serializers.BaseSerializer):
                try:
                    serializer = self.write_serializer(data=data, context=self.context)
                    if hasattr(serializer, 'is_valid') and callable(serializer.is_valid):
                        serializer.is_valid(raise_exception=False)
                        if not serializer.errors:
                            return serializer.validated_data
                except Exception as e:
                    # If there's any error in serializer validation, just pass through the data
                    pass
            
            # Case 2: It's already a serializer instance
            elif hasattr(self.write_serializer, 'is_valid') and callable(self.write_serializer.is_valid):
                try:
                    self.write_serializer.initial_data = data
                    self.write_serializer.is_valid(raise_exception=False)
                    if not self.write_serializer.errors:
                        return self.write_serializer.validated_data
                except Exception as e:
                    pass
                
            # Case 3: It's a field instance (like ListField)
            elif hasattr(self.write_serializer, 'run_validation') and callable(self.write_serializer.run_validation):
                try:
                    return self.write_serializer.run_validation(data)
                except Exception as e:
                    pass
        
        # Default: If validation fails or not applicable, just pass through the data
        return data


class SrcPagination(PageNumberPagination):
    page_size = 10 
    page_size_query_param = 'size'
    max_page_size = 50


class AuthorSerializer(serializers.ModelSerializer):
    type = serializers.SerializerMethodField()
    id = serializers.CharField(source='fqid')
    page = serializers.CharField(source='profile_url') 
    displayName = serializers.CharField(source='display_name')
    profileImage = serializers.ImageField(source='profile_image')
    class Meta:
        model = Author
        fields = ['type', 'id', 'host', 'displayName', 'github', 'profileImage', 'page']
        
    def get_type(self, obj):
        return "author"
   
    def get_id(self, obj):
        request = self.context.get('request')
        return request.build_absolute_uri(f'/authors/{obj.id}')

      
class PostSerializer(serializers.ModelSerializer):
    content = serializers.SerializerMethodField()
    shareable_link = serializers.SerializerMethodField()
    
    def get_shareable_link(self, obj):
        return obj.get_shareable_link()
    class Meta:
        model = Post
        fields = '__all__'
        
    def get_content(self, obj):
        content_type = obj.contentType
        content = obj.content

        if content_type == 'text/markdown':
            # Convert Markdown to HTML
            return markdown(content)
        elif content_type in ['image/png;base64', 'image/jpeg;base64', 'application/base64']:
            # Decode base64 image and return as a data URL
            return f"data:{content_type};base64,{content}"
        else:
            # Plain text or other types
            return content



# Serializers Below for API endpoints

class SingleAuthorSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='fqid', required=False, allow_null=True)
    type = serializers.SerializerMethodField()
    page = serializers.CharField(source='profile_url') 
    profileImage = ReadWriteSerializerField(write_serializer=serializers.CharField(source='profile_image_url', required=False, allow_null=True) )
    displayName = serializers.CharField(source='display_name')
    
    profileImageInput = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = Author
        fields = [  
                'type', 
                'id', 
                'host', 
                'displayName', 
                'github', 
                'profileImage', 
                'profileImageInput', 
                'page'
            ]

    def get_type(self, obj):
        return "author"
    

    def get_profileImage(self, obj):
        logger.info(f"\n\nSingleAuthorSerializer get_profileImage called\n\n")
        if obj.profile_image_url:
            return obj.profile_image_url
        return get_default_profile_image()

    def update(self, instance, validated_data):

        logger.info(f"\n\nSingleAuthor Update Started\n\n")
        profile_image_input = validated_data.pop('profileImageInput', None)
        if profile_image_input:
            logger.info(f"\nProfile image input: {profile_image_input}\n")

            if profile_image_input.startswith('http://') or profile_image_input.startswith('https://'):
                # Directly set the absolute URL as the profile image
                instance.profile_image = profile_image_input
                instance.profile_image_url = profile_image_input  # Store the absolute URL
            else:
                request = self.context.get('request')
                current_host = request.build_absolute_uri('/')[:-1]
                local_media_url = f"{current_host}{settings.MEDIA_URL}"
                if profile_image_input.startswith(settings.MEDIA_URL) or profile_image_input.startswith(local_media_url):
                    file_path = os.path.join(settings.MEDIA_ROOT, profile_image_input.replace(local_media_url, '').replace(settings.MEDIA_URL, ''))
                    if os.path.exists(file_path):
                        with open(file_path, 'rb') as f:
                            file_name = os.path.basename(file_path)
                            instance.profile_image.save(file_name, File(f), save=False)
                        # Set the absolute URL for the profile_image_url field
                        instance.profile_image_url = f"{current_host}{settings.MEDIA_URL}{file_name}"
                    else:
                        raise serializers.ValidationError(f"Image file does not exist at {file_path}.")
                else:
                    raise serializers.ValidationError(f"Profile image must be a URL to an existing file in the media directory (e.g., '{local_media_url}images/...').")

        # Update other fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance

    def create(self, validated_data):
        request = self.context.get('request')
        logger.error(f"\n\nUnvalidated author data: {request}\n\n")
        logger.error(f"\n\nvalid author validated_data: {validated_data}\n\n")

        # Fetch the existing author or create a new one
        author, created = Author.objects.get_or_create(
            fqid=validated_data.get('fqid'),
        )

        # Update fields explicitly
        author.display_name = validated_data.get('display_name')
        profile_image = validated_data.get('profileImage')

        if profile_image is not None:
            author.profile_image_url = profile_image
        else:
            author.profile_image_url = ""
            
        author.host = validated_data.get('host')
        author.github = validated_data.get('github')
        author.profile_url = validated_data.get('profile_url')
        author.save()

        return author


class SingleLikeSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='fqid')
    object = serializers.SerializerMethodField()
    type = serializers.SerializerMethodField()
    author = SingleAuthorSerializer()
    object_id = serializers.UUIDField(write_only=True, required=False)
    content_type = serializers.CharField(write_only=True, required=False)
    published = serializers.DateTimeField()

    class Meta:
        model = Like
        fields = [
            'type',  # -> 'like'
            'author',  # Good
            'published',  # Good
            'id',  # -> fqid
            'object',  # -> post.fqid
            'object_id',  # Add this line
            'content_type',  # Add this line
        ]

    def get_type(self, obj):
        return "like"

    def get_object(self, obj):
        # Get the content type and looked up the related model
        content_type = ContentType.objects.get_for_id(obj.content_type_id)
        # Get the actual object instance (Post or Comment)
        liked_object = content_type.get_object_for_this_type(id=obj.object_id)
        # Return the fqid of that object
        return liked_object.fqid
    

    def is_valid(self, raise_exception=False, skip_validation=False):
        """Override is_valid to allow skipping validation when needed"""
        if skip_validation:
            self._validated_data = self.initial_data
            self._errors = {}
            return True
        return super().is_valid(raise_exception=raise_exception)

    def create(self, validated_data):

        #if validated_data["type"] ==

        #logger.info(f"\n\nSingleLikeSerializer create called with validated_data: {validated_data}\n\n")

        author_data = validated_data.pop('author')

        logger.info(f"\n\nSingleLikeSerializer create called with validated_data author_data: {author_data}\n\n")

        fqid = author_data.get('fqid') or author_data.get('id')
        display_name = author_data.get('display_name') or author_data.get('displayName')
        profile_image = author_data.get('profileImage') or author_data.get('profile_image_url')
        profile_url = author_data.get('profile_url') or author_data.get('page')

        author, created = Author.objects.update_or_create(
            fqid=fqid,  # JSON uses 'id' for fqid
            defaults={
                'display_name': display_name,  # JSON uses 'displayName'
                'profile_image_url': clean_url(profile_image),  # JSON uses 'profileImage'
                'host': author_data.get('host'),
                'github': author_data.get('github'),
                'profile_url': profile_url  # JSON uses 'page'
            }
        )

        if created:

            logger.info(f"\n\nSingleLikeSerializer CREATED NEW AUTHOR author data: {author.get_details_dict()}\n\n")
        


        content_type_value = validated_data.get('content_type')
        content_type = ContentType.objects.get(model=content_type_value)

        like, created = Like.objects.update_or_create(
            fqid=validated_data.get('fqid'),
            defaults={
                'author': author,
                'published': validated_data.get('published'),
                'content_type': content_type,
                'object_id': validated_data.get('object_id')
            }
        )

        return like


    
class SingleFollowRequestSerializer(serializers.ModelSerializer):

    type = serializers.SerializerMethodField()
    summary = serializers.SerializerMethodField()
    actor = SingleAuthorSerializer()
    object = SingleAuthorSerializer()

    class Meta:
        model = FollowRequest
        
        fields = [ 
            'type',
            'summary',   
            'actor', 
            'object',
        ]

    def get_type(self, obj):
        return "follow"
    
    def get_object(self, obj):
        return "actor wants to follow object"
    
    def create(self, validated_data):

        logger.error(f"\n\nvalidated_data follow request data: {validated_data}\n\n")

        actor_author_data = validated_data.pop('actor')
        actor_author, created = Author.objects.update_or_create(
            fqid=actor_author_data.get('fqid'),  # JSON uses 'id' for fqid
            defaults={
                'display_name': actor_author_data.get('display_name'),  # JSON uses 'displayName'
                'profile_image_url': clean_url(actor_author_data.get('profileImage')),  # JSON uses 'profileImage'
                'host': actor_author_data.get('host'),
                'github': actor_author_data.get('github'),
                'profile_url': actor_author_data.get('page')  # JSON uses 'page'
            }
        )

        
        

        object_author_data = validated_data.pop('object')
        object_author, created = Author.objects.update_or_create(
            fqid=object_author_data.get('fqid'),  # JSON uses 'id' for fqid
            defaults={
                'display_name': object_author_data.get('display_name'),  # JSON uses 'displayName'
                'profile_image_url': clean_url(object_author_data.get('profileImage')),  # JSON uses 'profileImage'
                'host': object_author_data.get('host'),
                'github': object_author_data.get('github'),
                'profile_url': object_author_data.get('page')  # JSON uses 'page'
            }
        )

        follow_request, created = FollowRequest.objects.update_or_create(
            actor=actor_author,
            object=object_author
        )

        return follow_request



# Multi Serializers
class MultiLikeSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='fqid')
    type = serializers.SerializerMethodField()
    page = serializers.CharField(source='fqid')
    page_number = serializers.SerializerMethodField(read_only=True)
    size = serializers.SerializerMethodField(read_only=True)
    count = serializers.SerializerMethodField(read_only=True)
    src = ReadWriteSerializerField(write_serializer=serializers.ListField(child=SingleLikeSerializer()))


    class Meta:
        model = Like
        fields = [
            'type',
            'page',
            'id',
            'page_number',
            'size',
            'count',
            'src'
        ]

    def get_type(self, obj):
        return "likes"

    def get_page_number(self, obj):
        request = self.context.get('request')
        paginator = SrcPagination()
        likes = Like.objects.filter(object_id=obj.id, content_type=ContentType.objects.get_for_model(obj))
        page = paginator.paginate_queryset(likes, request)
        return paginator.page.number if page is not None else 1

    def get_size(self, obj):
        request = self.context.get('request')
        paginator = SrcPagination()
        return paginator.get_page_size(request)

    def get_count(self, obj):
        likes = Like.objects.filter(object_id=obj.id, content_type=ContentType.objects.get_for_model(obj))
        return likes.count()

    def get_src(self, obj):
        request = self.context.get('request')
        paginator = SrcPagination()
        likes = Like.objects.filter(object_id=obj.id, content_type=ContentType.objects.get_for_model(obj))
        page = paginator.paginate_queryset(likes, request)
        serializer = SingleLikeSerializer(page, many=True)
        return serializer.data
    
    def is_valid(self, raise_exception=False, skip_validation=False):
        """Override is_valid to allow skipping validation when needed"""
        if skip_validation:
            self._validated_data = self.initial_data
            self._errors = {}
            return True
        return super().is_valid(raise_exception=raise_exception)

    def create(self, validated_data):
        likes_data = validated_data.pop('src', [])
        likes = []

        # Assuming the object (Post or Comment) is passed in the context
        parent_object = self.context.get('parent_object')
        object_id = parent_object.id
        content_type = parent_object._meta.model_name

        for like_data in likes_data:

            like_data['object_id'] = object_id
            like_data['content_type'] = content_type

            like_serializer = SingleLikeSerializer(data=like_data, context=self.context)
            if like_serializer.is_valid(skip_validation=True):
                like = like_serializer.save()
                likes.append(like)
            else:
                logger.error("Invalid SingleLikeSerializer data", like_serializer.errors)

        return likes
        
    


class SingleCommentSerializer(serializers.ModelSerializer):
    """
    Serializes a list of comments, paginated.
    Includes the author, and likes for each comment.

    Note: obj must be a Post Model instance.
    Calls the MultiLikeSerializer to serialize all the comments like.
    """
    
    id = serializers.CharField(source='fqid')
    type = serializers.SerializerMethodField()
    likes = serializers.SerializerMethodField(read_only=True)
    contentType = serializers.CharField(source='content_type')
    author = SingleAuthorSerializer()
    post = ReadWriteSerializerField(write_serializer=serializers.CharField())
    #likes = MultiLikeSerializer(write_only=True)
    likes = ReadWriteSerializerField(write_serializer=serializers.ListField(child=MultiLikeSerializer()))
    
    class Meta:
        model = Comment

        fields = [ 
                'type', # -> 'comment'
                'author', # Good
                'comment', # Good
                'contentType', # Good
                'published', # Good
                'id', # -> fqid
                'post', # -> post.post_url
                'likes' # Missing, must query
            ]
    
    def get_type(self, obj):
        return "comment"

    def get_likes(self, obj):
        comment = get_object_or_404(Comment, fqid=obj.fqid)
        likes_serializer = MultiLikeSerializer(comment, context=self.context)
        return likes_serializer.data

    def get_post(self, obj):
        if isinstance(obj, Comment):
            return obj.post.fqid
        else:
            return obj.post
        
    def is_valid(self, raise_exception=False, skip_validation=False):
        """Override is_valid to allow skipping validation when needed"""
        if skip_validation:
            self._validated_data = self.initial_data
            self._errors = {}
            return True
        return super().is_valid(raise_exception=raise_exception)
        
    
    def create(self, validated_data):
        author_data = validated_data.pop('author')
        post_fqid = validated_data.get("post")
        post = get_object_or_404(Post, fqid=post_fqid)

        logger.info(f"\n\nSingleCommentSerializer create called with post fqid: {post_fqid}\n\n")
        logger.info(f"\n\nSingleCommentSerializer author data: {author_data}\n\n")
        

        author, created = Author.objects.update_or_create(
            fqid=author_data.get('fqid'),
            defaults={
                'display_name': author_data.get('display_name'),
                'profile_image_url': clean_url(author_data.get('profileImage')),
                'host': author_data.get('host'),
                'github': author_data.get('github'),
                'profile_url': author_data.get('profile_url')
            }
        )

        if created:

            logger.info(f"\n\nSingleCommentSerializer CREATED NEW AUTHOR author data: {author.get_details_dict()}\n\n")
        

        content_type_str = validated_data.get('contentType') or validated_data.get('content_type')

        comment, created = Comment.objects.update_or_create(
            fqid=validated_data.get('fqid'),  # Only use fqid for lookup
            defaults={
                'author': author,
                'comment': validated_data.get('comment'),
                'content_type': content_type_str,
                'published': validated_data.get('published'),
                'post': post
            }
        )

        likes_data = validated_data.get('likes', {})


        likes_serializer = MultiLikeSerializer(data=likes_data, context={'request': self.context['request'], 'parent_object': comment})
        if likes_serializer.is_valid(skip_validation=True):
            likes = likes_serializer.save()
            comment.likes.set(likes)
        else:
            logger.error("Invalid data SingleCommentSerializer -> MultiLikeSerializer: ",likes_serializer.errors)


        return comment

class SinglePostDeSerializer(serializers.ModelSerializer):
    pass

class SingleCommentDeSerializer(serializers.ModelSerializer):
    pass



class MultiCommentSerializer(serializers.ModelSerializer):
    """
    Serializes a list of comments, paginated.
    Includes the author, and likes for each comment.

    Note: obj must be a Post or  Model instance.
    Calls the SingleLikeSerializer to serialize all the comments like.
    """

    id = serializers.CharField(source='fqid')
    type = serializers.SerializerMethodField()
    page = serializers.CharField(source='fqid')
    page_number = serializers.SerializerMethodField(read_only=True)
    size = serializers.SerializerMethodField(read_only=True)
    count = serializers.SerializerMethodField(read_only=True)
    src = ReadWriteSerializerField(write_serializer=serializers.ListField(child=SingleCommentSerializer()))


    class Meta:
        model = Comment
        fields = [
            'type',
            'page',
            'id',
            'page_number',
            'size',
            'count',
            'src'
        ]

    def get_type(self, obj):
        return "comments"
    
    def get_page(self, obj):
        request = self.context.get('request', None)
        if request:
            return request.build_absolute_uri()
        return None

    def get_page_number(self, obj):
        request = self.context.get('request', None)
        if request:
            paginator = SrcPagination()
            if isinstance(obj, Author):
                comments = Comment.objects.filter(author=obj)
            elif isinstance(obj, Post):
                comments = Comment.objects.filter(post=obj)
            else:
                comments = Comment.objects.none()
            page = paginator.paginate_queryset(comments, request)
            return paginator.page.number if page is not None else 1
        return None

    def get_size(self, obj):
        request = self.context.get('request', None)
        if request:
            paginator = SrcPagination()
            return paginator.get_page_size(request)
        return None

    def get_count(self, obj):
        if isinstance(obj, Author):
            comments = Comment.objects.filter(author=obj)
        elif isinstance(obj, Post):
            comments = Comment.objects.filter(post=obj)
        else:
            comments = Comment.objects.none()
        return comments.count()

    def get_src(self, obj):
        request = self.context.get('request', None)
        if request:
            paginator = SrcPagination()
            if isinstance(obj, Author):
                comments = Comment.objects.filter(author=obj)
            elif isinstance(obj, Post):
                comments = Comment.objects.filter(post=obj)
            else:
                comments = Comment.objects.none()
            page = paginator.paginate_queryset(comments, request)
            serializer = SingleCommentSerializer(page, many=True, context={'request': request})
            return serializer.data
        return None
    
    def is_valid(self, raise_exception=False, skip_validation=False):
        """Override is_valid to allow skipping validation when needed"""
        if skip_validation:
            self._validated_data = self.initial_data
            self._errors = {}
            return True
        return super().is_valid(raise_exception=raise_exception)

    def create(self, validated_data):

        comments_data = validated_data.pop('src', [])
        comments = []

        for comment_data in comments_data:

            comment_serializer = SingleCommentSerializer(data=comment_data, context=self.context)
            if comment_serializer.is_valid(skip_validation=True):
                comment = comment_serializer.save()
                comments.append(comment)
            else:
                logger.error("Invalid SingleCommentSerializer data", comment_serializer.errors)

        return comments
    



class SinglePostSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='fqid')
    page = serializers.CharField(source='post_url')
    type = serializers.SerializerMethodField()

    comments = ReadWriteSerializerField(write_serializer=MultiCommentSerializer)
    likes = ReadWriteSerializerField(write_serializer=MultiLikeSerializer)

    author = SingleAuthorSerializer()

    class Meta:
        model = Post
        fields = [
            'type',  # -> 'post'
            'title',  # Good
            'id',  # -> fqid
            'page',  # -> post_url
            'description',  # Good
            'contentType',  # Good
            'content',  # Good
            'author',  # Good
            'comments',  # Missing, must query
            'likes',  # Missing, must query
            'published',  # Good
            'visibility',  # Good
        ]

    def get_type(self, obj):
        return "post"

    

    def to_representation(self, instance):
        # Get the default serialized data
        data = super().to_representation(instance)

        

        # If the content type is text/markdown, strip HTML tags from the content
        if instance.contentType == 'text/markdown':
            data['content'] = strip_tags(instance.content)
        

        # Got the rest of this function from chat GPT
        # Handle all image types
        elif instance.contentType in ['image/png;base64', 'image/jpeg;base64', 'application/base64']:

            # Only process if content appears to be a file path and not already base64
            if (instance.content.startswith('/media/') or 
                instance.content.startswith('media/') or 
                '/' in instance.content) and not instance.content.startswith('data:'):
                
                try:
                    # Get file path
                    file_path = instance.content.replace("%20", "_").replace(" ", "_")
                    if file_path.startswith('/media/'):
                        file_path = file_path[len('/media/'):]
                    elif file_path.startswith('media/'):
                        file_path = file_path[len('media/'):]
                    
                    # Construct full path
                    full_path = os.path.join(settings.MEDIA_ROOT, file_path)
                    
                    # Determine MIME type
                    if instance.contentType == 'image/png;base64':
                        mime_type = 'image/png'
                    elif instance.contentType == 'image/jpeg;base64':
                        mime_type = 'image/jpeg'
                    else:  # application/base64
                        # Try to determine from file extension
                        _, ext = os.path.splitext(full_path)
                        if ext.lower() in ['.png']:
                            mime_type = 'image/png'
                        elif ext.lower() in ['.jpg', '.jpeg']:
                            mime_type = 'image/jpeg'
                        else:
                            mime_type = 'application/octet-stream'
                    
                    # Check if file exists
                    if os.path.exists(full_path):
                        with open(full_path, 'rb') as image_file:
                            binary_data = image_file.read()
                            base64_data = base64.b64encode(binary_data).decode('utf-8')
                            #data['content'] = f"data:{mime_type};base64,{base64_data}"
                            data['content'] = f"{base64_data}"
                    else:
                        # Log that file wasn't found
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.error(f"Image file not found: {full_path}")
                
                except Exception as e:
                    # Log the error but don't break serialization
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"Error converting image to base64: {str(e)}")
                    # Keep original content if conversion fails
        
        return data

    # Queries local Comments and includes comments from the JSON input
    def get_comments(self, obj):
        request = self.context.get('request')
        post = get_object_or_404(Post, fqid=obj.fqid)
        serialized_comments = MultiCommentSerializer(post, context={'request': request}).data
        if hasattr(obj, 'comments_data'):
            serialized_comments.extend(obj.comments_data)
        return serialized_comments

    # Queries local PostLikes and includes likes from the JSON input
    def get_likes(self, obj):
        request = self.context.get('request')
        post = get_object_or_404(Post, fqid=obj.fqid)
        serialized_likes = MultiLikeSerializer(post, context={'request': request}).data
        if hasattr(obj, 'likes_data'):
            serialized_likes.extend(obj.likes_data)
        return serialized_likes



    def create(self, validated_data):

        post_data = validated_data
        author_data = validated_data.get('author')

        author, created = Author.objects.update_or_create(
            fqid=author_data.get('fqid'),
            defaults={
                'display_name': author_data.get('display_name'),
                'profile_image_url': clean_url(author_data.get('profileImage')),
                'host': author_data.get('host'),
                'github': author_data.get('github'),
                'profile_url': author_data.get('profile_url')
            }
        )

        if created:

            logger.info(f"\n\nSinglePostSerializer CREATED NEW AUTHOR author data: {author.get_details_dict()}\n\n")
        


        post, created = Post.objects.update_or_create(
            fqid=post_data.get('fqid'),
            defaults={
                'author': author,
                'title': post_data.get('title'),
                'post_url': post_data.get('page'),
                'description': post_data.get('description'),
                'content': post_data.get('content'),
                'contentType': post_data.get('contentType'),
                'published': post_data.get('published'),
                'visibility':post_data.get('visibility')
            }
        )

        comments_raw_data = validated_data.get('comments', {})
        likes_raw_data = validated_data.get('likes', {})

        comments = MultiCommentSerializer(data=comments_raw_data, context={'request': self.context['request']})
        if comments.is_valid(skip_validation=True):
            comments = comments.save()

        likes = MultiLikeSerializer(data=likes_raw_data, context={'request': self.context['request'], 'parent_object': post})
        if likes.is_valid(skip_validation=True):
            likes = likes.save()
            post.likes.set(likes)

        post.save()

        return post
    
