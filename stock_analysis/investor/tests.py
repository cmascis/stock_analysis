from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse


class AuthWorkflowTests(TestCase):
    def test_signup_creates_user_and_redirects_home(self):
        response = self.client.post(
            reverse("signup"),
            {
                "username": "newuser",
                "password1": "S3cur3Pass123!!",
                "password2": "S3cur3Pass123!!",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("home"))
        self.assertTrue(get_user_model().objects.filter(username="newuser").exists())

    def test_login_and_logout_flow(self):
        user_model = get_user_model()
        user_model.objects.create_user(username="alice", password="S3cur3Pass123!!")

        login_response = self.client.post(
            reverse("login"),
            {"username": "alice", "password": "S3cur3Pass123!!"},
        )
        self.assertEqual(login_response.status_code, 302)
        self.assertRedirects(login_response, reverse("home"))

        logout_response = self.client.post(reverse("logout"))
        self.assertEqual(logout_response.status_code, 302)
        self.assertRedirects(logout_response, reverse("home"))
