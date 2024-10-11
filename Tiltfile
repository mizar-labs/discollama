# Load the extensions
load('ext://deployment', 'deployment_create')
load('ext://podman', 'podman_build')
load('ext://secret', 'secret_from_dict')

allow_k8s_contexts('default')


#Podman
podman_build(
  'quay.io/mightydjinn/discollama',
  context='.',
  extra_flags=['--platform=linux/amd64'],
  ignore=['.github/*',
          '.dockerignore',
          '.env',
          'compose.yaml',
          'Tiltfile'
  ],
  live_update=[
        sync('./discollama.py', '/app/'),
        run('cd /app && poetry install --no-root --only main',
            trigger='./pyproject.toml')
  ]
)


#Docker
#docker_build('discollama', '.')

k8s_yaml(secret_from_dict('discollama', inputs = {
    'REDIS_HOST' : os.getenv('REDIS_HOST'),
    'REDIS_PORT' : os.getenv('REDIS_PORT'),
    'OLLAMA_HOST' : os.getenv('OLLAMA_HOST'),
    'OLLAMA_MODEL' : os.getenv('OLLAMA_MODEL'),
    'DISCORD_TOKEN' : os.getenv('DISCORD_TOKEN')
}))


# Create a redis deployment and service with a readiness probe
deployment_create(
  'redis',
  ports='6379',
  readiness_probe={'exec':{'command':['redis-cli','ping']}}
)

deployment_create(
 'discollama',
 image='quay.io/mightydjinn/discollama',
 env_from=[{'secretRef': {'name': 'discollama'}}]
)
