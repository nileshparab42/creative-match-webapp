import json
import os
import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote_plus

from django.contrib.auth import authenticate, login
from django.contrib.auth.models import User
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from google.ads.googleads.client import GoogleAdsClient
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from .models import OAuthCredential, OnboardingProfile

# Only relax OAuth's HTTPS requirement for local dev over http://127.0.0.1.
# Cloud Run always serves over https, so this must stay off in production.
if os.environ.get("DJANGO_DEBUG", "").strip().lower() in ("1", "true", "yes", "on") or "K_SERVICE" not in os.environ:
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

# Path to the downloaded Google OAuth client secret JSON. Keep this file out of
# git; locally it can sit at the repo root, on Cloud Run mount it via a Secret
# Manager secret (as a volume) and point GOOGLE_CLIENT_SECRET_FILE at that path.
CLIENT_SECRET_FILE = os.environ.get(
    "GOOGLE_CLIENT_SECRET_FILE",
    str(Path(__file__).resolve().parent.parent / "client_secret.json"),
)

# Must exactly match a redirect URI registered on the OAuth client, and must be
# https:// once deployed. Set OAUTH_REDIRECT_URI to your Cloud Run URL +
# "/oauth2callback/" as a service env var.
REDIRECT_URI = os.environ.get("OAUTH_REDIRECT_URI", "http://127.0.0.1:8000/oauth2callback/")

DEVELOPER_TOKEN = os.environ.get("GOOGLE_ADS_DEVELOPER_TOKEN", "")
if not DEVELOPER_TOKEN:
    print("WARNING: GOOGLE_ADS_DEVELOPER_TOKEN is not set; Google Ads calls will fail.")

SCOPES = [
    "https://www.googleapis.com/auth/bigquery",
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/userinfo.profile",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/adwords",
]

AUDIENCE_COLORS = [
    "#4f8ef7",
    "#3ecf8e",
    "#a78bfa",
    "#f59e0b",
    "#ef4444",
    "#14b8a6",
    "#8b5cf6",
]

AD_GROUP_AD_ID_RE = re.compile(r"Ad Group:\s*(.*?)\s*&\s*AD ID:\s*(\d+)")


# ---------------------------------------------------------------------------
# Google Ads helpers
# ---------------------------------------------------------------------------

def _build_flow(**kwargs):
    """Build a Flow from GOOGLE_CLIENT_SECRET_FILE, whether it holds a file
    path (local dev) or raw JSON content (Cloud Run, injected via Secret
    Manager env var)."""
    raw = CLIENT_SECRET_FILE.strip()
    if raw.startswith("{"):
        client_config = json.loads(raw)
        return Flow.from_client_config(client_config, **kwargs)
    return Flow.from_client_secrets_file(raw, **kwargs)


def credentials_to_dict(creds):
    return {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
    }


def get_google_ads_client(creds_data):
    """Build a GoogleAdsClient from the session's stored OAuth credentials."""
    return GoogleAdsClient.load_from_dict({
        "developer_token": DEVELOPER_TOKEN,
        "client_id": creds_data["client_id"],
        "client_secret": creds_data["client_secret"],
        "refresh_token": creds_data["refresh_token"],
        "use_proto_plus": True,
    })


def get_accessible_customer_ids(client):
    """Return the list of customer IDs the authenticated user can access."""
    customer_service = client.get_service("CustomerService")
    response = customer_service.list_accessible_customers()
    return [name.split("/")[-1] for name in response.resource_names]


def get_children(client, customer_id):
    """Recursively fetch child accounts under an MCC."""
    ga_service = client.get_service("GoogleAdsService")

    query = """
        SELECT
            customer_client.id,
            customer_client.descriptive_name,
            customer_client.manager,
            customer_client.level,
            customer_client.status
        FROM customer_client
        WHERE customer_client.level = 1
    """

    response = ga_service.search(customer_id=customer_id, query=query)

    children = []
    for row in response:
        child_id = str(row.customer_client.id)

        child = {
            "customer_id": child_id,
            "name": row.customer_client.descriptive_name,
            "manager": row.customer_client.manager,
            "level": row.customer_client.level,
            "status": row.customer_client.status.name,
        }

        if row.customer_client.manager:
            try:
                child["children"] = get_children(client, child_id)
            except Exception:
                child["children"] = []

        children.append(child)

    return children


