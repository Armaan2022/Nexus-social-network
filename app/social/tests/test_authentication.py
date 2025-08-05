from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase
from django.contrib.auth.models import User

# LOGIN / REGISTER TESTS

class UserRegistrationTests(APITestCase):
    def test_user_registration(self):
        # URL for the registration endpoint
        url = reverse('account_signup')  # allauth's default signup URL name

        # Data for registration
        data = {
            'username': 'testuser',
            'email': 'test@example.com',
            'password1': 'testpassword123',
            'password2': 'testpassword123',
        }

        # Send a POST request to register the user
        response = self.client.post(url, data, format='multipart', follow=True)

        # Check the final response status code (200 for successful redirect)
        self.assertEqual(response.status_code, 200)

        # Verify that the user was created in the database
        self.assertTrue(User.objects.filter(username='testuser').exists())
    
class UserLoginTests(APITestCase):
    def setUp(self):
        # Create a user for testing login
        self.user = User.objects.create_user(username='testuser', password='testpassword123')

    def test_user_login(self):
        # URL for the login endpoint
        url = reverse('account_login')  # allauth's default login URL name

        # Data for login
        data = {
            'login': 'testuser',  # Use 'login' instead of 'username'
            'password': 'testpassword123',
        }

        # Send a POST request to log in the user
        response = self.client.post(url, data, format='multipart', follow=True)

        # Check the final response status code (200 for successful redirect)
        self.assertEqual(response.status_code, 200)

        # Verify that the user is logged in
        self.assertTrue('_auth_user_id' in self.client.session)  # Check session