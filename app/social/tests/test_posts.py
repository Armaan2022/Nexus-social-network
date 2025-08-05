from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from django.urls import reverse
from ..models import Post, Author

class CreatePostViewTests(TestCase):
    def setUp(self):
        # Create a test user
        self.user = User.objects.create_user(username='testuser', password='testpassword123')
        
        # Create or get the author for the test user
        self.author, created = Author.objects.get_or_create(user=self.user, defaults={'display_name': 'Test Author'})
        
        # Log in the user
        self.client.login(username='testuser', password='testpassword123')

        # Create some test posts
        self.post1 = Post.objects.create(
            title='Test Post 1',
            content='This is a test post.',
            contentType='text/plain',
            visibility='PUBLIC',
            author=self.author,
            published=timezone.now()
        )
        self.post2 = Post.objects.create(
            title='Test Post 2',
            content='This is another test post.',
            contentType='text/markdown',
            visibility='FRIENDS',
            author=self.author,
            published=timezone.now()
        )

    def test_create_text_post(self):
        """
        Test that an authenticated user can create a text post.
        """
        url = reverse('create_post')
        data = {
            'title': 'Test Text Post',
            'content': 'This is a test text post.',
            'content_type': 'text/plain',
            'visibility': 'PUBLIC',
        }

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)  # Redirect after successful creation
        self.assertEqual(response.url, reverse('stream'))  # Redirect to stream page

        # Verify that the post was created in the database
        post = Post.objects.filter(title='Test Text Post').first()
        self.assertIsNotNone(post)
        self.assertEqual(post.content, 'This is a test text post.')
        self.assertEqual(post.contentType, 'text/plain')
        self.assertEqual(post.visibility, 'PUBLIC')

    def test_create_markdown_post(self):
        """
        Test that an authenticated user can create a markdown post.
        """
        url = reverse('create_post')
        data = {
            'title': 'Test Markdown Post',
            'content': '# This is a test markdown post.',
            'content_type': 'text/markdown',
            'visibility': 'FRIENDS',
        }

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)  # Redirect after successful creation
        self.assertEqual(response.url, reverse('stream'))  # Redirect to stream page

        # Verify that the post was created in the database
        post = Post.objects.filter(title='Test Markdown Post').first()
        self.assertIsNotNone(post)
        self.assertIn('<h1>This is a test markdown post.</h1>', post.content)  # Markdown is rendered to HTML
        self.assertEqual(post.contentType, 'text/markdown')
        self.assertEqual(post.visibility, 'FRIENDS')


    def test_create_post_unauthenticated(self):
        """
        Test that an unauthenticated user cannot create a post.
        """
        self.client.logout()  # Log out the user

        url = reverse('create_post')
        data = {
            'title': 'Test Unauthenticated Post',
            'content': 'This post should not be created.',
            'content_type': 'text/plain',
            'visibility': 'PUBLIC',
        }

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)  # Redirect to login page
        self.assertIn('/accounts/login/', response.url)  # Verify redirect to login page

        # Verify that no post was created in the database
        self.assertFalse(Post.objects.filter(title='Test Unauthenticated Post').exists())

        # TODO : Add tests for edit/delete posts
    

    def test_my_posts_view(self):
        """
        Test that an authenticated user can view their posts.
        """
        url = reverse('my_posts')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test Post 1')
        self.assertContains(response, 'Test Post 2')
    
    def test_my_posts_view_unauthenticated(self):
        """
        Test that an unauthenticated user cannot view the my_posts page.
        """
        self.client.logout()  # Log out the user
        url = reverse('my_posts')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)  # Redirect to login page
        self.assertIn('/accounts/login/', response.url)  # Verify redirect to login page
    
    def test_edit_post_view(self):
        """
        Test that an authenticated user can edit their post.
        """
        url = reverse('edit_post', args=[self.post1.id])
        data = {
            'title': 'Updated Test Post 1',
            'content': 'This is an updated test post.',
            'content_type': 'text/plain',
            'visibility': 'FRIENDS',
        }

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)  # Redirect after successful update
        self.assertEqual(response.url, reverse('my_posts'))  # Redirect to my_posts page

        # Verify that the post was updated in the database
        updated_post = Post.objects.get(id=self.post1.id)
        self.assertEqual(updated_post.title, 'Updated Test Post 1')
        self.assertEqual(updated_post.content, 'This is an updated test post.')
        self.assertEqual(updated_post.visibility, 'FRIENDS')

    def test_edit_post_view_unauthenticated(self):
        """
        Test that an unauthenticated user cannot edit a post.
        """
        self.client.logout()  # Log out the user
        url = reverse('edit_post', args=[self.post1.id])
        data = {
            'title': 'Unauthenticated Edit',
            'content': 'This edit should not be allowed.',
            'content_type': 'text/plain',
            'visibility': 'PUBLIC',
        }

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)  # Redirect to login page
        self.assertIn('/accounts/login/', response.url)  # Verify redirect to login page

        # Verify that the post was not updated in the database
        post = Post.objects.get(id=self.post1.id)
        self.assertNotEqual(post.title, 'Unauthenticated Edit')

    def test_delete_post_view(self):
        """
        Test that an authenticated user can delete their post.
        """
        url = reverse('delete_post', args=[self.post1.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)  # Redirect after successful deletion
        self.assertEqual(response.url, reverse('my_posts'))  # Redirect to my_posts page

        # Verify that the post was marked as deleted in the database
        deleted_post = Post.objects.get(id=self.post1.id)
        self.assertEqual(deleted_post.visibility, 'DELETED')

    def test_delete_post_view_unauthenticated(self):
        """
        Test that an unauthenticated user cannot delete a post.
        """
        self.client.logout()  # Log out the user
        url = reverse('delete_post', args=[self.post1.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)  # Redirect to login page
        self.assertIn('/accounts/login/', response.url)  # Verify redirect to login page

        # Verify that the post was not marked as deleted in the database
        post = Post.objects.get(id=self.post1.id)
        self.assertNotEqual(post.visibility, 'DELETED')