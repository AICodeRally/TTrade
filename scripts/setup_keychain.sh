#!/bin/bash
# Store TTrade secrets in macOS Keychain
set -euo pipefail
echo "TTrade Keychain Setup"
echo "===================="
read -s -p "Enter Public.com API key: " PUBLIC_KEY
echo
security add-generic-password -a "$USER" -s "ttrade-PUBLIC_API_KEY" -w "$PUBLIC_KEY" 2>/dev/null \
  || security delete-generic-password -s "ttrade-PUBLIC_API_KEY" 2>/dev/null \
  && security add-generic-password -a "$USER" -s "ttrade-PUBLIC_API_KEY" -w "$PUBLIC_KEY"
echo "  Stored: ttrade-PUBLIC_API_KEY"
read -s -p "Enter Gmail app password: " GMAIL_PW
echo
security add-generic-password -a "$USER" -s "ttrade-GMAIL_APP_PASSWORD" -w "$GMAIL_PW" 2>/dev/null \
  || security delete-generic-password -s "ttrade-GMAIL_APP_PASSWORD" 2>/dev/null \
  && security add-generic-password -a "$USER" -s "ttrade-GMAIL_APP_PASSWORD" -w "$GMAIL_PW"
echo "  Stored: ttrade-GMAIL_APP_PASSWORD"
echo ""
echo "Done! Verify with:"
echo "  security find-generic-password -s ttrade-PUBLIC_API_KEY -w"
echo "  security find-generic-password -s ttrade-GMAIL_APP_PASSWORD -w"
