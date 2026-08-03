from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
import os
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from google_auth_oauthlib.flow import Flow
from django.http import JsonResponse
from google.ads.googleads.client import GoogleAdsClient
from googleapiclient.discovery import build
import re
import json
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from .models import OnboardingProfile, OAuthCredential
from django.contrib.auth.models import User

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

CLIENT_SECRET_FILE = "client_secret.json"

DEVELOPER_TOKEN = "wsl12rygNVvukgoxJSrCUg"

SCOPES = [
    "https://www.googleapis.com/auth/bigquery",
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/userinfo.profile",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/adwords",
]

# Create your views here.

def credentials_to_dict(creds):
    return {
        'token': creds.token,
        'refresh_token': creds.refresh_token,
        'token_uri': creds.token_uri,
        'client_id': creds.client_id,
        'client_secret': creds.client_secret,
        'scopes': creds.scopes
    }


def gads(request):
    creds_data = request.session.get("credentials")

    if not creds_data:
        return redirect("login")

    client = GoogleAdsClient.load_from_dict({
        "developer_token": DEVELOPER_TOKEN,
        "client_id": creds_data["client_id"],
        "client_secret": creds_data["client_secret"],
        "refresh_token": creds_data["refresh_token"],
        "use_proto_plus": True,
    })

    customer_service = client.get_service("CustomerService")
    response = customer_service.list_accessible_customers()

    customer_id = response.resource_names[0].split("/")[-1]

    ga_service = client.get_service("GoogleAdsService")

    query = """
        SELECT
            campaign.id,
            campaign.name,
            asset.image_asset.full_size.url
        FROM asset_group_asset
        WHERE campaign.advertising_channel_type = 'PERFORMANCE_MAX'
    """

    ads_response = ga_service.search(
        customer_id=customer_id,
        query=query
    )

    campaigns = {}

    for row in ads_response:
        campaign_id = str(row.campaign.id)
        campaign_name = row.campaign.name

        if campaign_id not in campaigns:
            campaigns[campaign_id] = {
                "campaign_id": campaign_id,
                "campaign_name": campaign_name,
                "images": []
            }

        image_url = row.asset.image_asset.full_size.url

        if image_url:
            campaigns[campaign_id]["images"].append(image_url)

    return JsonResponse(
        {"campaigns": list(campaigns.values())},
        safe=False
    )

from django.http import JsonResponse
from django.shortcuts import redirect
from google.ads.googleads.client import GoogleAdsClient
from django.http import JsonResponse
from django.shortcuts import redirect
from google.ads.googleads.client import GoogleAdsClient


def get_children(client, customer_id):
    """
    Recursively fetch child accounts under an MCC.
    """

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

    response = ga_service.search(
        customer_id=customer_id,
        query=query
    )

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

        # If child is another MCC, recurse
        if row.customer_client.manager:
            try:
                child["children"] = get_children(
                    client,
                    child_id
                )
            except Exception:
                child["children"] = []

        children.append(child)

    return children


def test(request):
    creds_data = request.session.get("credentials")

    if not creds_data:
        return redirect("login")

    try:
        # Build Google Ads configuration
        config = {
            "developer_token": DEVELOPER_TOKEN,
            "client_id": creds_data["client_id"],
            "client_secret": creds_data["client_secret"],
            "refresh_token": creds_data["refresh_token"],
            "use_proto_plus": True,
        }

        # Create client
        client = GoogleAdsClient.load_from_dict(config)

        # Get all accounts user can access
        customer_service = client.get_service(
            "CustomerService"
        )

        accessible_customers = (
            customer_service.list_accessible_customers()
        )

        hierarchy = []

        for resource_name in accessible_customers.resource_names:
            customer_id = resource_name.split("/")[-1]

            hierarchy.append({
                "customer_id": customer_id,
                "children": get_children(
                    client,
                    customer_id
                )
            })

        return JsonResponse({
            "success": True,
            "accessible_accounts": len(
                accessible_customers.resource_names
            ),
            "hierarchy": hierarchy
        })

    except Exception as e:
        return JsonResponse(
            {
                "success": False,
                "error": str(e)
            },
            status=500
        )


from django.http import JsonResponse

from .models import OAuthCredential

def run(request):
    campaigns = request.GET.getlist("selected_campaigns")

    credential = OAuthCredential.objects.get(user=request.user)

    credential.selected_campaigns = campaigns
    credential.save()

    return render(request, "run.html")

from django.shortcuts import render

from google.ads.googleads.client import GoogleAdsClient
from urllib.parse import quote_plus

