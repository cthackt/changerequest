import os, json
import numpy as np
import pandas as pd
from flask import Flask, g
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from sqlalchemy import create_engine
from .custom.functions import add_custom_checks_function, fix_custom_imports


CUSTOM_CONFIG_PATH = os.path.join(os.getcwd(), 'proj', 'config')
assert os.path.exists(os.path.join(CUSTOM_CONFIG_PATH, 'config.json')), \
    f"{os.path.join(CUSTOM_CONFIG_PATH, 'config.json')} configuration file not found"

CUSTOM_CONFIG = json.loads( open( os.path.join(CUSTOM_CONFIG_PATH, 'config.json'), 'r' ).read() )

app = Flask(__name__, static_url_path='/static')
app.debug = True # remove for production

# SQLALchemy
db = SQLAlchemy()
db.init_app(app)

# LoginManager
login_manager = LoginManager()
login_manager.init_app(app)


# CORS
CORS(app)

# does your application require uploaded filenames to be modified to timestamps or left as is
app.config['CORS_HEADERS'] = 'Content-Type'


app.config['WTF_CSRF_ENABLED'] = True

app.config['MAIL_SERVER'] = CUSTOM_CONFIG.get('mail_server')
app.config['MAIL_DEFAULT_SENDER'] = CUSTOM_CONFIG.get('send_from')
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = True


app.config['SESSION_TYPE'] = 'filesystem'

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DB_CONNECTION_STRING")
app.config['SQLALCHEMY_ECHO'] = True
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

app.config['SECURITY_PASSWORD_SALT'] = os.environ.get('FLASK_APP_SECURITY_PASSWORD_SALT')


app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024  # 100MB limit
app.secret_key = os.environ.get('FLASK_APP_SECRET_KEY')
app.infile = ""

app.maintainers = CUSTOM_CONFIG.get('maintainers')

app.send_from = CUSTOM_CONFIG.get('send_from')


# this code is starting to get out of hand
# I'm wondering if i should just stick my custom configuration here
# or maybe i can try to extend the app.config with the custom config...
# app.custom_config = CUSTOM_CONFIG
# ok, so after having done app.config.update, i can see that it works
# Now, something to do that will likely get swept under the rug and forgotted until it becomes a problem -
#  We need to adjust the code accordingly and get rid of all these individual lines that add on to the app's attributes and things like that
app.config.update(CUSTOM_CONFIG)


# list of database fields that should not be queried on - removed status could be a problem 9sep17 - added trawl calculated fields - removed projectcode for smc part of tbl_phab
app.system_fields = [
    "globalid", "submissionid", "created_user", "created_date", "last_edited_user", "last_edited_date", "warnings"
]

app.custom_unchanging_fields = CUSTOM_CONFIG.get('custom_unchanging_fields')

# All fields that begin with login must also be immutable
app.immutable_fields = [
    *app.system_fields, *app.custom_unchanging_fields
]

# set the database connection string, database, and type of database we are going to point our application at
app.eng = create_engine(os.environ.get('DB_CONNECTION_STRING'))

# set the database connection string, database, and type of database we are going to point our application at
#app.eng = create_engine(environ.get("DB_CONNECTION_STRING"))
def connect_db():
    return create_engine(os.environ.get("DB_CONNECTION_STRING"))

@app.before_request
def before_request():
    g.eng = connect_db()

@app.teardown_request
def teardown_request(exception):
    if hasattr(g, 'eng'):
        g.eng.dispose()


class NpEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, pd.Timestamp):
            return obj.strftime("%Y-%m-%d %H:%M:%S")
        return super(NpEncoder, self).default(obj)

app.json_encoder = NpEncoder

# resolve custom imports, and fix if not set up correctly
# if the app has to add a custom checks file, or an import statement, the app (container) needs to be restarted again
CUSTOM_CHECKS_DIRECTORY = os.path.join(os.getcwd(), 'proj','custom')
app.dtypes = CUSTOM_CONFIG.get('dtypes')
for dtyp in app.dtypes.keys():
    for tbl, func_name in app.dtypes.get(dtyp).get("custom_checks_functions").items():
        add_custom_checks_function(CUSTOM_CHECKS_DIRECTORY, func_name)

# fix the imports in the custom file
fix_custom_imports(CUSTOM_CHECKS_DIRECTORY)

app.user_management = CUSTOM_CONFIG.get('user_management')
# user management info
if app.user_management.get('users_table'):
    app.users_table = CUSTOM_CONFIG.get('users_table')
else:
    print("Warning - no users table specified - falling back to default db_editors")
    app.users_table = 'db_editors'


# App depends on a schema called tmp existing in the database
app.eng.execute("CREATE SCHEMA IF NOT EXISTS tmp;")

# import blueprints down here after custom imports are fixed
# if we tried doing it before, it might have ModuleNotFound Errors
from .export import export
from .login import login
from .main import comparison
from .finalize import finalize
from .auth import auth_bp
from .scraper import scraper
app.register_blueprint(export)
app.register_blueprint(login)
app.register_blueprint(comparison)
app.register_blueprint(finalize)
app.register_blueprint(auth_bp)
app.register_blueprint(scraper)
