from django.urls import path
from . import views

urlpatterns = [
    path('', views.login_view, name='login'),
    path('test/', views.test, name='test'),
    path('gads/', views.gads, name='gads'),
    path('home/', views.home, name='home'),
    path('run_prediction_script/', views.run_prediction_script, name='run_prediction_script'),
    path('run_train_script/', views.run_train_script, name='run_train_script'),
    path('select-creatives/', views.select_creative, name='select_creative'),
    path('campaign/', views.campaign, name='campaign'),
    path('run/', views.run, name='run'),
    path('audiences/', views.audiences, name='audiences'),
    path('creatives/', views.creatives, name='creatives'),
    path('scores/', views.scores, name='scores'),
    path('settings/', views.settings, name='settings'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('onboarding/', views.onboarding, name='onboarding'),
    path('save-onboarding/', views.save_onboarding, name='save_onboarding'),
    path('save-settings/', views.save_settings, name='save_settings'),
    path('google-login/', views.google_login, name='google_login'),
    path('oauth2callback/', views.oauth2callback, name='oauth2callback'),
    # path("trigger-job/", views.trigger_creative_match_job, name="trigger_creative_match_job"),
]

