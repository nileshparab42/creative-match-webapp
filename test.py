import json
import psycopg2
from psycopg2.extras import Json

# Connect to Cloud SQL PostgreSQL
conn = psycopg2.connect(
    dbname="ga4_creds_db",
    user="postgres",
    password="2CMji&vnX+c&sEdz",
    host="34.14.171.35",
    port="5432"
)

cursor = conn.cursor()

# Sample JSON
creative_json = {
    "model_version": "v1",
    "generated_at": "2026-07-24T10:30:00Z",
    "recommendations": [
        {
            "creative_id": "CR001",
            "rank": 1,
            "creative_profile": {
                "programme": "Online MBA",
                "tagline": "AN MBA THAT WORKS AROUND YOUR CAREER",
                "colour": "Blue",
                "format": "Display Ad",
                "cta": "Admissions Open For July 2026 Intake",
                "cta_position": "bottom",
                "feature": "Online MBA",
                "asset_type": "Image",
                "audio_type": "Others",
                "face_count": 1,
                "word_count": 46
            },
            "audience_drivers": [
                {
                    "feature": "Region",
                    "value": "Gujarat",
                    "shap": -0.0211
                }
            ],
            "creative_drivers": [
                {
                    "attribute": "Tagline",
                    "value": "AN MBA THAT WORKS AROUND YOUR CAREER",
                    "shap": 0.0907
                }
            ]
        }
    ]
}

# Insert one row
cursor.execute("""
INSERT INTO audience_creative_data
(email, audience_id, creatives)
VALUES (%s, %s, %s)
ON CONFLICT (email, audience_id)
DO UPDATE SET
    creatives = EXCLUDED.creatives,
    created_at = CURRENT_TIMESTAMP;
""", (
    "abc@gmail.com",
    "AUD001",
    Json(creative_json)
))

conn.commit()

print("Row inserted successfully!")

# Read it back
cursor.execute("""
SELECT email, audience_id, creatives
FROM audience_creative_data;
""")

rows = cursor.fetchall()

for row in rows:
    print("=" * 60)
    print("Email:", row[0])
    print("Audience ID:", row[1])
    print(json.dumps(row[2], indent=4))

cursor.close()
conn.close()

print("Done!")


import psycopg2

conn = psycopg2.connect(
    dbname="ga4_creds_db",
    user="postgres",
    password="2CMji&vnX+c&sEdz",
    host="34.14.171.35",
    port="5432"
)

cursor = conn.cursor()

# Create table
cursor.execute("""
CREATE TABLE IF NOT EXISTS email_creative_links (
    email VARCHAR(255) PRIMARY KEY,
    creative_links JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
""")



cursor.execute("""
INSERT INTO email_creative_links(email, creative_links)
VALUES (%s, %s)
ON CONFLICT (email)
DO UPDATE SET
    creative_links = EXCLUDED.creative_links,
    updated_at = CURRENT_TIMESTAMP;
""", ("abc@gmail.com", links))

conn.commit()

print("Inserted successfully!")

cursor.execute("""
SELECT email, creative_links
FROM email_creative_links;
""")

for email, creative_links in cursor.fetchall():
    print(email)
    print(creative_links)

cursor.close()
conn.close()