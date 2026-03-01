#!/bin/sh
set -eu

KCADM=/opt/keycloak/bin/kcadm.sh

KEYCLOAK_BASE_URL="${KEYCLOAK_BASE_URL:-http://keycloak:8080}"
echo "Using KEYCLOAK_BASE_URL=${KEYCLOAK_BASE_URL}"
KEYCLOAK_REALM="${KEYCLOAK_REALM:-reports-realm}"
echo "Using KEYCLOAK_REALM=${KEYCLOAK_REALM}"
KEYCLOAK_ADMIN="${KEYCLOAK_ADMIN:-admin}"
KEYCLOAK_ADMIN_PASSWORD="${KEYCLOAK_ADMIN_PASSWORD:-admin}"

YANDEX_IDP_ALIAS="${YANDEX_IDP_ALIAS:-yandex}"
YANDEX_CLIENT_ID="${YANDEX_CLIENT_ID:?YANDEX_CLIENT_ID is required}"
YANDEX_CLIENT_SECRET="${YANDEX_CLIENT_SECRET:?YANDEX_CLIENT_SECRET is required}"

YANDEX_OIDC_ISSUER="${YANDEX_OIDC_ISSUER:?YANDEX_OIDC_ISSUER is required}"
YANDEX_OIDC_AUTH_URL="${YANDEX_OIDC_AUTH_URL:?YANDEX_OIDC_AUTH_URL is required}"
YANDEX_OIDC_TOKEN_URL="${YANDEX_OIDC_TOKEN_URL:?YANDEX_OIDC_TOKEN_URL is required}"
YANDEX_OIDC_USERINFO_URL="${YANDEX_OIDC_USERINFO_URL:?YANDEX_OIDC_USERINFO_URL is required}"
YANDEX_OIDC_JWKS_URL="${YANDEX_OIDC_JWKS_URL:?YANDEX_OIDC_JWKS_URL is required}"

wait_for_keycloak() {
  echo "Waiting for Keycloak..."
  until $KCADM config credentials \
    --server "$KEYCLOAK_BASE_URL" \
    --realm master \
    --user "$KEYCLOAK_ADMIN" \
    --password "$KEYCLOAK_ADMIN_PASSWORD" >/dev/null 2>&1; do
    sleep 2
  done
  echo "Authenticated in Keycloak admin CLI"
}

extract_id_by_name() {
  target_name="$1"
  sed 's/},{/}\n{/g' | grep "\"name\" : \"$target_name\"" | sed -n 's/.*"id" : "\([^"]*\)".*/\1/p' | head -n 1
}

extract_client_id() {
  sed -n 's/.*"id" : "\([^"]*\)".*/\1/p' | head -n 1
}

ensure_idp_mapper() {
  mapper_name="$1"
  claim_name="$2"
  user_attr="$3"

  existing_id="$(
    $KCADM get "identity-provider/instances/${YANDEX_IDP_ALIAS}/mappers" -r "$KEYCLOAK_REALM" 2>/dev/null \
      | tr -d '\n' \
      | extract_id_by_name "$mapper_name" || true
  )"

  if [ -n "${existing_id:-}" ]; then
    $KCADM update "identity-provider/instances/${YANDEX_IDP_ALIAS}/mappers/${existing_id}" -r "$KEYCLOAK_REALM" \
      -s "name=${mapper_name}" \
      -s "identityProviderAlias=${YANDEX_IDP_ALIAS}" \
      -s "identityProviderMapper=oidc-user-attribute-idp-mapper" \
      -s 'config."syncMode"=INHERIT' \
      -s 'config."claim"='"${claim_name}" \
      -s 'config."user.attribute"='"${user_attr}"
  else
    $KCADM create "identity-provider/instances/${YANDEX_IDP_ALIAS}/mappers" -r "$KEYCLOAK_REALM" \
      -s "name=${mapper_name}" \
      -s "identityProviderAlias=${YANDEX_IDP_ALIAS}" \
      -s "identityProviderMapper=oidc-user-attribute-idp-mapper" \
      -s 'config."syncMode"=INHERIT' \
      -s 'config."claim"='"${claim_name}" \
      -s 'config."user.attribute"='"${user_attr}"
  fi
}

ensure_client_attr_mapper() {
  client_uuid="$1"
  mapper_name="$2"
  user_attr="$3"
  claim_name="$4"

  existing_id="$(
    $KCADM get "clients/${client_uuid}/protocol-mappers/models" -r "$KEYCLOAK_REALM" 2>/dev/null \
      | tr -d '\n' \
      | extract_id_by_name "$mapper_name" || true
  )"

  if [ -n "${existing_id:-}" ]; then
    $KCADM update "clients/${client_uuid}/protocol-mappers/models/${existing_id}" -r "$KEYCLOAK_REALM" \
      -s "name=${mapper_name}" \
      -s "protocol=openid-connect" \
      -s "protocolMapper=oidc-usermodel-attribute-mapper" \
      -s 'config."user.attribute"='"${user_attr}" \
      -s 'config."claim.name"='"${claim_name}" \
      -s 'config."jsonType.label"=String' \
      -s 'config."id.token.claim"=true' \
      -s 'config."access.token.claim"=true' \
      -s 'config."userinfo.token.claim"=true'
  else
    $KCADM create "clients/${client_uuid}/protocol-mappers/models" -r "$KEYCLOAK_REALM" \
      -s "name=${mapper_name}" \
      -s "protocol=openid-connect" \
      -s "protocolMapper=oidc-usermodel-attribute-mapper" \
      -s 'config."user.attribute"='"${user_attr}" \
      -s 'config."claim.name"='"${claim_name}" \
      -s 'config."jsonType.label"=String' \
      -s 'config."id.token.claim"=true' \
      -s 'config."access.token.claim"=true' \
      -s 'config."userinfo.token.claim"=true' >/dev/null
  fi
}

