from celery.result import AsyncResult
from flask import Blueprint
from flask import (
	request,
    render_template,
    url_for, flash, redirect,
)

from flask import Blueprint
from flask import request
bp = Blueprint("tasks", __name__, url_prefix="/tasks")

from . import tasks

@bp.post("/process")
def process():
    fp = request.form.get("filepath", type=str)
    result = tasks.predict_CT.delay(fp)
    return {"result_id":result.id}


@bp.get("/progress/<id>")
def result(id: str) -> dict[str, object]:
    result = AsyncResult(id)
    ready = result.ready()
    return {
        "ready": ready,
        "successful": result.successful() if ready else None,
        "value": result.get() if ready else result.result,
    }



# @bp.get('/progress/<string:thread_id>')
# def progress(thread_id):
#     return {"thread_id": thread_id}

    # return render_template("progress.html", 
    #     cancer_progress=cache.get('cancer_progress'), 
    #     nodule_progress=cache.get('nodule_progress'), 
    #     followup_progress=cache.get('followup_progress'),         
    #     input_file=cache.get('input_file'),
    #     thread_id = thread_id)

