# Load the extensions
load('ext://deployment', 'deployment_create')
load('ext://podman', 'podman_build')
load('ext://secret', 'secret_from_dict')

allow_k8s_contexts('default')

yamls = [
  'components/statestore/redis.yaml',
  'components/deployments/discollama.yaml',
]

for yaml in yamls:
  k8s_yaml(yaml)


#Podman
podman_build(
  'quay.io/mightydjinn/discollama',
  context='.',
  extra_flags=['--platform=linux/amd64'],
  ignore=['.github/*',
          '.dockerignore',
          '.env',
          'compose.yaml',
          'Tiltfile',
          'components/**'
  ],
)


#Docker
#docker_build('discollama', '.')

k8s_yaml(secret_from_dict('discollama', inputs = {
    'OLLAMA_HOST' : os.getenv('OLLAMA_HOST'),
    'OLLAMA_MODEL' : os.getenv('OLLAMA_MODEL'),
    'DISCORD_TOKEN' : os.getenv('DISCORD_TOKEN')
}))
