// PSA on Azure: Container Apps (api, worker, proxy + migrate job), PostgreSQL Flexible Server
// (private access), Azure Files for attachments, ACR, Log Analytics and Key Vault. Every secret
// reaches the containers as a Container Apps Key Vault reference (keyVaultUrl + identity), so no
// secret value appears in this template, its parameters or the deployment history.
// Driven by deploy.sh, which creates the vault and the registry first; see docs/AZURE_DEPLOY.md.

@description('Short lowercase prefix for resource names, e.g. "psa".')
@minLength(2)
@maxLength(12)
param namePrefix string

@description('Six-character suffix that makes global names unique (deploy.sh derives it).')
@minLength(6)
@maxLength(6)
param suffix string

param location string = resourceGroup().location

@description('Public host name staff and clients use, e.g. psa.example.com.')
param publicHost string

@description('Image tag built by deploy.sh (az acr build).')
param imageTag string

param entraTenantId string
param entraClientId string

@description('PostgreSQL administrator (owner, runs migrations) password. Pass a Key Vault reference; never a literal.')
@secure()
param postgresAdminPassword string

@description('Id of the managed certificate for publicHost once bound (deploy.sh looks it up); empty before that.')
param customDomainCertificateId string = ''

@description('First admin inserted by the migrate job (empty skips it).')
param bootstrapAdminEmail string = ''

@description('false deploys everything except api, worker and proxy, so deploy.sh can run migrations before new app code rolls out.')
param deployApps bool = true

@description('Point-in-time-restore window for PostgreSQL, in days (7-35).')
@minValue(7)
@maxValue(35)
param postgresBackupRetentionDays int = 14

var compactPrefix = replace(namePrefix, '-', '')
var vaultName = '${namePrefix}-kv-${suffix}'
var acrName = '${compactPrefix}acr${suffix}'
var storageName = '${compactPrefix}st${suffix}'
var pgName = '${namePrefix}-pg-${suffix}'
var pgAdminUser = 'psa_owner'
var shareName = 'attachments'
var attachmentsDir = '/data/attachments'
var vaultSecretsBase = '${keyVault.properties.vaultUri}secrets/'

// Built-in role definition ids
var roleKeyVaultSecretsUser = '4633458b-17de-408a-b874-0445c86b69e6'
var roleKeyVaultSecretsOfficer = 'b86a8fe4-44ce-4948-aee5-eccb2c155cd7'
var roleAcrPull = '7f951dda-4ed3-4680-a7ca-43fe172d538d'

// ---------------------------------------------------------------- monitoring
resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${namePrefix}-logs'
  location: location
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

// ---------------------------------------------------------------- network
resource vnet 'Microsoft.Network/virtualNetworks@2023-11-01' = {
  name: '${namePrefix}-vnet'
  location: location
  properties: {
    addressSpace: { addressPrefixes: [ '10.40.0.0/16' ] }
    subnets: [
      {
        name: 'apps'
        properties: {
          addressPrefix: '10.40.0.0/23'
          delegations: [ { name: 'apps', properties: { serviceName: 'Microsoft.App/environments' } } ]
        }
      }
      {
        name: 'postgres'
        properties: {
          addressPrefix: '10.40.2.0/24'
          delegations: [ { name: 'postgres', properties: { serviceName: 'Microsoft.DBforPostgreSQL/flexibleServers' } } ]
        }
      }
    ]
  }
}

resource pgDns 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: '${pgName}.private.postgres.database.azure.com'
  location: 'global'
}

resource pgDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: pgDns
  name: '${namePrefix}-vnet-link'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: { id: vnet.id }
  }
}

// ---------------------------------------------------------------- identity, vault, registry
resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${namePrefix}-id'
  location: location
}

// deploy.sh creates the vault with the same settings first (it must hold the generated secrets
// before this template runs); declaring it here keeps the settings enforced on every deploy.
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: vaultName
  location: location
  properties: {
    tenantId: subscription().tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
    enablePurgeProtection: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 90
    enabledForTemplateDeployment: true // lets the parameter file reference pg-admin-password
    accessPolicies: []
  }
}

