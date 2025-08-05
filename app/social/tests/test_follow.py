from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse
from ..models import Author, FollowRequest, Follow

class FollowTest(TestCase):
    def setUp(self):
        # Create test users with unique usernames
        self.user = User.objects.create_user(username='testuser', password='testpassword123')
        self.user2 = User.objects.create_user(username='testuser2', password='testpassword123')
        self.user3 = User.objects.create_user(username='testuser3', password='testpassword123')
        
        self.author, created = Author.objects.get_or_create(user=self.user, defaults={'display_name': 'Test Author'})
        self.author2, created = Author.objects.get_or_create(user=self.user2, defaults={'display_name': 'Test Author 2'})
        self.author3, created = Author.objects.get_or_create(user=self.user3, defaults={'display_name': 'Test Author 3'})

        # Log in the user
        self.client.login(username='testuser', password='testpassword123')

    def test_follow_request(self):
        """
        Test that an authenticated user can send a follow request.
        """
        url = reverse('follow_request', kwargs={'author_serial': self.author2.id})
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)  # Follow request sent successfully

        # Verify that the follow request was created in the database
        self.assertTrue(FollowRequest.objects.filter(actor=self.author, object=self.author2).exists())

    def test_follow_request_accept(self):
        """
        Test that an authenticated user can accept a follow request, and become a follower.
        """
        # Set up follow request
        url = reverse('follow_request', kwargs={'author_serial': self.author2.id})
        response = self.client.post(url)
        follow_request = FollowRequest.objects.get(actor=self.author, object=self.author2)
        follow_request_id = follow_request.id

        # Accept the follow request using the retrieved ID
        url = reverse('accept_follow_request', kwargs={'request_id': follow_request_id})
        response = self.client.post(url)

        # Check the response status code
        self.assertEqual(response.status_code, 302)  # Redirect after successful acceptance

        # Verify that the follow request was accepted and the follow relationship was created
        self.assertFalse(FollowRequest.objects.filter(actor=self.author, object=self.author2).exists())
        self.assertTrue(Follow.objects.filter(user=self.author, following=self.author2).exists())

    def test_follow_request_decline(self):
        """
        Test that an authenticated user can decline a follow request, and they won't become a follower.
        """
        # Set up follow request
        url = reverse('follow_request', kwargs={'author_serial': self.author2.id})
        response = self.client.post(url)
        follow_request = FollowRequest.objects.get(actor=self.author, object=self.author2)
        follow_request_id = follow_request.id

        # Decline the follow request using the retrieved ID
        url = reverse('deny_follow_request', kwargs={'request_id': follow_request_id})
        response = self.client.post(url)

        # Check the response status code
        #self.assertEqual(response.status_code, 302)  # Redirect after successful decline

        # Verify that the follow request was declined and the follow relationship was not created
        self.assertFalse(FollowRequest.objects.filter(actor=self.author, object=self.author2).exists())
        self.assertFalse(Follow.objects.filter(user=self.author, following=self.author2).exists())

    def test_follow_request_duplicate(self):
        """
        Test that an authenticated user can send a follow request only once.
        """
        url = reverse('follow_request', kwargs={'author_serial': self.author2.id})
        self.client.post(url)
        self.client.post(url)
        self.client.post(url)
        self.client.post(url)

        # Verify that only one follow request was created in the database
        self.assertEqual(FollowRequest.objects.filter(actor=self.author, object=self.author2).count(), 1)