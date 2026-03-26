# Production environment variables
# Contact: contact@etherionai.com

billing_account_id = "01979A-3429E4-56DDB0 "
alert_email        = "contact@etherionai.com"

# Database Configuration (Cost Optimization)
database_availability_type = "ZONAL" # Disable HA to save costs (approx $100/mo savings)

# Optional guardrails tuning (kept at safe defaults)
# cost_threshold_usd = 100.0
# kill_switch_enabled = false

# Spend-guard (optional: uncomment and set when image is available)
# spend_guard_image_url        = "us-central1-docker.pkg.dev/<PROJECT_ID>/etherion/spend-guard:1"
# spend_guard_threshold_usd    = 100.0
# spend_guard_lookback_hours   = 24
# spend_guard_schedule_cron    = "*/15 * * * *"
# spend_guard_schedule_time_zone = "UTC"
