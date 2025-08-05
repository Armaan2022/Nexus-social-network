from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse
from ..models import Author

class ViewProfileTests(TestCase):
    def setUp(self):
        # Create a test user
        self.user = User.objects.create_user(username='testuser', password='testpassword123')
        
        # Create or get the author for the test user
        self.author, created = Author.objects.get_or_create(
            user=self.user,
            defaults={
                'display_name': 'Test Author',
                'title': 'Software Developer',
                'description': 'This is a test profile.',
            }
        )
        
        # Log in the user
        self.client.login(username='testuser', password='testpassword123')

# TODO : Make them pass
    # def test_view_profile_authenticated(self):
    #     """
    #     Test that an authenticated user can view their profile.
    #     """
    #     url = reverse('view_profile')
    #     response = self.client.get(url)

    #     # Check the response status code
    #     self.assertEqual(response.status_code, 200)

    #     # Check that the profile details are displayed in the response content
    #     self.assertContains(response, 'Test Author')
    #     self.assertContains(response, 'Software Developer')
    #     self.assertContains(response, 'This is a test profile.')


# TODO: Make them pass
    # def test_update_profile_authenticated(self):
    #     """
    #     Test that an authenticated user can update their profile.
    #     """
    #     url = reverse('view_profile')
    #     data = {
    #         'display_name': 'Updated Author',
    #         'title': 'Senior Developer',
    #         'description': 'This is an updated profile.',
    #     }

    #     response = self.client.post(url, data, format='multipart')

    #     # Verify that the profile was updated in the database
    #     updated_author = Author.objects.get(user=self.user)
    #     self.author.refresh_from_db()
    #     self.assertEqual(self.author.display_name, 'Updated Author')
    #     self.assertEqual(self.author.title, 'Senior Developer')
    #     self.assertEqual(self.author.description, 'This is an updated profile.')

    def test_view_profile_unauthenticated(self):
        """
        Test that an unauthenticated user is redirected to the login page.
        """
        self.client.logout()  # Log out the user

        url = reverse('view_profile')
        response = self.client.get(url)

        # Check the response status code (302 for redirect)
        self.assertEqual(response.status_code, 302)

        # Verify that the user is redirected to the login page
        self.assertIn('/accounts/login/', response.url)
