# 3rd party modules
import yaml

# stdlib
import logging, os, sys
from logging.handlers import RotatingFileHandler


# Initialize default config structure
def create_default_config():
    return {
        "app": {},
        "reddit": {},
        "paths": {},
        "defaults": {},
        "runtime": {}
    }


# Loading config
config = create_default_config()
config_found = False

# Try loading from config files first
if os.path.isfile("config.yml"):
    with open('config.yml', 'r') as f:
        config = yaml.safe_load(f)
        config["docker"] = False
        config_found = True
elif os.path.isfile("config-docker.yml"):
    with open('config-docker.yml', 'r') as f:
        config = yaml.safe_load(f)
        config["docker"] = True
        config["paths"] = {}
        config["paths"]["output"] = "output"
        config_found = True

# Check for environment variables and use them if available
# This allows Render (or other cloud platforms) to override settings

# App settings
if os.environ.get('APP_NAME'):
    if 'app' not in config:
        config['app'] = {}
    config['app']['name'] = os.environ.get('APP_NAME')

if os.environ.get('APP_URL'):
    if 'app' not in config:
        config['app'] = {}
    config['app']['url'] = os.environ.get('APP_URL')

# Reddit API credentials
if os.environ.get('REDDIT_CLIENT_ID'):
    if 'reddit' not in config:
        config['reddit'] = {}
    config['reddit']['client-id'] = os.environ.get('REDDIT_CLIENT_ID')

if os.environ.get('REDDIT_CLIENT_SECRET'):
    if 'reddit' not in config:
        config['reddit'] = {}
    config['reddit']['client-secret'] = os.environ.get('REDDIT_CLIENT_SECRET')

if os.environ.get('REDDIT_ROOT'):
    if 'reddit' not in config:
        config['reddit'] = {}
    config['reddit']['root'] = os.environ.get('REDDIT_ROOT')
else:
    # Set default Reddit root if not provided
    if 'reddit' in config and 'root' not in config['reddit']:
        config['reddit']['root'] = 'https://www.reddit.com'

# Path settings
if 'paths' not in config:
    config['paths'] = {}

if os.environ.get('OUTPUT_PATH'):
    config['paths']['output'] = os.environ.get('OUTPUT_PATH')
elif 'output' not in config.get('paths', {}):
    config['paths']['output'] = 'output'

# Date format settings
if 'defaults' not in config:
    config['defaults'] = {}

if os.environ.get('DATE_FORMAT'):
    config['defaults']['dateformat'] = os.environ.get('DATE_FORMAT')
elif 'dateformat' not in config.get('defaults', {}):
    config['defaults']['dateformat'] = '%a %Y-%m-%d at %H:%M'

# Verify essential configuration exists
missing_config = []
if 'app' not in config or 'name' not in config['app']:
    missing_config.append('app.name')
if 'app' not in config or 'url' not in config['app']:
    missing_config.append('app.url')
if 'reddit' not in config or 'client-id' not in config['reddit']:
    missing_config.append('reddit.client-id')
if 'reddit' not in config or 'client-secret' not in config['reddit']:
    missing_config.append('reddit.client-secret')

if missing_config and not config_found:
    print("No configuration file found and the following required environment variables are missing:", file=sys.stderr)
    for config_item in missing_config:
        print(f"- {config_item}", file=sys.stderr)
    print("\nEither provide a config.yml/config-docker.yml file or set the required environment variables.", file=sys.stderr)
    raise SystemExit(1)

# Set standard configuration values
config['app']['version'] = "1.2.0"
config['app']['project'] = "https://github.com/Ailothaen/RedditArchiver"

# Ensure 'name' exists before constructing the agent string
if 'name' in config['app']:
    config['reddit']['agent'] = f"{config['app']['name']} v{config['app']['version']} (by u/ailothaen)"
else:
    config['reddit']['agent'] = f"RedditArchiver v{config['app']['version']} (by u/ailothaen)"

# Initialize runtime settings
if 'runtime' not in config:
    config['runtime'] = {}
config['runtime']['average'] = int(os.environ.get('AVERAGE_DOWNLOAD_TIME', '30'))

# Set additional config from environment if provided
if os.environ.get('DISABLE_RECURSION_LIMIT'):
    if 'app' not in config:
        config['app'] = {}
    config['app']['disable-recursion-limit'] = os.environ.get('DISABLE_RECURSION_LIMIT').lower() == 'true'

# Set default IP access restriction if specified
if os.environ.get('ONLY_ALLOW_FROM'):
    if 'app' not in config:
        config['app'] = {}
    config['app']['only-allow-from'] = os.environ.get('ONLY_ALLOW_FROM').split(',')
config['runtime']['average'] = 30

# Setup logging with fallback
log = logging.getLogger('redditarchiver_main')
log.setLevel(logging.INFO)  # Define minimum severity here

# Create formatter
formatter = logging.Formatter('[%(asctime)s][%(module)s][%(levelname)s] %(message)s', '%Y-%m-%d %H:%M:%S %z')

# First try to set up file logging
try:
    # Check if logs directory exists, create if it doesn't
    log_dir = './logs'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
        print(f"Created logs directory at {os.path.abspath(log_dir)}")
    
    # Create file handler
    file_handler = RotatingFileHandler(
        os.path.join(log_dir, 'main.log'),
        maxBytes=1000000,
        backupCount=10
    )
    file_handler.setFormatter(formatter)
    log.addHandler(file_handler)
    print("File logging configured successfully")
    
except Exception as e:
    print(f"Warning: Could not set up file logging: {str(e)}")
    print("Falling back to console logging only")

# Always add console handler as backup
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)
log.addHandler(console_handler)

# Application startup banner
log.info("+----------------------------------------+")
log.info("|     ;;;;;                              |")
log.info("|     ;;;;;         R e d d i t          |")
log.info("|     ;;;;;       A r c h i v e r        |")
log.info("|   ..;;;;;..                            |")
log.info("|    ':::::'          v {}            |".format(config['app']['version']))
log.info("|      ':`                               |")
log.info("+----------------------------------------+")
python_version = sys.version.replace("\n", " ")
log.info(f"Python version: {python_version}")
log.info(f"Running with app URL: {config['app'].get('url', 'Not set')}")
log.debug("Config: {}".format(str(config)))