def parse_ad_group_and_id(description):
    """Extract (ad_group, ad_id) from a user list description, if present."""
    match = AD_GROUP_AD_ID_RE.search(description or "")
    if not match:
        return "-", "-"
    return match.group(1), match.group(2)


def build_campaign_link(list_name, ad_id):
    campaign_name = quote_plus(list_name)
    return (
        "https://www.paruluniversity.ac.in/"
        f"?utm_source=google&utm_medium=display"
        f"&utm_campaign={campaign_name}&utm_content={ad_id}"
    )


def fetch_ad_images_by_ad_id(ga_service, customer_id):
    """Return {ad_id: [image_url, ...]} for all ads with image assets."""
    ad_images = defaultdict(list)

    query = """
        SELECT
            ad_group_ad.ad.id,
            asset.image_asset.full_size.url
        FROM ad_group_ad_asset_view
        WHERE asset.image_asset.full_size.url IS NOT NULL
    """

    for row in ga_service.search(customer_id=customer_id, query=query):
        image_url = row.asset.image_asset.full_size.url
        if image_url:
            ad_images[row.ad_group_ad.ad.id].append(image_url)

    return ad_images


def fetch_audiences(ga_service, customer_id, ad_images=None, limit=5):
    """Fetch 'Creative Match' user lists formatted for the audiences template."""
    query = f"""
        SELECT
            user_list.id,
            user_list.name,
            user_list.description,
            user_list.size_for_display,
            user_list.type
        FROM user_list
        WHERE user_list.name LIKE 'Creative Match%'
        ORDER BY user_list.size_for_display DESC
        LIMIT {limit}
    """

    audiences = []
    for i, row in enumerate(ga_service.search(customer_id=customer_id, query=query)):
        ad_group, ad_id = parse_ad_group_and_id(row.user_list.description)

        image_url = None
        if ad_images is not None and ad_id != "-":
            images = ad_images.get(int(ad_id), [])
            image_url = images[-1] if images else None

        entry = {
            "segment_name": row.user_list.name,
            "dot_color": AUDIENCE_COLORS[i % len(AUDIENCE_COLORS)],
            "audience_size": f"{row.user_list.size_for_display:,}",
            "audience_size_raw": row.user_list.size_for_display,
            "ad_group": ad_group,
            "ad_id": ad_id,
            "campaign_type": row.user_list.type.name.replace("_", " ").title(),
            "campaign_badge": "badge-accent",
            "campaign_link": build_campaign_link(row.user_list.name, ad_id),
        }
        if ad_images is not None:
            entry["image_url"] = image_url

        audiences.append(entry)

    return audiences


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------
# views.py
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.http import JsonResponse
from django.utils import timezone as django_timezone
from django.views.decorators.http import require_POST
from google.cloud import run_v2

PROJECT_ID = "parul-university-website"
REGION = "asia-south1"
PREDICTION_JOB_NAME = "creativematch-predict"
TRAIN_JOB_NAME = "creativematch-fetch-train"

IST = ZoneInfo("Asia/Kolkata")

from django.contrib import messages

def _get_last_execution_status(job_name):
    """Latest Cloud Run Jobs execution for job_name: status + when it ran, in IST."""
    if not job_name:
        return None

    try:
        client = run_v2.ExecutionsClient()
        parent = client.job_path(PROJECT_ID, REGION, job_name)
        executions = list(client.list_executions(parent=parent))
        if not executions:
            return None

        latest = max(executions, key=lambda e: e.create_time)

        if latest.succeeded_count > 0:
            status = "success"
        elif latest.failed_count > 0:
            status = "failed"
        elif latest.running_count > 0:
            status = "running"
        else:
            status = "pending"

        timestamp = latest.completion_time or latest.start_time or latest.create_time
        return {
            "status": status,
            "timestamp": timestamp.astimezone(IST) if timestamp else None,
            "log_uri": latest.log_uri or None,
        }
    except Exception as e:
        print(f"Failed to fetch last execution for job '{job_name}': {e}")
        return None


