from django.db import models
from django.contrib.auth.models import User

# Create your models here.
class Test(models.Model):
    name = models.CharField(max_length=100)

class OAuthCredential(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    google_user_id = models.CharField(max_length=50, blank=True)
    # email = models.EmailField(unique=True)  # New field
    email = models.EmailField(null=True, blank=True)

    token = models.TextField()
    refresh_token = models.TextField(null=True, blank=True)
    token_uri = models.CharField(max_length=255)
    client_id = models.CharField(max_length=255)
    client_secret = models.CharField(max_length=255)
    scopes = models.TextField()

    selected_campaigns = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class OnboardingProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    ga4_property_id = models.CharField(max_length=50)
    ga4_account_id = models.CharField(max_length=50, null=True, blank=True)
    gads_customer_id = models.CharField(max_length=50)
    bigquery_dataset_path = models.CharField(max_length=255, null=True, blank=True)
    ga4_measurement_id = models.CharField(max_length=50)
    mp_api_secret = models.CharField(max_length=255)  # consider encrypting at rest
    business = models.CharField(max_length=50)
    business_parameter = models.CharField(max_length=100)
    notif_email = models.EmailField()
    created_at = models.DateTimeField(auto_now_add=True)
    