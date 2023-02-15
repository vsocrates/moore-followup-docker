import uuid

from flask import (
	Flask,
	request,
    render_template,
    url_for, flash, redirect
)
from flask_cors import CORS


import spacy
from run_followup_pipeline import Followup_PredictionThread

app = Flask(__name__)
CORS(app)

SECRET_KEY = "b98ce042c833cf76dc0021903e83e18ac132b7a483991049"
app.config['SECRET_KEY'] = SECRET_KEY
app.config["DEBUG"] = True
exporting_threads = {}

@app.route('/', methods=['GET', "POST"])
def input_fp():
    global exporting_threads

    if request.method == 'POST':
        fpath = request.form['filepath']
        if not fpath:
            print('Path to data is required!')
            flash('Path to data is required!')
        else:
            thread_id = str(uuid.uuid1())
            thread = Followup_PredictionThread(fpath)
            if thread.has_data:
                exporting_threads[thread_id] = thread
                exporting_threads[thread_id].start()
                return redirect(url_for('progress', thread_id=thread_id))
            else:
                flash('Path to data is required!')
                return render_template('index.html')            

    return render_template('index.html')


@app.route('/progress/<string:thread_id>', methods=['GET'])
def progress(thread_id):
    global exporting_threads

    progress = exporting_threads[thread_id].progress
    input_file = exporting_threads[thread_id].input_file

    return render_template("progress.html", 
        progress=progress, 
        input_file=input_file,
        thread_id = thread_id)

