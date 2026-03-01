#!/bin/sh
set -eu

KEYCLOAK_URL="http://keycloak:8080"
REALM_NAME="reports-realm"

echo "Waiting for Keycloak..."
until /opt/keycloak/bin/kcadm.sh config credentials \
  --server "$KEYCLOAK_URL" \
  --realm master \
  --user admin \
  --password admin >/dev/null 2>&1
do
  sleep 5
done

echo "Authenticated in Keycloak admin CLI"

REALM_ID=$(
  /opt/keycloak/bin/kcadm.sh get "realms/${REALM_NAME}" \
  | sed -n 's/.*"id" : "\(.*\)".*/\1/p' \
  | head -1
)

if [ -z "${REALM_ID}" ]; then
  echo "Failed to resolve realm ID for ${REALM_NAME}"
  exit 1
fi

echo "Resolved realm id: ${REALM_ID}"

echo "Configuring OTP policy..."
/opt/keycloak/bin/kcadm.sh update "realms/${REALM_NAME}" \
  -s otpPolicyType=totp \
  -s otpPolicyAlgorithm=HmacSHA1 \
  -s otpPolicyDigits=6 \
  -s otpPolicyPeriod=30 \
  -s otpPolicyLookAheadWindow=1 \
  -s otpPolicyCodeReusable=false

echo "Enabling required action CONFIGURE_TOTP..."
/opt/keycloak/bin/kcadm.sh update "authentication/required-actions/CONFIGURE_TOTP" -r "$REALM_NAME" \
  -s enabled=true \
  -s defaultAction=true \
  -s priority=10

echo "Assigning CONFIGURE_TOTP to all current users in realm..."
USER_IDS=$(/opt/keycloak/bin/kcadm.sh get users -r "$REALM_NAME" | sed -n 's/.*"id" : "\(.*\)".*/\1/p')

for USER_ID in $USER_IDS; do
  /opt/keycloak/bin/kcadm.sh update "users/${USER_ID}" -r "$REALM_NAME" \
    -s 'requiredActions=["CONFIGURE_TOTP"]'
done

echo "MFA configuration completed successfully"