resource kvSecretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: keyVault
  name: guid(keyVault.id, identity.id, roleKeyVaultSecretsUser)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleKeyVaultSecretsUser)
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// Accepted risk (security review): the onboarding wizard writes the secrets it creates.
resource kvSecretsOfficer 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: keyVault
  name: guid(keyVault.id, identity.id, roleKeyVaultSecretsOfficer)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleKeyVaultSecretsOfficer)
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  sku: { name: 'Basic' }
  properties: {
    adminUserEnabled: false
  }
}

resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: acr
  name: guid(acr.id, identity.id, roleAcrPull)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleAcrPull)
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// ---------------------------------------------------------------- PostgreSQL
resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2023-06-01-preview' = {
  name: pgName
  location: location
  sku: { name: 'Standard_B1ms', tier: 'Burstable' }
  properties: {
    version: '16'
    administratorLogin: pgAdminUser
    administratorLoginPassword: postgresAdminPassword
    authConfig: { passwordAuth: 'Enabled', activeDirectoryAuth: 'Disabled' }
    storage: { storageSizeGB: 32, autoGrow: 'Enabled' }
    backup: { backupRetentionDays: postgresBackupRetentionDays, geoRedundantBackup: 'Disabled' }
    highAvailability: { mode: 'Disabled' }
    network: {
      delegatedSubnetResourceId: vnet.properties.subnets[1].id
      privateDnsZoneArmResourceId: pgDns.id
      publicNetworkAccess: 'Disabled'
    }
  }
  dependsOn: [ pgDnsLink ]
}

resource psaDb 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2023-06-01-preview' = {
  parent: postgres
  name: 'psa'
  properties: { charset: 'UTF8', collation: 'en_US.utf8' }
}

// ---------------------------------------------------------------- attachments storage
resource storage 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: storageName
  location: location
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    supportsHttpsTrafficOnly: true
  }
}

resource fileService 'Microsoft.Storage/storageAccounts/fileServices@2023-01-01' = {
  parent: storage
  name: 'default'
  properties: {
    shareDeleteRetentionPolicy: { enabled: true, days: 14 }
  }
}

resource share 'Microsoft.Storage/storageAccounts/fileServices/shares@2023-01-01' = {
  parent: fileService
  name: shareName
  properties: { shareQuota: 100 }
}

// ---------------------------------------------------------------- Container Apps
resource env 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${namePrefix}-env'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
    vnetConfiguration: {
      infrastructureSubnetId: vnet.properties.subnets[0].id
      internal: false
    }
    workloadProfiles: [ { name: 'Consumption', workloadProfileType: 'Consumption' } ]
  }
}

resource envShare 'Microsoft.App/managedEnvironments/storages@2024-03-01' = {
  parent: env
  name: shareName
  properties: {
    azureFile: {
      accountName: storage.name
      accountKey: storage.listKeys().keys[0].value
      shareName: share.name
      accessMode: 'ReadWrite'
    }
  }
}

// Key Vault secret name -> env var. Each is a Container Apps secret with keyVaultUrl + identity.
var runtimeSecrets = [
  { name: 'database-url', env: 'DATABASE_URL' }
  { name: 'session-secret', env: 'SESSION_SECRET' }
  { name: 'credentials-key', env: 'CREDENTIALS_KEY' }
  { name: 'entra-client-secret', env: 'ENTRA_CLIENT_SECRET' }
  { name: 'portal-entra-client-id', env: 'PORTAL_ENTRA_CLIENT_ID' }
  { name: 'portal-entra-client-secret', env: 'PORTAL_ENTRA_CLIENT_SECRET' }
  { name: 'graph-tenant-id', env: 'GRAPH_TENANT_ID' }
  { name: 'graph-client-id', env: 'GRAPH_CLIENT_ID' }
  { name: 'graph-client-secret', env: 'GRAPH_CLIENT_SECRET' }
  { name: 'mail-mailbox', env: 'MAIL_MAILBOX' }
]
// The owner connection (migrations) and the app-role password only go to the migrate job.
var migrateSecrets = concat(runtimeSecrets, [
  { name: 'migration-database-url', env: 'MIGRATION_DATABASE_URL' }
  { name: 'app-db-password', env: 'APP_DB_PASSWORD' }
])