def audiences(request):
    audiences = []

    creds_data = request.session.get("credentials")

    if not creds_data:
        return render(request, "audiences.html", {"audiences": []})

    try:
        client = GoogleAdsClient.load_from_dict({
            "developer_token": DEVELOPER_TOKEN,
            "client_id": creds_data["client_id"],
            "client_secret": creds_data["client_secret"],
            "refresh_token": creds_data["refresh_token"],
            "use_proto_plus": True,
        })

        customer_service = client.get_service("CustomerService")
        response = customer_service.list_accessible_customers()

        accounts = [
            resource_name.split("/")[-1]
            for resource_name in response.resource_names
        ]

        if not accounts:
            return render(
                request,
                "audiences.html",
                {
                    "audiences": [],
                    "error": "No Google Ads accounts found."
                }
            )

        customer_id = accounts[0]

        ga_service = client.get_service("GoogleAdsService")

        query = """
            SELECT
                user_list.id,
                user_list.name,
                user_list.description,
                user_list.size_for_display,
                user_list.type
            FROM user_list
            WHERE user_list.name LIKE 'Creative Match%'
            ORDER BY user_list.size_for_display DESC
        """

        response = ga_service.search(
            customer_id=customer_id,
            query=query
        )

        colors = [
            "#4f8ef7",
            "#3ecf8e",
            "#a78bfa",
            "#f59e0b",
            "#ef4444",
            "#14b8a6",
            "#8b5cf6",
        ]

        for i, row in enumerate(response):

            description = row.user_list.description or ""

            ad_group = "-"
            ad_id = "-"

            match = re.search(
                r"Ad Group:\s*(.*?)\s*&\s*AD ID:\s*(\d+)",
                description
            )

            if match:
                ad_group = match.group(1)
                ad_id = match.group(2)

            campaign_name = quote_plus(row.user_list.name)

            campaign_link = (
                f"https://www.paruluniversity.ac.in/"
                f"?utm_source=google"
                f"&utm_medium=display"
                f"&utm_campaign={campaign_name}"
                f"&utm_content={ad_id}"
            )

            audiences.append({
                "segment_name": row.user_list.name,
                "dot_color": colors[i % len(colors)],
                "audience_size": f"{row.user_list.size_for_display:,}",
                "ad_group": ad_group,
                "ad_id": ad_id,
                "campaign_type": row.user_list.type.name.replace("_", " ").title(),
                "campaign_badge": "badge-accent",
                "campaign_link": campaign_link,   # Replace later with the real landing page
            })
    except Exception as e:
        print("Google Ads Error:", e)
        return render(
            request,
            "audiences.html",
            {
                "audiences": [],
                "error": str(e)
            }
        )

    return render(
        request,
        "audiences.html",
            {
                "audiences": audiences
            }
        )

def creatives(request):    
    return render(request, 'creatives.html')

def scores(request):    
    return render(request, 'scores.html')

def settings(request):    
    return render(request, 'settings.html')

# def home(request):
    campaigns = []
    audiences = []

    creds_data = request.session.get("credentials")

    if not creds_data:
        return render(
            request,
            "home.html",
            {
                "campaigns": [],
                "audiences": []
            }
        )

    try:
        client = GoogleAdsClient.load_from_dict({
            "developer_token": DEVELOPER_TOKEN,
            "client_id": creds_data["client_id"],
            "client_secret": creds_data["client_secret"],
            "refresh_token": creds_data["refresh_token"],
            "use_proto_plus": True,
        })

        customer_service = client.get_service("CustomerService")
        response = customer_service.list_accessible_customers()

        accounts = [
            resource_name.split("/")[-1]
            for resource_name in response.resource_names
        ]

        if not accounts:
            return render(
                request,
                "home.html",
                {
                    "campaigns": [],
                    "audiences": [],
                    "error": "No Google Ads accounts found."
                }
            )

        customer_id = accounts[0]

        ga_service = client.get_service("GoogleAdsService")

        # --------------------
        # CAMPAIGNS
        # --------------------
        campaign_query = """
            SELECT
                campaign.id,
                campaign.name,
                campaign.status,
                campaign.advertising_channel_type,
                asset.image_asset.full_size.url
            FROM asset_group_asset
            WHERE asset.image_asset.full_size.url IS NOT NULL
            LIMIT 100
        """

        ads_response = ga_service.search(
            customer_id=customer_id,
            query=campaign_query
        )

        campaigns_dict = {}

        for row in ads_response:
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

        # --------------------
        # AUDIENCES
        # --------------------
        audience_query = """
            SELECT
                user_list.id,
                user_list.name,
                user_list.description,
                user_list.size_for_search,
                user_list.size_for_display
            FROM user_list
            WHERE user_list.name LIKE 'Creative Match%'
            ORDER BY user_list.size_for_display DESC
            LIMIT 5
        """

        audience_response = ga_service.search(
            customer_id=customer_id,
            query=audience_query
        )

        for row in audience_response:
            audiences.append({
                "id": row.user_list.id,
                "name": row.user_list.name,
                "description": row.user_list.description,
                "search_size": row.user_list.size_for_search,
                "display_size": row.user_list.size_for_display,
            })

    except Exception as e:
        print("Google Ads Error:", e)

        return render(
            request,
            "home.html",
            {
                "campaigns": [],
                "audiences": [],
                "error": str(e)
            }
        )

    return render(
        request,
        "home.html",
        {
            "campaigns": campaigns,
            "audiences": audiences,
        }
    )


