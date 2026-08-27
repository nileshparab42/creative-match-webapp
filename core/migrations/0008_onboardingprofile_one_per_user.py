from django.db import migrations, models
import django.db.models.deletion


def dedupe_onboarding_profiles(apps, schema_editor):
    OnboardingProfile = apps.get_model('core', 'OnboardingProfile')
    seen_users = set()
    for profile in OnboardingProfile.objects.order_by('user_id', '-created_at'):
        if profile.user_id is None:
            continue
        if profile.user_id in seen_users:
            profile.delete()
        else:
            seen_users.add(profile.user_id)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0007_oauthcredential_email'),
    ]

    operations = [
        migrations.RunPython(dedupe_onboarding_profiles, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='onboardingprofile',
            name='user',
            field=models.OneToOneField(null=True, blank=True, on_delete=django.db.models.deletion.CASCADE, to='auth.user'),
        ),
    ]
