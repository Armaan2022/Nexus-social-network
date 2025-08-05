from django.urls import reverse
from django.test import TestCase
from django.contrib.auth.models import User
from ..models import Author, Follow  # Replace 'your_app' with your actual app name
from uuid import uuid4

class FollowersFollowingViewTests(TestCase):
    def setUp(self):
        # Create a test user
        self.user = User.objects.create_user(username='testuser', password='testpassword123')
        
        # Get or create the Author instance for the test user
        self.author, created = Author.objects.get_or_create(
            user=self.user,
            defaults={'display_name': 'Test Author', 'id': uuid4()}
        )

        # Create another user and author to act as a follower/following
        self.other_user = User.objects.create_user(username='otheruser', password='testpassword123')
        self.other_author, created = Author.objects.get_or_create(
            user=self.other_user,
            defaults={'display_name': 'Other Author', 'id': uuid4()}
        )

        # Log in the test user
        self.client.login(username='testuser', password='testpassword123')

    def test_followers_view(self):
        """
        Test that the followers view returns the correct list of followers for an author.
        """
        # Create a Follow instance where the other author is following the test author
        Follow.objects.create(user=self.other_author, following=self.author)

        url = reverse('followers', args=[self.author.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        # Verify that the response contains the follower author
        self.assertContains(response, self.other_author.display_name)
        self.assertEqual(response.context['follower_authors'], [self.other_author])

    def test_followers_view_unauthenticated(self):
        """
        Test that an unauthenticated user cannot access the followers view.
        """
        self.client.logout()  # Log out the user
        url = reverse('followers', args=[self.author.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)  # Redirect to login page
        self.assertIn('/accounts/login/', response.url)  # Verify redirect to login page

    def test_following_view(self):
        """
        Test that the following view returns the correct list of authors the user is following.
        """
        # Create a Follow instance where the test author is following the other author
        follow = Follow.objects.create(user=self.author, following=self.other_author)

        url = reverse('following', args=[self.author.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        # Verify that the response contains the following data
        self.assertContains(response, self.other_author.display_name)
        self.assertEqual(
            response.context['following_data'],
            [{'author': self.other_author, 'follow_id': follow.id}]
        )

    def test_following_view_unauthenticated(self):
        """
        Test that an unauthenticated user cannot access the following view.
        """
        self.client.logout()  # Log out the user
        url = reverse('following', args=[self.author.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)  # Redirect to login page
        self.assertIn('/accounts/login/', response.url)  # Verify redirect to login page