import re
from urllib.parse import quote_plus

from google.ads.googleads.client import GoogleAdsClient


def home(request):
    campaigns = []
    audiences = []

    creds_data = request.session.get("credentials")

    if not creds_data:
        return render(
            request,
            "home.html",
            {
                "campaigns": [],
                "audiences": []
            }
        )

    try:
        client = GoogleAdsClient.load_from_dict({
            "developer_token": DEVELOPER_TOKEN,
            "client_id": creds_data["client_id"],
            "client_secret": creds_data["client_secret"],
            "refresh_token": creds_data["refresh_token"],
            "use_proto_plus": True,
        })

        customer_service = client.get_service("CustomerService")
        response = customer_service.list_accessible_customers()

        accounts = [
            resource_name.split("/")[-1]
            for resource_name in response.resource_names
        ]

        if not accounts:
            return render(
                request,
                "home.html",
                {
                    "campaigns": [],
                    "audiences": [],
                    "error": "No Google Ads accounts found."
                }
            )

        customer_id = accounts[0]

        ga_service = client.get_service("GoogleAdsService")

        # =====================================================
        # CAMPAIGNS
        # =====================================================
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

        ads_response = ga_service.search(
            customer_id=customer_id,
            query=campaign_query
        )

        campaigns_dict = {}

        for row in ads_response:
            campaign_id = row.campaign.id

            if campaign_id not in campaigns_dict:
                print(campaign_id)
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

        # =====================================================
        # FETCH ALL AD IMAGES (ONE QUERY)
        # =====================================================
        from collections import defaultdict

        ad_images = defaultdict(list)

        image_query = """
            SELECT
                ad_group_ad.ad.id,
                asset.image_asset.full_size.url
            FROM ad_group_ad_asset_view
            WHERE asset.image_asset.full_size.url IS NOT NULL
        """

        image_response = ga_service.search(
            customer_id=customer_id,
            query=image_query
        )

        for row in image_response:
            ad_id = row.ad_group_ad.ad.id
            image_url = row.asset.image_asset.full_size.url

            if image_url:
                ad_images[ad_id].append(image_url)

        # =====================================================
        # AUDIENCES
        # =====================================================
        audience_query = """
            SELECT
                user_list.id,
                user_list.name,
                user_list.description,
                user_list.size_for_display,
                user_list.type
            FROM user_list
            WHERE user_list.name LIKE 'Creative Match%'
            ORDER BY user_list.size_for_display DESC
            LIMIT 5
        """

        audience_response = ga_service.search(
            customer_id=customer_id,
            query=audience_query
        )

        colors = [
            "#4f8ef7",
            "#3ecf8e",
            "#a78bfa",
            "#f59e0b",
            "#ef4444",
            "#14b8a6",
            "#8b5cf6",
        ]

        for i, row in enumerate(audience_response):

            description = row.user_list.description or ""

            ad_group = "-"
            ad_id = "-"
            image_url = None

            match = re.search(
                r"Ad Group:\s*(.*?)\s*&\s*AD ID:\s*(\d+)",
                description
            )

            if match:
                ad_group = match.group(1)
                ad_id = match.group(2)

                images = ad_images.get(int(ad_id), [])
                image_url = images[-1] if images else None

            campaign_name = quote_plus(row.user_list.name)

            campaign_link = (
                f"https://www.paruluniversity.ac.in/"
                f"?utm_source=google"
                f"&utm_medium=display"
                f"&utm_campaign={campaign_name}"
                f"&utm_content={ad_id}"
            )

            audiences.append({
                "segment_name": row.user_list.name,
                "dot_color": colors[i % len(colors)],
                "audience_size": f"{row.user_list.size_for_display:,}",
                "ad_group": ad_group,
                "ad_id": ad_id,
                "campaign_type": row.user_list.type.name.replace("_", " ").title(),
                "campaign_badge": "badge-accent",
                "campaign_link": campaign_link,
                "image_url": image_url,
            })
    

    except Exception as e:
        print("Google Ads Error:", e)

        return render(
            request,
            "home.html",
            {
                "campaigns": [],
                "audiences": [],
                "error": str(e)
            }
        )

    return render(
        request,
        "home.html",
        {
            "campaigns": campaigns,
            "audiences": audiences,
        }
    )

