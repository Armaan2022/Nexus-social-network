from django.urls import reverse
from rest_framework.test import APITestCase
from django.contrib.auth.models import User
from ..models import Author, FollowRequest, Follow, Post

# Test to see that an authenticated user can access the stream.

class DashboardTests(APITestCase):
    def setUp(self):
        # Create a test user
        # Create a test users
        self.user = User.objects.create_user(username='testuser', password='testpassword123')
        self.user2 = User.objects.create_user(username='testuser2', password='testpassword123')

        self.author, created = Author.objects.get_or_create(user=self.user, defaults={'display_name': 'Test Author'})
        self.author2, created = Author.objects.get_or_create(user=self.user2, defaults={'display_name': 'Test Author'})
        
        # Create or get the author for the test user

        # Log in the user
        self.client.login(username='testuser', password='testpassword123')

        self.publid_post = Post.objects.create(author=self.author, title='Test Public Post', content='This is a test post.', contentType='text/plain', visibility='PUBLIC')
        self.private_post = Post.objects.create(author=self.author, title='Test Friends Only Post', content='This is a test post.', contentType='text/plain', visibility='FRIENDS')
        self.private_post = Post.objects.create(author=self.author, title='Test Unlisted Post', content='This is a test post.', contentType='text/plain', visibility='UNLISTED')
        self.private_post = Post.objects.create(author=self.author, title='Test Deleted Post', content='This is a test post.', contentType='text/plain', visibility='DELETED')
        
    
    def test_dashboard_authenticated(self):
        # Access the dashboard as an authenticated user
        response = self.client.get(reverse('stream'))
        self.assertEqual(response.status_code, 200)

    def test_dashboard_unauthenticated(self):
        # Log out the user
        self.client.logout()

        # Access the dashboard as an unauthenticated user
        response = self.client.get(reverse('stream'))
        self.assertEqual(response.status_code, 302)  # Redirect to login
        self.assertIn('/accounts/login/', response.url)  # Verify redirect URL






    def test_view_public_posts(self):
        """
        Viewing only public posts, not following any authors.
        """

        response = self.client.get(reverse('stream'))
        self.assertEqual(response.status_code, 200)

        self.assertContains(response, 'Test Public Post')
        self.assertNotContains(response, 'Test Friends Only Post')
        self.assertNotContains(response, 'Test Unlisted Post')
        self.assertNotContains(response, 'Test Deleted Post')

    
    def test_view_following_posts(self):
        """
        Posts from authors that the user is following should be displayed.
        Unlisted, and public posts should be displayed.
        """


        # User follows author 2, becuase they have an unlisted post that should become visible.
        url = reverse('follow_request', kwargs={'author_serial': self.author2.id})
        response = self.client.post(url)
        follow_request = FollowRequest.objects.get(actor=self.author, object=self.author2)
        follow_request_id = follow_request.id
        url = reverse('accept_follow_request', kwargs={'request_id': follow_request_id})
        response = self.client.post(url)


        response = self.client.get(reverse('stream'))
        self.assertEqual(response.status_code, 200)

        self.assertContains(response, 'Test Public Post')
        self.assertNotContains(response, 'Test Unlisted Post')

        self.assertNotContains(response, 'Test Friends Only Post')
        self.assertNotContains(response, 'Test Deleted Post')

# TODO: Make them pass
    # def test_view_friends_posts(self):
    #     """
    #     Posts from authors that the user is following should be displayed.
    #     Unlisted, Friends Only, and public posts should be displayed.
    #     """


    #     # User follows author 2, because they have an unlisted post that should become visible.
    #     url = reverse('follow_request', kwargs={'author_serial': self.author2.id})
    #     response = self.client.post(url)
    #     follow_request = FollowRequest.objects.get(actor=self.author, object=self.author2)
    #     follow_request_id = follow_request.id
    #     url = reverse('accept_follow_request', kwargs={'request_id': follow_request_id})
    #     response = self.client.post(url)

    #     # Accept follow request from other user
    #     self.client.logout()
    #     self.client.login(username='testuser2', password='testpassword123')

    #     url = reverse('follow_request', kwargs={'author_serial': self.author.id})
    #     response = self.client.post(url)
    #     follow_request = FollowRequest.objects.get(actor=self.author2, object=self.author)
    #     follow_request_id = follow_request.id
    #     url = reverse('accept_follow_request', kwargs={'request_id': follow_request_id})
    #     response = self.client.post(url)

    #     # Go back to original user for tests
    #     self.client.logout()
    #     self.client.login(username='testuser', password='testpassword123')

    #     response = self.client.get(reverse('stream'))
    #     self.assertEqual(response.status_code, 200)

    #     self.assertContains(response, 'Test Public Post')
    #     self.assertContains(response, 'Test Unlisted Post')
    #     self.assertContains(response, 'Test Friends Only Post')
        
    #     self.assertNotContains(response, 'Test Deleted Post')