def _next_daily_run(hour=3, minute=0):
    """Next occurrence of hour:minute IST, today or tomorrow."""
    now_ist = django_timezone.now().astimezone(IST)
    candidate = now_ist.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now_ist:
        candidate += timedelta(days=1)
    return candidate


def _next_monthly_run(day=1, hour=2, minute=0):
    """Next occurrence of day/hour:minute IST, this month or next."""
    now_ist = django_timezone.now().astimezone(IST)
    candidate = now_ist.replace(day=day, hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now_ist:
        if candidate.month == 12:
            candidate = candidate.replace(year=candidate.year + 1, month=1)
        else:
            candidate = candidate.replace(month=candidate.month + 1)
    return candidate


def _describe_next_run(run_time, now_ist):
    """Human label like 'today 3:00 AM' / 'tomorrow 3:00 AM' / 'Sep 1, 2:00 AM'."""
    hour_12 = run_time.hour % 12 or 12
    time_str = f"{hour_12}:{run_time.minute:02d} {'AM' if run_time.hour < 12 else 'PM'}"
    days_ahead = (run_time.date() - now_ist.date()).days
    if days_ahead == 0:
        return f"today {time_str}"
    if days_ahead == 1:
        return f"tomorrow {time_str}"
    return f"{run_time.strftime('%b')} {run_time.day}, {time_str}"


def _format_count(n):
    """1234 -> '1.2k', 999 -> '999'."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def _trigger_job(job_name, request):
    if not job_name:
        messages.error(request, f"Job not configured: {job_name!r}")
        return redirect("/home")

    try:
        client = run_v2.JobsClient()
        job_path = client.job_path(PROJECT_ID, REGION, job_name)

        request_obj = run_v2.RunJobRequest(name=job_path)
        operation = client.run_job(request=request_obj)

        execution_name = operation.metadata.name if operation.metadata else None
        messages.success(request, f"Job '{job_name}' triggered successfully.")

    except Exception as e:
        messages.error(request, f"Failed to trigger job '{job_name}': {e}")

    return redirect("/home")

def gads(request):
    creds_data = request.session.get("credentials")
    if not creds_data:
        return redirect("login")

    client = get_google_ads_client(creds_data)
    customer_id = get_accessible_customer_ids(client)[0]
    ga_service = client.get_service("GoogleAdsService")

    query = """
        SELECT
            campaign.id,
            campaign.name,
            asset.image_asset.full_size.url
        FROM asset_group_asset
        WHERE campaign.advertising_channel_type = 'PERFORMANCE_MAX'
    """

    campaigns = {}
    for row in ga_service.search(customer_id=customer_id, query=query):
        campaign_id = str(row.campaign.id)

        if campaign_id not in campaigns:
            campaigns[campaign_id] = {
                "campaign_id": campaign_id,
                "campaign_name": row.campaign.name,
                "images": [],
            }

        image_url = row.asset.image_asset.full_size.url
        if image_url:
            campaigns[campaign_id]["images"].append(image_url)

    return JsonResponse({"campaigns": list(campaigns.values())}, safe=False)


def test(request):
    creds_data = request.session.get("credentials")
    if not creds_data:
        return redirect("login")

    try:
        client = get_google_ads_client(creds_data)
        accessible_ids = get_accessible_customer_ids(client)

        hierarchy = [
            {"customer_id": customer_id, "children": get_children(client, customer_id)}
            for customer_id in accessible_ids
        ]

        return JsonResponse({
            "success": True,
            "accessible_accounts": len(accessible_ids),
            "hierarchy": hierarchy,
        })

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


def run(request):
    if not request.user.is_authenticated:
        return render(request, "login.html")
                
    creds_data = get_valid_credentials(request)
    if not creds_data:
        return render(request, "login.html", {
            "error": "Your Google session has expired. Please reconnect.",
        })
    campaigns = request.GET.getlist("selected_campaigns")

    credential = OAuthCredential.objects.get(user=request.user)
    credential.selected_campaigns = campaigns
    credential.save()

    return render(request, "run.html")


def audiences(request):
    if not request.user.is_authenticated:
            return render(request, "login.html")
                
    creds_data = get_valid_credentials(request)
    if not creds_data:
        return render(request, "login.html", {
            "error": "Your Google session has expired. Please reconnect.",
        })
    creds_data = request.session.get("credentials")
    if not creds_data:
        return render(request, "audiences.html", {"audiences": []})

    try:
        client = get_google_ads_client(creds_data)
        accounts = get_accessible_customer_ids(client)

        if not accounts:
            return render(request, "audiences.html", {
                "audiences": [],
                "error": "No Google Ads accounts found.",
            })

        ga_service = client.get_service("GoogleAdsService")
        audience_list = fetch_audiences(ga_service, accounts[0],limit=100)

    except Exception as e:
        print("Google Ads Error:", e)
        return render(request, "audiences.html", {"audiences": [], "error": str(e)})

    return render(request, "audiences.html", {"audiences": audience_list})


def creatives(request):
    if not request.user.is_authenticated:
        return render(request, "login.html")
                
    creds_data = get_valid_credentials(request)
    if not creds_data:
        return render(request, "login.html", {
            "error": "Your Google session has expired. Please reconnect.",
        })
    return render(request, "creatives.html")


def scores(request):
    if not request.user.is_authenticated:
        return render(request, "login.html")
                
    creds_data = get_valid_credentials(request)
    if not creds_data:
        return render(request, "login.html", {
            "error": "Your Google session has expired. Please reconnect.",
        })
    return render(request, "scores.html")


def settings(request):
    if not request.user.is_authenticated:
        return render(request, "login.html")
                
    creds_data = get_valid_credentials(request)
    if not creds_data:
        return render(request, "login.html", {
            "error": "Your Google session has expired. Please reconnect.",
        })
    return render(request, "settings.html")

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleAuthRequest

def get_valid_credentials(request):
    """
    Returns a refreshed credentials dict, updating the session if the
    access token was refreshed. Returns None if credentials are missing
    or the refresh_token itself is invalid/revoked.
    """
    creds_data = request.session.get("credentials")
    if not creds_data:
        return None

    creds = Credentials(
        token=creds_data.get("token"),
        refresh_token=creds_data.get("refresh_token"),
        token_uri=creds_data.get("token_uri"),
        client_id=creds_data.get("client_id"),
        client_secret=creds_data.get("client_secret"),
        scopes=creds_data.get("scopes"),
    )

    # Refresh if expired (or about to expire)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(GoogleAuthRequest())
            except Exception as e:
                print("Token refresh failed:", e)
                return None  # refresh_token revoked/invalid -> force real re-login
        else:
            return None

    # Persist refreshed token back into session
    creds_data["token"] = creds.token
    creds_data["expiry"] = creds.expiry.isoformat() if creds.expiry else None
    request.session["credentials"] = creds_data
    request.session.modified = True

    return creds_data


def home(request):
    if not request.user.is_authenticated:
        return render(request, "login.html")

    creds_data = get_valid_credentials(request)
    if not creds_data:
        return render(request, "login.html", {
            "error": "Your Google session has expired. Please reconnect.",
        })

    try:
        client = get_google_ads_client(creds_data)
        accounts = get_accessible_customer_ids(client)

        if not accounts:
            return render(request, "login.html", {
                "campaigns": [],
                "audiences": [],
                "error": "No Google Ads accounts found.",
            })

        customer_id = accounts[0]
        ga_service = client.get_service("GoogleAdsService")

        # Campaigns (with a representative image per campaign)
        campaign_query = """
            SELECT
                campaign.id,
                campaign.name,
                campaign.status,
                campaign.advertising_channel_type,
                asset.image_asset.full_size.url
            FROM asset_group_asset
            WHERE asset.image_asset.full_size.url IS NOT NULL
            LIMIT 10
        """

        campaigns_dict = {}
        for row in ga_service.search(customer_id=customer_id, query=campaign_query):
            campaign_id = row.campaign.id

            if campaign_id not in campaigns_dict:
                campaigns_dict[campaign_id] = {
                    "id": campaign_id,
                    "name": row.campaign.name,
                    "type": row.campaign.advertising_channel_type.name,
                    "status": row.campaign.status.name,
                    "score": 0.91,
                    "image": None,
                }

            image_url = row.asset.image_asset.full_size.url
            if image_url and campaigns_dict[campaign_id]["image"] is None:
                campaigns_dict[campaign_id]["image"] = image_url

        campaigns = list(campaigns_dict.values())

        # Ad images, keyed by ad id, reused when resolving audience thumbnails
        ad_images = fetch_ad_images_by_ad_id(ga_service, customer_id)

        # Audiences
        audience_list = fetch_audiences(ga_service, customer_id, ad_images=ad_images,limit=100)

    except Exception as e:
        print("Google Ads Error:", e)
        return render(request, "login.html", {
            "campaigns": [],
            "audiences": [],
            "error": str(e),
        })

    now_ist = django_timezone.now().astimezone(IST)
    daily_next_run = _next_daily_run()
    monthly_next_run = _next_monthly_run()
    next_run = min(daily_next_run, monthly_next_run)
    daily_last_run = _get_last_execution_status(PREDICTION_JOB_NAME)

    total_audience_size = sum(a["audience_size_raw"] for a in audience_list)

    return render(request, "home.html", {
        "campaigns": campaigns,
        "audiences": audience_list,
        "audiences_count": len(audience_list),
        "total_audience_size": _format_count(total_audience_size) if audience_list else None,
        "daily_last_run": daily_last_run,
        "monthly_last_run": _get_last_execution_status(TRAIN_JOB_NAME),
        "next_run_label": _describe_next_run(next_run, now_ist),
    })


def dashboard(request):
    if not request.user.is_authenticated:
        return render(request, "login.html")
    
    creds_data = get_valid_credentials(request)
    if not creds_data:
        return render(request, "login.html", {
            "error": "Your Google session has expired. Please reconnect.",
        })
    return render(request, "dashboard.html")


def campaign(request):
    if not request.user.is_authenticated:
        return render(request, "login.html")
        
    creds_data = get_valid_credentials(request)
    if not creds_data:
        return render(request, "login.html", {
            "error": "Your Google session has expired. Please reconnect.",
        })
    email = request.user.email
    audience_id = request.GET.get("audience_id")
    image_url = request.GET.get("image_url")
    segment_name = request.GET.get("segment_name")


    audience_characteristics = []
    creative_overview = ""

    if audience_id:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT creatives
                FROM audience_creative_data
                WHERE email = %s
                  AND audience_id = %s
                LIMIT 1
                """,
                [email, audience_id],
            )
            row = cursor.fetchone()

        if row:
            creative_json = row[0]
            if isinstance(creative_json, str):
                creative_json = json.loads(creative_json)

            recommendations = creative_json.get("recommendations", {})
            creative_overview = recommendations.get("creative_overview", "")
            audience_characteristics = recommendations.get("audienceCharacteristics", [])

    return render(request, "campaign.html", {
        "creative_overview": creative_overview,
        "audience_characteristics": audience_characteristics,
        "audience_id": audience_id,
        "image_url": image_url,
        "segment_name": segment_name,
    })