var runtimeSecretRefs = [for s in runtimeSecrets: { name: s.name, keyVaultUrl: '${vaultSecretsBase}${s.name}', identity: identity.id }]
var runtimeSecretEnv = [for s in runtimeSecrets: { name: s.env, secretRef: s.name }]
var migrateSecretRefs = [for s in migrateSecrets: { name: s.name, keyVaultUrl: '${vaultSecretsBase}${s.name}', identity: identity.id }]
var migrateSecretEnv = [for s in migrateSecrets: { name: s.env, secretRef: s.name }]

var plainEnv = [
  { name: 'ENVIRONMENT', value: 'production' }
  { name: 'PUBLIC_URL', value: 'https://${publicHost}' }
  { name: 'ENTRA_TENANT_ID', value: entraTenantId }
  { name: 'ENTRA_CLIENT_ID', value: entraClientId }
  { name: 'ATTACHMENTS_DIR', value: attachmentsDir }
  { name: 'ONBOARDING_ENABLED', value: 'true' }
  { name: 'KEY_VAULT_URL', value: keyVault.properties.vaultUri }
  { name: 'AZURE_CLIENT_ID', value: identity.properties.clientId }
  { name: 'DEV_LOGIN_ENABLED', value: 'false' }
]

var registries = [ { server: acr.properties.loginServer, identity: identity.id } ]
var userIdentity = { type: 'UserAssigned', userAssignedIdentities: { '${identity.id}': {} } }
var backendImage = '${acr.properties.loginServer}/psa-api:${imageTag}'
// The share is SMB: map ownership to the image's non-root user (uid 10001, backend/Dockerfile).
var attachmentsVolume = [ { name: 'attachments', storageType: 'AzureFile', storageName: envShare.name, mountOptions: 'uid=10001,gid=10001,dir_mode=0750,file_mode=0640' } ]
var attachmentsMount = [ { volumeName: 'attachments', mountPath: attachmentsDir } ]

resource api 'Microsoft.App/containerApps@2024-03-01' = if (deployApps) {
  name: 'api' // the proxy's Caddyfile upstream is "api"
  location: location
  identity: userIdentity
  properties: {
    environmentId: env.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      // Internal only. The proxy calls http://api (deploy.sh adapts the Caddyfile upstream).
      ingress: { external: false, targetPort: 8000, transport: 'http', allowInsecure: true }
      registries: registries
      secrets: runtimeSecretRefs
    }
    template: {
      containers: [
        {
          name: 'api'
          image: backendImage
          // Uploads go through the api, so it mounts the share read-write (compose mounts it ro).
          env: concat(plainEnv, runtimeSecretEnv)
          resources: { cpu: json('0.5'), memory: '1Gi' }
          volumeMounts: attachmentsMount
          probes: [
            { type: 'Liveness', httpGet: { path: '/healthz', port: 8000 }, periodSeconds: 30 }
            { type: 'Readiness', httpGet: { path: '/readyz', port: 8000 }, periodSeconds: 10 }
          ]
        }
      ]
      volumes: attachmentsVolume
      scale: { minReplicas: 1, maxReplicas: 3 }
    }
  }
  dependsOn: [ kvSecretsUser, acrPull, psaDb ]
}

