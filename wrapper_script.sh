#!/bin/sh

# Start the first process
# ./my_first_process &

# start redis
nohup redis-server &

# start celery
nohup celery -A make_celery worker --loglevel INFO &

# Start the second process
# ./my_second_process &
export FLASK_APP=task_app
# python /app/deploy.py
flask -A task_app run --host=0.0.0.0
# flask --app deploy --debug  run --host=0.0.0.0

# Wait for any process to exit
wait -n

# Exit with status of process that exited first
exit $?


# CMD ["gunicorn", "--bind", "0.0.0.0:5005", \
# "--timeout", "120" ,\
# #  "--threads", "2", \
# # "--worker-tmp-dir", "/dev/shm",\
# "--workers", "2", "--threads", "1", "--worker-class", "sync", \
#  "deploy:app"]