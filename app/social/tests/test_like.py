from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from ..models import Author, Like, Post, Comment
import uuid

class LikesTests(TestCase):
    def setUp(self):
        # Create a test user
        self.user = User.objects.create_user(username='testuser', password='testpassword123')

        self.author, created = Author.objects.get_or_create(user=self.user, defaults={'display_name': 'Test Author'})

        # Log in the user
        self.client.login(username='testuser', password='testpassword123')

        # Create a test post
        self.post = Post.objects.create(author=self.author, title='Test Post', content='This is a test post.', contentType='text/plain', visibility='PUBLIC')


    def test_like_post(self):
        """
        Test that an authenticated user can like a post.
        """
        url = reverse('like_item', kwargs={'post_id': self.post.id})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)  # Redirect after successful creation
        self.assertEqual(response.url, reverse('stream'))  # Redirect to stream page

        # Check the response status code
        self.assertEqual(response.status_code, 302)  # Redirect after successful like

        # Verify that the like was created in the database
        self.assertTrue(Like.objects.filter(object_id=self.post.id, author=self.author).exists())

    def test_like_comment(self):
        """
        Test that an authenticated user can like a comment.
        TODO: Implement this test case.
        """
        pass
        #url = reverse('like_comment', kwargs={'comment_id': self.comment.comment_uuid})
        #response = self.client.post(url)
        #self.assertEqual(response.status_code, 302)  # Redirect after successful creation
        #self.assertEqual(response.url, reverse('stream'))  # Redirect to stream page

        # Check the response status code
        #self.assertEqual(response.status_code, 302)  # Redirect after successful like

        # Verify that the like was created in the database
        #self.assertTrue(Like.objects.filter(post=self.post, author=self.author).exists())

    def test_like_post_unauthenticated(self):
        """
        Test that an unauthenticated user cannot like a post.
        """
        self.client.logout()  # Log out the user

        url = reverse('like_item', kwargs={'post_id': self.post.id})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)  # Redirect to login page

        # Verify that the like was not created in the database
        self.assertFalse(Like.objects.filter(object_id=self.post.id, author=self.author).exists())

    def test_like_comment_unauthenticated(self):
        """
        Test that an unauthenticated user cannot like a comment.
        TODO: Implement this test case.
        """
        pass
        #self.client.logout()  # Log out the user

        #url = reverse('like_comment', kwargs={'comment_id': self.comment.comment_uuid})
        #response = self.client.post(url)
        #self.assertEqual(response.status_code, 302)  # Redirect to login page

        # Verify that the like was not created in the database
        #self.assertFalse(Like.objects.filter(post=self.post, author=self.author).exists())

    def test_duplicate_post_likes(self):
        """
        Test that an authenticated user can like a post only once.
        """
        url = reverse('like_item', kwargs={'post_id': self.post.id})
        response = self.client.post(url)
        response = self.client.post(url)
        response = self.client.post(url)
        response = self.client.post(url)
        
        # Check the response status code
        self.assertEqual(response.status_code, 302)  # Redirect after successful like

        # Verify that only one like was created in the database
        self.assertEqual(Like.objects.filter(object_id=self.post.id, author=self.author).count(), 1)