resource worker 'Microsoft.App/containerApps@2024-03-01' = if (deployApps) {
  name: 'worker'
  location: location
  identity: userIdentity
  properties: {
    environmentId: env.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      registries: registries
      secrets: runtimeSecretRefs
    }
    template: {
      containers: [
        {
          name: 'worker'
          image: backendImage
          command: [ 'python', '-m', 'app.worker' ]
          env: concat(plainEnv, runtimeSecretEnv)
          resources: { cpu: json('0.25'), memory: '0.5Gi' }
          volumeMounts: attachmentsMount
        }
      ]
      volumes: attachmentsVolume
      scale: { minReplicas: 1, maxReplicas: 1 } // exactly one mailbox poller
    }
  }
  dependsOn: [ kvSecretsUser, acrPull, psaDb ]
}

resource proxy 'Microsoft.App/containerApps@2024-03-01' = if (deployApps) {
  name: 'proxy'
  location: location
  identity: userIdentity
  properties: {
    environmentId: env.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      // TLS terminates at the Container Apps ingress (443); Caddy serves plain HTTP behind it.
      ingress: {
        external: true
        targetPort: 80
        transport: 'auto'
        allowInsecure: false
        customDomains: empty(customDomainCertificateId) ? [] : [
          { name: publicHost, certificateId: customDomainCertificateId, bindingType: 'SniEnabled' }
        ]
      }
      registries: registries
    }
    template: {
      containers: [
        {
          name: 'proxy'
          image: '${acr.properties.loginServer}/psa-proxy:${imageTag}'
          env: [ { name: 'SITE_ADDRESS', value: ':80' } ]
          resources: { cpu: json('0.25'), memory: '0.5Gi' }
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 2 }
    }
  }
  dependsOn: [ acrPull, api ]
}

// Creates the runtime role psa_app (RLS applies to it; see deploy/postgres-init/01-roles.sh),
// runs migrations as the owner, then inserts the first admin when BOOTSTRAP_ADMIN_EMAIL is set.
var migrateScript = '''
set -e
python - <<'PY'
import os
import psycopg
from psycopg import sql
url = os.environ["MIGRATION_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
pw = sql.Literal(os.environ["APP_DB_PASSWORD"])
with psycopg.connect(url, autocommit=True) as c:
    exists = c.execute("SELECT 1 FROM pg_roles WHERE rolname = 'psa_app'").fetchone()
    stmt = "ALTER ROLE psa_app LOGIN PASSWORD {}" if exists else (
        "CREATE ROLE psa_app LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS")
    c.execute(sql.SQL(stmt).format(pw))
    c.execute("GRANT CONNECT ON DATABASE psa TO psa_app")
print("app role ready")
PY
alembic upgrade head
if [ -n "${BOOTSTRAP_ADMIN_EMAIL:-}" ]; then python -m app.bootstrap_admin; fi
'''

resource migrate 'Microsoft.App/jobs@2024-03-01' = {
  name: 'migrate'
  location: location
  identity: userIdentity
  properties: {
    environmentId: env.id
    workloadProfileName: 'Consumption'
    configuration: {
      triggerType: 'Manual'
      replicaTimeout: 1800
      replicaRetryLimit: 0
      manualTriggerConfig: { parallelism: 1, replicaCompletionCount: 1 }
      registries: registries
      secrets: migrateSecretRefs
    }
    template: {
      containers: [
        {
          name: 'migrate'
          image: backendImage
          command: [ '/bin/sh', '-c', migrateScript ]
          env: concat(plainEnv, migrateSecretEnv, [ { name: 'BOOTSTRAP_ADMIN_EMAIL', value: bootstrapAdminEmail } ])
          resources: { cpu: json('0.5'), memory: '1Gi' }
        }
      ]
    }
  }
  dependsOn: [ kvSecretsUser, acrPull, psaDb ]
}

output proxyFqdn string = deployApps ? proxy.properties.configuration.ingress.fqdn : ''
output vaultName string = keyVault.name
output identityClientId string = identity.properties.clientId
output environmentName string = env.name
output customDomainVerificationId string = env.properties.customDomainConfiguration.customDomainVerificationId
output postgresHost string = postgres.properties.fullyQualifiedDomainName