import json
def dashboard(request):    
    return render(request, 'dashboard.html')

from django.shortcuts import render, redirect
from google.ads.googleads.client import GoogleAdsClient


# def campaign(request):
#     campaign_id = request.GET.get("campaign_id")
#     # campaign_id = "23277124054"

#     if not campaign_id:
#         return redirect("home")

#     creds_data = request.session.get("credentials")

#     if not creds_data:
#         return redirect("login")

#     try:
#         client = GoogleAdsClient.load_from_dict({
#             "developer_token": DEVELOPER_TOKEN,
#             "client_id": creds_data["client_id"],
#             "client_secret": creds_data["client_secret"],
#             "refresh_token": creds_data["refresh_token"],
#             "use_proto_plus": True,
#         })

#         customer_service = client.get_service("CustomerService")
#         response = customer_service.list_accessible_customers()

#         customer_id = response.resource_names[0].split("/")[-1]

#         ga_service = client.get_service("GoogleAdsService")

#         query = f"""
#             SELECT
#                 campaign.id,
#                 campaign.name,
#                 campaign.status,
#                 campaign.advertising_channel_type,
#                 asset.image_asset.full_size.url
#             FROM asset_group_asset
#             WHERE campaign.id = {campaign_id}
#         """

#         ads_response = ga_service.search(
#             customer_id=customer_id,
#             query=query
#         )

#         campaign_data = None
#         images = []

#         for row in ads_response:

#             if campaign_data is None:
#                 campaign_data = {
#                     "id": row.campaign.id,
#                     "name": row.campaign.name,
#                     "status": row.campaign.status.name,
#                     "type": row.campaign.advertising_channel_type.name,
#                 }

#             image_url = row.asset.image_asset.full_size.url

#             if image_url and image_url not in images:
#                 images.append(image_url)

#         return render(
#             request,
#             "campaign.html",
#             {
#                 "campaign": campaign_data,
#                 "images": images,
#             }
#         )

#     except Exception as e:
#         return render(
#             request,
#             "campaign.html",
#             {
#                 "error": str(e)
#             }
#         )

import json
from django.db import connection
from django.shortcuts import render

import json
from django.db import connection
from django.shortcuts import render

def campaign(request):
    email = request.user.email
    audience_id = request.GET.get("audience_id")

    audience_characteristics = []
    creative_overview = ""

    if audience_id:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT creatives
                FROM audience_creative_data
                WHERE email = %s
                  AND audience_id = %s
                LIMIT 1
            """, [email, audience_id])

            row = cursor.fetchone()

        if row:
            creative_json = row[0]

            # If stored as TEXT
            if isinstance(creative_json, str):
                creative_json = json.loads(creative_json)

            recommendations = creative_json.get("recommendations", {})

            creative_overview = recommendations.get("creative_overview", "")
            audience_characteristics = recommendations.get(
                "audienceCharacteristics", []
            )

    return render(
        request,
        "campaign.html",
        {
            "creative_overview": creative_overview,
            "audience_characteristics": audience_characteristics,
            "audience_id": audience_id,
        },
    )

def onboarding(request):    
    return render(request, 'onboarding.html')


import json
import re
from django.http import JsonResponse
from django.views.decorators.http import require_POST

def to_camel_case(text):
    words = re.split(r'[\s_-]+', text.strip())
    return ''.join(word.capitalize() for word in words if word)

@require_POST
def save_onboarding(request):
    data = json.loads(request.body)

    OnboardingProfile.objects.create(
        user=request.user if request.user.is_authenticated else None,
        ga4_property_id=data.get('ga4id'),
        gads_customer_id=data.get('gadsid'),
        ga4_measurement_id=data.get('measurementid'),
        mp_api_secret=data.get('mpsecret'),
        business=data.get('business'),
        business_parameter=to_camel_case(data.get('businessParameter', '')),
        notif_email=data.get('notifEmail'),
    )

    return JsonResponse({'status': 'ok'})



from collections import defaultdict, Counter
import json


import json
from django.db import connection
from django.shortcuts import render

def select_creative(request):
    email = request.user.email
    print(email)

    creative_data = []

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT creative_links
            FROM email_creative_links
            WHERE email = %s
        """, [email])

        row = cursor.fetchone()

    if row:
        links = row[0]

        # If creative_links is stored as text
        if isinstance(links, str):
            links = json.loads(links)

        for creative_id, value in links.items():
            # print(creative_id)
            creative_data.append({
                "creative_id": creative_id,
                "ad_id": value.get("ad_id"),
                "primary_image": value.get("primary_image"),
            })

    return render(
        request,
        "select-creative.html",
        {
            "creative_data": creative_data,
        },
    )