import subprocess
import sys
from django.http import JsonResponse

# These views used to shell out to a hardcoded Windows path (D:\OneDrive\...),
# which only ever existed on one laptop and will always fail on Cloud Run
# (different OS, no such filesystem, no such file in the container image).
#
# For this to work in both environments, the target script must ship inside
# the repo so it's present both locally and in the Cloud Run build. Point
# PREDICTION_SCRIPT_PATH / TRAIN_SCRIPT_PATH at that in-repo location, e.g.
# BASE_DIR / "scripts" / "hello.py", and set the env vars only if you need to
# override that for local testing.
PREDICTION_SCRIPT_PATH = os.environ.get("PREDICTION_SCRIPT_PATH", "")
TRAIN_SCRIPT_PATH = os.environ.get("TRAIN_SCRIPT_PATH", "")


def _run_script(script_path, request):
    if not script_path or not os.path.exists(script_path):
        print(f"Script not configured or not found: {script_path!r}")
        return redirect("/home")

    try:
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            check=True,
        )
        print("=== Script Output ===")
        print(result.stdout)
        if result.stderr:
            print("=== Script Error ===")
            print(result.stderr)
    except subprocess.CalledProcessError as e:
        print("Script failed!")
        print(e.stderr)

    return redirect("/home")


# def run_prediction_script(request):
#     return _run_script(PREDICTION_SCRIPT_PATH, request)


