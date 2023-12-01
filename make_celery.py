from task_app import create_app
from flask_cors import CORS

flask_app = create_app()
# CORS(flask_app)
celery_app = flask_app.extensions["celery"]