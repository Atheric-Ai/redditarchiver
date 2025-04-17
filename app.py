# Project modules
import auth, controllers, models
from config import config

# 3rd party modules
import flask, flask_apscheduler

# stdlib
import logging, os, datetime

app = flask.Flask(__name__)
log = logging.getLogger('redditarchiver_main')

# Ensure output directory exists
output_path = os.path.join(os.getcwd(), 'output')
if not os.path.exists(output_path):
    os.makedirs(output_path, exist_ok=True)
    log.info(f"Created output directory at {output_path}")
else:
    log.info(f"Using existing output directory at {output_path}")


@app.before_request
def before_request_callback():
    """
    Initialises cookie and Reddit token
    """
    # Preventing unauthorized people to access the app
    if "only-allow-from" in config.get("app", {}) and config.get("app", {}).get("only-allow-from"):
        # Get client IP address, either from X-Forwarded-For header or remote_addr
        forwarded_ips = flask.request.headers.getlist("X-Forwarded-For")
        if forwarded_ips:
            client_ip = forwarded_ips[0]
        else:
            client_ip = flask.request.remote_addr
            
        is_allowed = auth.is_client_allowed(client_ip)
        if not is_allowed:
            log.warning(f"Access denied from {client_ip}")
            flask.abort(403)

    flask.g.db = models.connect()
    flask.g.resp = flask.make_response()
    flask.g.data = {}

    # Manage cookies
    if flask.request.endpoint not in ('token', 'favicon', 'status', 'download'):
        auth.manage_cookie()
        flask.g.token = models.read_token(flask.g.db, flask.g.cookie)



# -------------------------- #
# Routes                     #
# -------------------------- #

@app.route("/")
def main():
    """
    Landing page, where the form to download is.
    If the user is not authenticated, a prompt to authenticate appears instead
    """
    if flask.g.token is None:
        # Authentication URL crafter
        flask.g.data['auth_url'] = controllers.craft_authentication_url()
        flask.g.resp.data = flask.render_template('main_unauthenticated.html', data=flask.g.data, config=config)
    else:
        flask.g.resp.data = flask.render_template('main_authenticated.html', data=flask.g.data, config=config)
    return flask.g.resp


@app.route("/favicon.ico")
def favicon():
    """
    Self-explanatory, I guess?
    """
    return flask.send_from_directory(os.path.join(os.getcwd(), 'static', 'images'), 'favicon.ico')


@app.route("/token")
def token():
    """
    Interception of token given by Reddit
    """
    cookie = flask.request.args.get('state')
    code = flask.request.args.get('code')
    
    # Detailed debug logging
    log.info("=== OAUTH CALLBACK DEBUG ===")
    log.info(f"Full request URL: {flask.request.url}")
    log.info(f"Request method: {flask.request.method}")
    log.info(f"All query parameters: {dict(flask.request.args)}")
    log.info(f"State parameter: {cookie}")
    log.info(f"Code parameter: {code}")
    log.info(f"Current cookie: {flask.request.cookies.get('redditarchive_id', 'Not Set')}")
    log.info(f"App URL in config: {config['app']['url']}")
    log.info(f"Referring URL: {flask.request.referrer}")
    log.info(f"Request headers: {dict(flask.request.headers)}")
    
    # Verify the state parameter matches our cookie
    current_cookie = flask.request.cookies.get('redditarchive_id', None)
    if cookie != current_cookie:
        log.error(f"State mismatch: State={cookie}, Cookie={current_cookie}")
        log.info("==========================")
        return "Authentication failed: state parameter does not match cookie.", 400
    else:
        log.info("State verification: PASSED ✓")
    
    # Configure redirect URI exactly as in Reddit app
    redirect_uri = f"{config['app']['url']}/token"
    log.info(f"Using redirect URI for token exchange: {redirect_uri}")
    log.info("==========================")
    
    try:
        refresh_token = controllers.get_refresh_token()
    except Exception as e:
        log.error(f'Reddit did not recognize the code for {cookie}. Error: {str(e)}')
        log.error(f'Exception details: {type(e).__name__}: {str(e)}')
        return "Reddit did not recognize the code given. This should not happen.", 400

    log.info(f'Refresh token got for cookie {cookie}: {refresh_token}')
    models.create_token(flask.g.db, cookie, refresh_token)

    # taking back to homepage
    return flask.redirect("/", code=303)


@app.route("/request", methods=['POST'])
def request():
    """
    Requests a job
    """
    try:
        flask.g.data['job_id'] = controllers.request()
    except ValueError as e:
        flask.g.data['error_message'] = controllers.error_message(str(e))
        flask.g.resp.data = flask.render_template('request_error.html', data=flask.g.data, config=config)
    else:
        flask.g.resp.data = flask.render_template('request.html', data=flask.g.data, config=config)
    
    return flask.g.resp


@app.route("/status/<job_id>")
def status(job_id):
    """
    Requests the status of a job
    """
    flask.g.resp.status, flask.g.resp.data = controllers.status(job_id)
    return flask.g.resp


@app.route("/download/<job_id>")
def download(job_id):
    """
    Downloads the result of a job
    """
    log.info(f"Download requested for job {job_id}")
    filename = controllers.get_filename(job_id)
    
    return flask.send_from_directory(os.path.join(os.getcwd(), 'output'), filename, as_attachment=True)


@app.route("/debug-config")
def debug_config():
    """
    Display current configuration (excluding sensitive values)
    """
    safe_config = {
        'app': {
            'url': config['app'].get('url'),
            'name': config['app'].get('name'),
            'version': config['app'].get('version')
        }
    }
    return flask.jsonify(safe_config)


# -------------------------- #
# Schedulers                 #
# -------------------------- #

scheduler = flask_apscheduler.APScheduler()
scheduler.init_app(app)
scheduler.start()

@scheduler.task('interval', id='st_cleanup_downloads', hours=1)
def cleanup_downloads():
    """
    Remove all downloads older than 24 hours
    """
    controllers.cleanup_downloads()


@scheduler.task('interval', id='st_cleanup_sessions', hours=24)
def cleanup_sessions():
    """
    Remove all sessions unused since 3 months
    """
    controllers.cleanup_sessions()


@scheduler.task('interval', id='st_calculate_average_eta', hours=24, start_date=datetime.datetime.now()+datetime.timedelta(seconds=10))
def calculate_average_eta():
    """
    Calculates average time to download a thread (depending on the number of replies) so we can give a good ETA estimation.
    Runs at startup then once every 24h.
    """
    controllers.calculate_average_eta()
