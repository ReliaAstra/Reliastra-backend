SEED_VENDORS: list[dict[str, str]] = [
    {
        "vendor_name": "stripe",
        "display_name": "Stripe",
        "endpoint_url": "https://status.stripe.com",
        "category": "payments",
    },
    {
        "vendor_name": "auth0",
        "display_name": "Auth0",
        "endpoint_url": "https://status.auth0.com",
        "category": "auth",
    },
    {
        "vendor_name": "cloudflare",
        "display_name": "Cloudflare",
        "endpoint_url": "https://www.cloudflarestatus.com",
        "category": "cdn",
    },
    {
        "vendor_name": "openai",
        "display_name": "OpenAI",
        "endpoint_url": "https://status.openai.com",
        "category": "ai",
    },
    {
        "vendor_name": "twilio",
        "display_name": "Twilio",
        "endpoint_url": "https://status.twilio.com",
        "category": "communications",
    },
]
