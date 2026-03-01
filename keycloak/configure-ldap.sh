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

EXISTING_PROVIDER_ID=$(
  /opt/keycloak/bin/kcadm.sh get components -r "$REALM_NAME" \
  --query name=bionicpro-ldap --query type=org.keycloak.storage.UserStorageProvider \
  | sed -n 's/.*"id" : "\(.*\)".*/\1/p' \
  | head -1 || true
)

if [ -n "${EXISTING_PROVIDER_ID}" ]; then
  echo "LDAP provider already exists: ${EXISTING_PROVIDER_ID}"
  exit 0
fi

echo "Creating LDAP user federation provider..."

LDAP_PROVIDER_ID=$(
  /opt/keycloak/bin/kcadm.sh create components -r "$REALM_NAME" \
    -s name=bionicpro-ldap \
    -s providerId=ldap \
    -s providerType=org.keycloak.storage.UserStorageProvider \
    -s parentId="$REALM_ID" \
    -s 'config.priority=["0"]' \
    -s 'config.enabled=["true"]' \
    -s 'config.editMode=["READ_ONLY"]' \
    -s 'config.vendor=["other"]' \
    -s 'config.usernameLDAPAttribute=["uid"]' \
    -s 'config.rdnLDAPAttribute=["uid"]' \
    -s 'config.uuidLDAPAttribute=["entryUUID"]' \
    -s 'config.userObjectClasses=["inetOrgPerson"]' \
    -s 'config.connectionUrl=["ldap://ldap:389"]' \
    -s 'config.usersDn=["ou=People,dc=example,dc=com"]' \
    -s 'config.authType=["simple"]' \
    -s 'config.bindDn=["cn=admin,dc=example,dc=com"]' \
    -s 'config.bindCredential=["admin"]' \
    -s 'config.searchScope=["1"]' \
    -s 'config.importEnabled=["true"]' \
    -s 'config.syncRegistrations=["false"]' \
    -s 'config.trustEmail=["true"]' \
    -s 'config.fullSyncPeriod=["-1"]' \
    -s 'config.changedSyncPeriod=["-1"]' \
    -i
)

echo "LDAP provider created: ${LDAP_PROVIDER_ID}"

echo "Creating username mapper..."
/opt/keycloak/bin/kcadm.sh create components -r "$REALM_NAME" \
  -s name=username-mapper \
  -s providerId=user-attribute-ldap-mapper \
  -s providerType=org.keycloak.storage.ldap.mappers.LDAPStorageMapper \
  -s parentId="$LDAP_PROVIDER_ID" \
  -s 'config."ldap.attribute"=["uid"]' \
  -s 'config."user.model.attribute"=["username"]' \
  -s 'config."is.mandatory.in.ldap"=["true"]' \
  -s 'config."always.read.value.from.ldap"=["true"]' \
  -s 'config."read.only"=["true"]'

echo "Creating email mapper..."
/opt/keycloak/bin/kcadm.sh create components -r "$REALM_NAME" \
  -s name=email-mapper \
  -s providerId=user-attribute-ldap-mapper \
  -s providerType=org.keycloak.storage.ldap.mappers.LDAPStorageMapper \
  -s parentId="$LDAP_PROVIDER_ID" \
  -s 'config."ldap.attribute"=["mail"]' \
  -s 'config."user.model.attribute"=["email"]' \
  -s 'config."is.mandatory.in.ldap"=["false"]' \
  -s 'config."always.read.value.from.ldap"=["true"]' \
  -s 'config."read.only"=["true"]'

echo "Creating full-name mapper..."
/opt/keycloak/bin/kcadm.sh create components -r "$REALM_NAME" \
  -s name=full-name-mapper \
  -s providerId=full-name-ldap-mapper \
  -s providerType=org.keycloak.storage.ldap.mappers.LDAPStorageMapper \
  -s parentId="$LDAP_PROVIDER_ID" \
  -s 'config."ldap.full.name.attribute"=["cn"]' \
  -s 'config."read.only"=["true"]' \
  -s 'config."write.only"=["false"]'

echo "Creating role mapper..."
/opt/keycloak/bin/kcadm.sh create components -r "$REALM_NAME" \
  -s name=ldap-role-mapper \
  -s providerId=role-ldap-mapper \
  -s providerType=org.keycloak.storage.ldap.mappers.LDAPStorageMapper \
  -s parentId="$LDAP_PROVIDER_ID" \
  -s 'config."roles.dn"=["ou=Groups,dc=example,dc=com"]' \
  -s 'config."role.name.ldap.attribute"=["cn"]' \
  -s 'config."role.object.classes"=["groupOfNames"]' \
  -s 'config."membership.ldap.attribute"=["member"]' \
  -s 'config."membership.attribute.type"=["DN"]' \
  -s 'config."membership.user.ldap.attribute"=["dn"]' \
  -s 'config."mode"=["READ_ONLY"]' \
  -s 'config."use.realm.roles.mapping"=["true"]'

echo "Triggering full LDAP sync..."
/opt/keycloak/bin/kcadm.sh create "user-storage/${LDAP_PROVIDER_ID}/sync?action=triggerFullSync" -r "$REALM_NAME"

echo "LDAP federation configured successfully"