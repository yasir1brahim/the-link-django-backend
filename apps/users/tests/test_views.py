from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.models import CustomUser


class PasswordResetTokenValidationViewTests(APITestCase):
    """Tests for the PasswordResetTokenValidationView endpoint."""

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='testuser',
            email='testuser@example.com',
            password='testpassword123'
        )
        self.url = '/api/auth/password/reset/validate/'

    def _get_valid_uid_and_token(self, user):
        """Generate a valid uid and token for the given user."""
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        return uid, token

    def test_valid_token_returns_valid_true(self):
        """Test that a valid token returns {'valid': True}."""
        uid, token = self._get_valid_uid_and_token(self.user)

        response = self.client.get(self.url, {'uid': uid, 'token': token})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['valid'])
        self.assertEqual(response.data['message'], 'Token is valid.')

    def test_expired_token_returns_valid_false_with_expired_error(self):
        """Test that an expired/invalid token returns {'valid': False, 'error': 'expired'}.

        Note: We simulate an expired token by modifying the user's password after
        token generation, which invalidates the token.
        """
        uid, token = self._get_valid_uid_and_token(self.user)

        # Invalidate the token by changing the user's password
        self.user.set_password('newpassword123')
        self.user.save()

        response = self.client.get(self.url, {'uid': uid, 'token': token})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['valid'])
        self.assertEqual(response.data['error'], 'expired')
        self.assertIn('expired', response.data['message'].lower())

    def test_invalid_uid_returns_valid_false_with_invalid_error(self):
        """Test that an invalid uid returns {'valid': False, 'error': 'invalid'}."""
        # Use a non-existent user ID
        invalid_uid = urlsafe_base64_encode(force_bytes(99999))
        token = 'sometoken'

        response = self.client.get(self.url, {'uid': invalid_uid, 'token': token})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['valid'])
        self.assertEqual(response.data['error'], 'invalid')

    def test_malformed_uid_returns_valid_false_with_invalid_error(self):
        """Test that a malformed uid returns {'valid': False, 'error': 'invalid'}."""
        response = self.client.get(self.url, {'uid': 'not-valid-base64!!!', 'token': 'sometoken'})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['valid'])
        self.assertEqual(response.data['error'], 'invalid')

    def test_malformed_token_returns_valid_false(self):
        """Test that a malformed token returns {'valid': False}."""
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))

        response = self.client.get(self.url, {'uid': uid, 'token': 'completely-invalid-token'})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['valid'])
        # Malformed tokens are treated as expired since the user exists but token doesn't match
        self.assertEqual(response.data['error'], 'expired')

    def test_missing_uid_parameter_returns_400(self):
        """Test that missing uid parameter returns 400 error."""
        response = self.client.get(self.url, {'token': 'sometoken'})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
        self.assertIn('Missing', response.data['error'])

    def test_missing_token_parameter_returns_400(self):
        """Test that missing token parameter returns 400 error."""
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))

        response = self.client.get(self.url, {'uid': uid})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
        self.assertIn('Missing', response.data['error'])

    def test_missing_both_parameters_returns_400(self):
        """Test that missing both parameters returns 400 error."""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
        self.assertIn('Missing', response.data['error'])

    def test_token_invalid_after_password_reset(self):
        """Test that a token becomes invalid after it's used to reset the password."""
        uid, token = self._get_valid_uid_and_token(self.user)

        # First, verify the token is valid
        response = self.client.get(self.url, {'uid': uid, 'token': token})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['valid'])

        # Use the token to reset the password via the confirm endpoint
        confirm_url = '/api/auth/password/reset/confirm/'
        confirm_response = self.client.post(confirm_url, {
            'uid': uid,
            'token': token,
            'new_password1': 'newSecurePassword123!',
            'new_password2': 'newSecurePassword123!'
        })
        self.assertEqual(confirm_response.status_code, status.HTTP_200_OK)

        # Now the same token should be invalid (expired)
        response = self.client.get(self.url, {'uid': uid, 'token': token})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['valid'])
        self.assertEqual(response.data['error'], 'expired')

    def test_empty_uid_parameter_returns_400(self):
        """Test that empty uid parameter returns 400 error."""
        response = self.client.get(self.url, {'uid': '', 'token': 'sometoken'})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)

    def test_empty_token_parameter_returns_400(self):
        """Test that empty token parameter returns 400 error."""
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))

        response = self.client.get(self.url, {'uid': uid, 'token': ''})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
