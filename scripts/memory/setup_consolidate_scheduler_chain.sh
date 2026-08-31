#!/usr/bin/env bash
# Multi-offset consolidate scheduler chain (GCP free-tier friendly).
#
# Why a chain?
#   consolidate promotes Muninn → MemU in batches. A single Cloud Function
#   invocation may finish only part of the candidate list (batch size + embed
#   latency). Chain = staggered HTTP jobs that page through offsets, plus a
#   primary auto_page job that tries to finish most work in one shot.
#
# Jobs created (us-central1):
#   daily-muninn-to-memu          03:00 UTC  auto_page=true  (primary)
#   daily-muninn-to-memu-p2       03:10 UTC  offset=12
#   daily-muninn-to-memu-p3       03:20 UTC  offset=24
#   daily-muninn-to-memu-p4       03:30 UTC  offset=36
#
# Safe if earlier page already finished (empty batch → no_action / success).
set -euo pipefail

PROJECT="${GCP_PROJECT:-arca-471022}"
REGION="${GCP_REGION:-us-central1}"
GW="${GCP_GATEWAY_URL:-https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator}"
export PATH="${HOME}/google-cloud-sdk/bin:${PATH}"

create_or_update() {
  local name="$1"
  local schedule="$2"
  local body="$3"
  if gcloud scheduler jobs describe "$name" --location="$REGION" --project="$PROJECT" >/dev/null 2>&1; then
    echo "Updating $name …"
    # update.http does not accept --headers; use --update-headers
    gcloud scheduler jobs update http "$name" \
      --location="$REGION" --project="$PROJECT" \
      --schedule="$schedule" --time-zone="Etc/UTC" \
      --uri="$GW" --http-method=POST \
      --update-headers="Content-Type=application/json" \
      --message-body="$body" \
      --attempt-deadline=320s \
      --quiet
  else
    echo "Creating $name …"
    gcloud scheduler jobs create http "$name" \
      --location="$REGION" --project="$PROJECT" \
      --schedule="$schedule" --time-zone="Etc/UTC" \
      --uri="$GW" --http-method=POST \
      --headers="Content-Type=application/json" \
      --message-body="$body" \
      --attempt-deadline=320s \
      --quiet
  fi
}

# Primary: auto_page walks offsets until done / time budget / max_batches
create_or_update "daily-muninn-to-memu" "0 3 * * *" \
  '{"operation":"consolidate","threshold":0.5,"batch":12,"offset":0,"auto_page":true,"max_batches":8,"time_budget_s":240}'

# Fallback pages (if auto_page stopped early under load)
create_or_update "daily-muninn-to-memu-p2" "10 3 * * *" \
  '{"operation":"consolidate","threshold":0.5,"batch":12,"offset":12,"auto_page":true,"max_batches":4,"time_budget_s":240}'

create_or_update "daily-muninn-to-memu-p3" "20 3 * * *" \
  '{"operation":"consolidate","threshold":0.5,"batch":12,"offset":24,"auto_page":true,"max_batches":4,"time_budget_s":240}'

create_or_update "daily-muninn-to-memu-p4" "30 3 * * *" \
  '{"operation":"consolidate","threshold":0.5,"batch":12,"offset":36,"auto_page":true,"max_batches":4,"time_budget_s":240}'

echo ""
echo "Scheduler chain ready:"
gcloud scheduler jobs list --location="$REGION" --project="$PROJECT" \
  --filter="name~daily-muninn-to-memu" \
  --format="table(name,schedule,state)"
echo ""
echo "Manual test:"
echo "  curl -X POST $GW -H 'Content-Type: application/json' \\"
echo "    -d '{\"operation\":\"consolidate\",\"auto_page\":true,\"batch\":5}'"