# def run_train_script(request):
#     return _run_script(TRAIN_SCRIPT_PATH, request)

def run_prediction_script(request):
    return _trigger_job(PREDICTION_JOB_NAME, request)


def run_train_script(request):
    return _trigger_job(TRAIN_JOB_NAME, request)


def onboarding(request):
    if not request.user.is_authenticated:
        return render(request, "login.html")
            
    creds_data = get_valid_credentials(request)
    if not creds_data:
        return render(request, "login.html", {
            "error": "Your Google session has expired. Please reconnect.",
        })
    return render(request, "onboarding.html")


def to_camel_case(text):
    words = re.split(r"[\s_-]+", text.strip())
    return "".join(word.capitalize() for word in words if word)


@require_POST
def save_onboarding(request):
    data = json.loads(request.body)

    OnboardingProfile.objects.create(
        user=request.user if request.user.is_authenticated else None,
        ga4_property_id=data.get("ga4id"),
        gads_customer_id=data.get("gadsid"),
        ga4_measurement_id=data.get("measurementid"),
        mp_api_secret=data.get("mpsecret"),
        business=data.get("business"),
        business_parameter=to_camel_case(data.get("businessParameter", "")),
        notif_email=data.get("notifEmail"),
    )

    return JsonResponse({"status": "ok"})


