#!/usr/bin/env bash
# Safely retry bot pushes when main advances. Never force-push user changes.
set -euo pipefail
for attempt in 1 2 3; do
  if git push origin HEAD:main; then
    echo "Bot commit pushed (attempt $attempt)."
    exit 0
  fi
  echo "::warning::Main branch moved; attempting safe rebase ($attempt/3)."
  git fetch origin main
  if ! git rebase origin/main; then
    git rebase --abort || true
    echo "::error::Conflicting repository updates; refusing to overwrite user changes."
    exit 1
  fi
  sleep $((attempt * 2))
done
echo "::error::Bot commit push failed after three retries."
exit 1
