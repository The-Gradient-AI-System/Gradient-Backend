from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/spreadsheets"
]

flow = InstalledAppFlow.from_client_secrets_file(
    "credentials.json",
    SCOPES
)

creds = flow.run_local_server(port=0)

with open("token.json", "w") as f:
    f.write(creds.to_json())

print("✅ token.json created")
