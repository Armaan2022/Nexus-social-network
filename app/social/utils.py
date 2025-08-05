from django.contrib.contenttypes.models import ContentType
from .models import InboxItem, Follow, Post, Comment, Author, Node
from .serializers import SinglePostSerializer, SingleLikeSerializer, SingleCommentSerializer, SingleFollowRequestSerializer
from rest_framework import authentication, exceptions
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone
from rest_framework import authentication
from rest_framework.authentication import get_authorization_header
import base64
import binascii
from django.contrib.auth.models import User
import logging
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
import logging
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404


logger = logging.getLogger(__name__)




class Inbox:
    def __init__(self, author):
        self.author = author

    def add_to_inbox(self, recipient, sender, instance):
        instance.save()  # Ensure the instance is saved before adding to the inbox
        InboxItem.objects.create(
            recipient=recipient,
            sender=sender,
            content_type=ContentType.objects.get_for_model(instance),
            object_id=instance.id
        )

    def add_post_to_followers_inbox(self, post):
        followers = Follow.objects.filter(following=post.author)
        for follower in followers:
            self.add_to_inbox(follower.user, post.author, post)

    def add_like_to_inbox(self, like):
        self.add_to_inbox(like.content_object.author, like.author, like)

    def add_comment_to_inbox(self, comment):
        self.add_to_inbox(comment.post.author, comment.author, comment)

    def add_follow_request_to_inbox(self, follow_request):
        self.add_to_inbox(follow_request.object, follow_request.actor, follow_request)



def get_object_by_fqid(fqid):
    """
    Find either a Post or Comment by fqid.
    Returns a tuple (object, content_type) or (None, None) if not found.
    """
    # Try to find as a Post first
    try:
        post = Post.objects.get(fqid=fqid)
        return post, ContentType.objects.get_for_model(Post)
    except Post.DoesNotExist:
        pass
    
    # If not a Post, try as a Comment
    try:
        comment = Comment.objects.get(fqid=fqid)
        return comment, ContentType.objects.get_for_model(Comment)
    except Comment.DoesNotExist:
        return None, None
    



def send_post_to_remote_followers(request, post, author):
    nodes = Node.objects.filter(is_active=True)

    logger.info(f"called send_post_to_remote_followers")

    followers = Follow.objects.filter(following=author)

    for node in nodes:
        for follower in followers:

            logger.info(f"sending Post to node {node.host}")

            logger.info(f"follower user host: {follower.user.host}")
            logger.info(f"node host: {node.host}")
            if str(follower.user.host) == str(node.host):

                logger.info(f"Matching node found: {node.host}")
                
                auth = (node.username, node.password)

                if str(follower.user.host) == str(node.host):
                    try:
                        node_host = node.host.rstrip('/')  # Remove trailing slash if present

                        logger.info(f"sending Post to node 1{node_host}")
                        drf_request = Request(request)
                        logger.info(f"drf_request {drf_request}")
                        serializer = SinglePostSerializer(post, context={'request': drf_request})
                        logger.info(f"past post serializer")
                        post_data = serializer.data.copy()

                        logger.info(f"past post serializer 1")


                        author_serial = follower.user.fqid.rstrip('/')
                        author_serial = author_serial.split('/')[-1]

                        logger.info(f"Sending post to: {f"{node_host}/authors/{author_serial}/inbox"} \nPost data: {post_data}")


                        
                        # Send POST request to the node's inbox
                        #if node.team_name == "bisque":

                            # Send POST request to the node's inbox
                            #response = requests.post(
                                #f"{node_host}/authors/{author_serial}/inbox",
                                #json=post_data,
                                ##auth=auth,
                                #timeout=10,
                                #verify=False
                            #)
                        #else:
                        
                        # Send POST request to the node's inbox
                        response = requests.post(
                            f"{node_host}/authors/{author_serial}/inbox",
                            json=post_data,
                            auth=auth,
                            timeout=10,
                            verify=False
                        )


                        messages.success(request, "Post sent!")

                    except requests.exceptions.RequestException as e:
                        logger.error(f"Error sending Post to {node.host}: {e}")
                        messages.error(request, f"Error sending Post to {node.host}")

    return redirect('stream')  # Redirect to the stream page after creating the post





def send_like_to_remote_nodes(request, author, like):
    logger.info(f"sending Like to host {author.host}")

    nodes = Node.objects.filter(is_active=True)

    for node in nodes:
        
        if author.host == node.host:

            auth = (node.username, node.password)

            try:
                node_host = node.host.rstrip('/')  # Remove trailing slash if present

                logger.info(f"sending Like to node {node_host}")
                drf_request = Request(request)
                serializer = SingleLikeSerializer(like, context={'request': drf_request})
                like = serializer.data
                
                author_serial = author.fqid.rstrip('/')
                author_serial = author_serial.split('/')[-1]

                logger.info(f"Sending like to: {f"{node_host}/authors/{author_serial}/inbox"} \nLike data: {like}")
                

                
                # Send POST request to the node's inbox
                response = requests.post(
                    f"{node_host}/authors/{author_serial}/inbox",
                    json=like,
                    auth=auth,
                    timeout=10,
                    verify=False
                )

                messages.success(request, "Like sent!")

            except requests.exceptions.RequestException as e:
                logger.error(f"Error sending Like to {node.host}: {e}")
                messages.error(request, f"Error sending Like to {node.host}")
                    
    return redirect('stream')  # Redirect to the stream page after creating the post




def send_comment_to_remote_nodes(request, post_author, comment):
    logger.info(f"sending Comment to host {post_author.host}")

    nodes = Node.objects.filter(is_active=True)

    for node in nodes:
        
        if post_author.host == node.host:

            auth = (node.username, node.password)

            try:
                node_host = node.host.rstrip('/')  # Remove trailing slash if present

                logger.info(f"sending Comment to node {node_host}")
                drf_request = Request(request)
                serializer = SingleCommentSerializer(comment, context={'request': drf_request})
                comment = serializer.data

                author_serial = post_author.fqid.rstrip('/')
                author_serial = author_serial.split('/')[-1]

                logger.info(f"Sending Comment to: {f"{node_host}/authors/{author_serial}/inbox"} \nComment data: {comment}")
                
                # Send POST request to the node's inbox
                #if node.team_name == "bisque":

                    # Send POST request to the node's inbox
                    #response = requests.post(
                        #f"{node_host}/authors/{author_serial}/inbox",
                        #json=comment,
                        #auth=auth,
                        #timeout=10,
                        #verify=False
                    #)
                #else:
                
                # Send POST request to the node's inbox
                response = requests.post(
                    f"{node_host}/authors/{author_serial}/inbox",
                    json=comment,
                    auth=auth,
                    timeout=10,
                    verify=False
                )

                messages.success(request, "Comment sent!")

            except requests.exceptions.RequestException as e:
                logger.error(f"Error sending Comment to {node.host}: {e}")
                messages.error(request, f"Error sending Comment to {node.host}")
                    
    return redirect('stream')  # Redirect to the stream page after creating the post

