from celery import Celery
from celery import Task
from flask import Flask
from flask import render_template
from flask import (
	request,
    render_template,
    url_for, flash, redirect,
)

from . import tasks


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_mapping(
        CELERY=dict(
            broker_url="redis://127.0.0.1",
            result_backend="redis://127.0.0.1",
            task_ignore_result=True,
        ),
    )
    app.config.from_prefixed_env()
    SECRET_KEY = "b983242c833cf76dc0sdea02190332bf7akr291049"

    app.config['SECRET_KEY'] = SECRET_KEY
    app.config["DEBUG"] = True

    celery_init_app(app)

    @app.route('/', methods=['GET', "POST"])
    def index():
        return render_template("index.html")
    # def index():
    #     if request.method == 'POST':
    #         fpath = request.form['filepath']
    #         if not fpath:
    #             print('Path to data is required!')
    #             flash('Path to data is required!')
    #         else:
    #             try:
    #                 data_in = tasks.read_file(fpath)
    #             except FileNotFoundError:
    #                 print(f"The file at path {fpath} cannot be found!")
    #                 flash('This file does not exist!')
    #                 return render_template('index.html')            
    #             else:
    #                 result = tasks.predict_CT.delay(fpath, data_in)
    #                 # executor.submit(predict_CT, fpath)
    #                 # executor.submit_stored('predictCT', predict_CT, fpath, data_in)
    #                 return redirect(url_for('progress', thread_id=result.id))

    #     return render_template('index.html')

    # @app.route("/")
    # def index() -> str:
    #     return render_template("index.html")

    from . import views
    print(views.bp)
    app.register_blueprint(views.bp)
    return app


def celery_init_app(app: Flask) -> Celery:
    class FlaskTask(Task):
        def __call__(self, *args: object, **kwargs: object) -> object:
            with app.app_context():
                return self.run(*args, **kwargs)

    celery_app = Celery(app.name, task_cls=FlaskTask)
    celery_app.config_from_object(app.config["CELERY"])
    celery_app.set_default()
    app.extensions["celery"] = celery_app
    return celery_app