from google.ads.googleads.client import GoogleAdsClient
from django.shortcuts import render
import json


# def select_creative(request):
#     creatives = []

#     creds_data = request.session.get("credentials")

#     if not creds_data:
#         return render(request, "home.html", {"creatives": []})

#     try:
#         client = GoogleAdsClient.load_from_dict({
#             "developer_token": DEVELOPER_TOKEN,
#             "client_id": creds_data["client_id"],
#             "client_secret": creds_data["client_secret"],
#             "refresh_token": creds_data["refresh_token"],
#             "use_proto_plus": True,
#         })

#         customer_service = client.get_service("CustomerService")
#         response = customer_service.list_accessible_customers()

#         accounts = [
#             resource_name.split("/")[-1]
#             for resource_name in response.resource_names
#         ]

#         if not accounts:
#             return render(
#                 request,
#                 "home.html",
#                 {
#                     "creatives": [],
#                     "error": "No Google Ads accounts found."
#                 }
#             )

#         customer_id = accounts[0]

#         ga_service = client.get_service("GoogleAdsService")

#         query = """
#             SELECT
#                 asset.id,
#                 asset.name,
#                 asset.type,
#                 asset.image_asset.full_size.url
#             FROM asset
#             WHERE asset.image_asset.full_size.url IS NOT NULL
#         """

#         response = ga_service.search(
#             customer_id=customer_id,
#             query=query
#         )

#         seen_assets = set()

#         for row in response:

#             asset_id = str(row.asset.id)

#             if asset_id in seen_assets:
#                 continue

#             seen_assets.add(asset_id)

#             creatives.append({
#                 "asset_id": asset_id,
#                 "asset_name": row.asset.name or f"Creative {asset_id}",
#                 "asset_type": row.asset.type_.name,
#                 "image_url": row.asset.image_asset.full_size.url,
#             })

#     except Exception as e:
#         print("Google Ads Error:", e)

#         return render(
#             request,
#             "select-creative.html",
#             {
#                 "creatives": [],
#                 "error": str(e)
#             }
#         )

#     return render(
#         request,
#         "select-creative.html",
#         {
#             "creatives": creatives,
#             "creatives_json": json.dumps(creatives)
#         }
#     )

def google_login(request):
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRET_FILE,
        scopes=SCOPES,
        redirect_uri="http://127.0.0.1:8000/oauth2callback/"
    )

    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent"
    )

    request.session["state"] = state

    if getattr(flow, "code_verifier", None):
        request.session["code_verifier"] = flow.code_verifier

    return redirect(authorization_url)


def oauth2callback(request):
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRET_FILE,
        scopes=SCOPES,
        state=request.session.get("state"),
        redirect_uri="http://127.0.0.1:8000/oauth2callback/"
    )

    if request.session.get("code_verifier"):
        flow.code_verifier = request.session["code_verifier"]

    flow.fetch_token(
        authorization_response=request.build_absolute_uri()
    )

    credentials = flow.credentials

    # Save credentials in session
    request.session["credentials"] = credentials_to_dict(credentials)

    # Get Google user information
    oauth2 = build("oauth2", "v2", credentials=credentials)
    user_info = oauth2.userinfo().get().execute()

    print(user_info)

    email = user_info["email"]

    # Create or get Django user
    user, created = User.objects.get_or_create(
        username=email,
        defaults={
            "email": email,
            "first_name": user_info.get("given_name", ""),
            "last_name": user_info.get("family_name", ""),
        }
    )

    # Update email if existing user
    user.email = email
    user.first_name = user_info.get("given_name", "")
    user.last_name = user_info.get("family_name", "")
    user.save()

    # Login user
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")

    # Save OAuth credentials
    OAuthCredential.objects.update_or_create(
        user=user,
        defaults={
            "google_user_id": user_info["id"],
            "email": user_info["email"],  # Add this
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
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        if not username or not password:
            return render(request, 'login.html', {
                'error': 'Please enter both username and password'
            })

        user = authenticate(request, username=username, password=password)

        if user:
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            return redirect('home')  # use URL name instead of render
        else:
            return render(request, 'login.html', {
                'error': 'Invalid username or password'
            })

    return render(request, 'login.html')