def select_creative(request):
    if not request.user.is_authenticated:
            return render(request, "login.html")
                
    creds_data = get_valid_credentials(request)
    if not creds_data:
        return render(request, "login.html", {
            "error": "Your Google session has expired. Please reconnect.",
        })
    email = request.user.email

    creative_data = []

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT creative_links
            FROM email_creative_links
            WHERE email = %s
            """,
            [email],
        )
        row = cursor.fetchone()

    if row:
        links = row[0]
        if isinstance(links, str):
            links = json.loads(links)

        for creative_id, value in links.items():
            creative_data.append({
                "creative_id": creative_id,
                "ad_id": value.get("ad_id"),
                "primary_image": value.get("primary_image"),
            })

    return render(request, "select-creative.html", {"creative_data": creative_data})


def google_login(request):
    flow = _build_flow(scopes=SCOPES, redirect_uri=REDIRECT_URI)

    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )

    request.session["state"] = state
    if getattr(flow, "code_verifier", None):
        request.session["code_verifier"] = flow.code_verifier

    return redirect(authorization_url)


def oauth2callback(request):
    flow = _build_flow(
        scopes=SCOPES,
        state=request.session.get("state"),
        redirect_uri=REDIRECT_URI,
    )

    if request.session.get("code_verifier"):
        flow.code_verifier = request.session["code_verifier"]

    flow.fetch_token(authorization_response=request.build_absolute_uri())
    credentials = flow.credentials

    request.session["credentials"] = credentials_to_dict(credentials)

    oauth2 = build("oauth2", "v2", credentials=credentials)
    user_info = oauth2.userinfo().get().execute()

    email = user_info["email"]

    user, created = User.objects.get_or_create(
        username=email,
        defaults={
            "email": email,
            "first_name": user_info.get("given_name", ""),
            "last_name": user_info.get("family_name", ""),
        },
    )

    user.email = email
    user.first_name = user_info.get("given_name", "")
    user.last_name = user_info.get("family_name", "")
    user.save()

    login(request, user, backend="django.contrib.auth.backends.ModelBackend")

    OAuthCredential.objects.update_or_create(
        user=user,
        defaults={
            "google_user_id": user_info["id"],
            "email": user_info["email"],
            "token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_uri": credentials.token_uri,
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "scopes": ",".join(credentials.scopes),
        },
    )

    return redirect("onboarding")


def login_view(request):
    if request.user.is_authenticated:
        creds_data = get_valid_credentials(request)
        if creds_data:
            return redirect("home")

    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        if not username or not password:
            return render(request, "login.html", {
                "error": "Please enter both username and password",
            })

        user = authenticate(request, username=username, password=password)

        if user:
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            return redirect("home")

        return render(request, "login.html", {"error": "Invalid username or password"})

    return render(request, "login.html")