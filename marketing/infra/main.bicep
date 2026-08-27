// =============================================================================
// Helix Prime Ecosystem — Marketing Site
// Azure Static Web Apps (free tier) hosting for the static portfolio site
// + 5-min demo video + screenshots.
// =============================================================================

@description('Azure region for the Static Web App.')
param location string = resourceGroup().location

@description('Short environment name used in resource naming (e.g. dev, prod).')
param environmentName string = 'prod'

@description('Repository URL for the Static Web App linked build (optional).')
param repositoryUrl string = ''

@description('Repository branch for the Static Web App linked build (optional).')
param branch string = 'main'

@description('SKU for the Static Web App. Free is fine for a portfolio.')
@allowed([
  'Free'
  'Standard'
])
param sku string = 'Free'

var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))
var tags = {
  'app': 'helix-prime-marketing'
  'env': environmentName
  'owner': 'Hatem Shalaby'
  'constitution': '000'
}

resource staticWebApp 'Microsoft.Web/staticSites@2023-12-01' = {
  name: 'helix-prime-${resourceToken}'
  location: location
  tags: tags
  sku: {
    name: sku
    tier: sku
  }
  properties: {
    repositoryUrl: empty(repositoryUrl) ? null : repositoryUrl
    branch: empty(repositoryUrl) ? null : branch
    buildProperties: {
      appLocation: '/'
      outputLocation: 'dist'
      skipGithubActionWorkflowGeneration: true
    }
    stagingEnvironmentPolicy: 'Enabled'
  }
}

output staticWebAppId string = staticWebApp.id
output staticWebAppName string = staticWebApp.name
output defaultHostname string = staticWebApp.properties.defaultHostname
output apiKey string = staticWebApp.listSecrets().apiKey