wait_for_keycloak

echo "Configuring Yandex IdP..."

if $KCADM get "identity-provider/instances/${YANDEX_IDP_ALIAS}" -r "$KEYCLOAK_REALM" >/dev/null 2>&1; then
  $KCADM update "identity-provider/instances/${YANDEX_IDP_ALIAS}" -r "$KEYCLOAK_REALM" \
    -s "alias=${YANDEX_IDP_ALIAS}" \
    -s "providerId=oidc" \
    -s "enabled=true" \
    -s "trustEmail=true" \
    -s "storeToken=true" \
    -s "firstBrokerLoginFlowAlias=first broker login" \
    -s "config.authorizationUrl=${YANDEX_OIDC_AUTH_URL}" \
    -s "config.tokenUrl=${YANDEX_OIDC_TOKEN_URL}" \
    -s "config.userInfoUrl=${YANDEX_OIDC_USERINFO_URL}" \
    -s "config.jwksUrl=${YANDEX_OIDC_JWKS_URL}" \
    -s "config.issuer=${YANDEX_OIDC_ISSUER}" \
    -s "config.clientId=${YANDEX_CLIENT_ID}" \
    -s "config.clientSecret=${YANDEX_CLIENT_SECRET}" \
    -s "config.disableUserInfo=false" \
    -s "config.syncMode=IMPORT" \
    -s "config.useJwksUrl=true" \
    -s "config.validateSignature=true" \
    -s "config.defaultScope=openid email profile"
else
  $KCADM create identity-provider/instances -r "$KEYCLOAK_REALM" \
    -s "alias=${YANDEX_IDP_ALIAS}" \
    -s "providerId=oidc" \
    -s "enabled=true" \
    -s "trustEmail=true" \
    -s "storeToken=true" \
    -s "firstBrokerLoginFlowAlias=first broker login" \
    -s "config.authorizationUrl=${YANDEX_OIDC_AUTH_URL}" \
    -s "config.tokenUrl=${YANDEX_OIDC_TOKEN_URL}" \
    -s "config.userInfoUrl=${YANDEX_OIDC_USERINFO_URL}" \
    -s "config.jwksUrl=${YANDEX_OIDC_JWKS_URL}" \
    -s "config.issuer=${YANDEX_OIDC_ISSUER}" \
    -s "config.clientId=${YANDEX_CLIENT_ID}" \
    -s "config.clientSecret=${YANDEX_CLIENT_SECRET}" \
    -s "config.disableUserInfo=false" \
    -s "config.syncMode=IMPORT" \
    -s "config.useJwksUrl=true" \
    -s "config.validateSignature=true" \
    -s "config.defaultScope=openid email profile" >/dev/null
fi

# Yandex Identity Hub is a standard OIDC provider.
# Claims returned with "openid email profile" scope:
#   sub               – Yandex numeric user ID (replaces the old "id" field)
#   preferred_username – Yandex login (replaces the old "login" field)
#   email             – primary email (replaces the old "default_email" field)
#   name              – display name (replaces the old "display_name" / "real_name")
#   picture           – avatar URL (replaces the old "default_avatar_id")
echo "Creating IdP mappers..."
ensure_idp_mapper "yandex-sub" "sub" "yandex_sub"
ensure_idp_mapper "yandex-email" "email" "yandex_email"
ensure_idp_mapper "yandex-preferred-username" "preferred_username" "yandex_preferred_username"
ensure_idp_mapper "yandex-name" "name" "yandex_name"
ensure_idp_mapper "yandex-given-name" "given_name" "yandex_given_name"
ensure_idp_mapper "yandex-family-name" "family_name" "yandex_family_name"
ensure_idp_mapper "yandex-picture" "picture" "yandex_picture"

echo "Finding bionicpro-auth client..."
CLIENT_UUID="$(
  $KCADM get clients -r "$KEYCLOAK_REALM" -q clientId=bionicpro-auth --fields id,clientId \
    | extract_client_id
)"

if [ -z "${CLIENT_UUID:-}" ]; then
  echo "bionicpro-auth client not found"
  exit 1
fi

echo "Creating client protocol mappers..."
ensure_client_attr_mapper "$CLIENT_UUID" "yandex-sub-claim" "yandex_sub" "yandex_sub"
ensure_client_attr_mapper "$CLIENT_UUID" "yandex-email-claim" "yandex_email" "yandex_email"
ensure_client_attr_mapper "$CLIENT_UUID" "yandex-preferred-username-claim" "yandex_preferred_username" "yandex_preferred_username"
ensure_client_attr_mapper "$CLIENT_UUID" "yandex-name-claim" "yandex_name" "yandex_name"
ensure_client_attr_mapper "$CLIENT_UUID" "yandex-given-name-claim" "yandex_given_name" "yandex_given_name"
ensure_client_attr_mapper "$CLIENT_UUID" "yandex-family-name-claim" "yandex_family_name" "yandex_family_name"
ensure_client_attr_mapper "$CLIENT_UUID" "yandex-picture-claim" "yandex_picture" "yandex_picture"

echo "Yandex IdP configured successfully"