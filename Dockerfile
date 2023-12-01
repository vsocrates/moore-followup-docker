# For more information, please refer to https://aka.ms/vscode-docker-python
FROM python:3.9.7

EXPOSE 5005

# Keeps Python from generating .pyc files in the container
ENV PYTHONDONTWRITEBYTECODE=1

# Turns off buffering for easier container logging
ENV PYTHONUNBUFFERED=1

RUN python -m pip install --upgrade pip 
RUN apt-get update && apt-get install python3-dev -y \
                        gcc -y \
                        libc-dev -y 
# RUN apt-get install python3-dev -y && \
# apt-get install libevent-dev -y

# Install pip requirements
COPY requirements.txt .
RUN python -m pip install -r requirements.txt

## or this one.
# pip install -U pip setuptools wheel
# pip install Flask
# pip install openpyxl

# pip3 install torch==1.9.0+cpu  -f https://download.pytorch.org/whl/torch_stable.html
# pip install transformers==4.20.1
# pip install -U spacy==3.2.3
# pip install spacy-transformers==1.1.7

RUN python -m spacy download en_core_web_trf-3.2.0 --direct

COPY en_moore_followup-0.0.0-py3-none-any.whl .
COPY en_moore_nodule-0.0.0-py3-none-any.whl .
COPY en_moore_cancer-0.0.0-py3-none-any.whl .

# copy over the package and install that? 
RUN pip install en_moore_followup-0.0.0-py3-none-any.whl
RUN pip install en_moore_nodule-0.0.0-py3-none-any.whl
RUN pip install en_moore_cancer-0.0.0-py3-none-any.whl

WORKDIR /app/data
WORKDIR /app
COPY . /app

# Creates a non-root user with an explicit UID and adds permission to access the /app folder
# For more info, please refer to https://aka.ms/vscode-docker-python-configure-containers
RUN adduser -u 5678 --disabled-password --gecos "" appuser && chown -R appuser /app
USER appuser

# During debugging, this entry point will be overridden. For more information, please refer to https://aka.ms/vscode-docker-python-debug
CMD [ "python3", "-m" , "flask", "--app=deploy", "--port=5005", "run"]
# CMD ["gunicorn", "--bind", "0.0.0.0:5005", \
# "--timeout", "120" ,\
# #  "--threads", "2", \
# # "--worker-tmp-dir", "/dev/shm",\
# "--workers", "2", "--threads", "1", "--worker-class", "async", \
#  "deploy:app"]
