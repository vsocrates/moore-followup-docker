import uuid
import time
import gc 

from flask import (
	Flask,
	request,
    render_template,
    url_for, flash, redirect,
)
from flask_cors import CORS
from flask_executor import Executor
from flask_caching import Cache

import spacy
# from run_followup_pipeline import Followup_PredictionThread

import json
import os
import ast
import re

import pandas as pd

import spacy
from spacy.training import Corpus
from spacy.tokens import DocBin
from spacy.language import Language

app = Flask(__name__)
CORS(app)

SECRET_KEY = "b98ce042c833cf76dc0021903e83e18ac132b7a483991049"

app.config['CACHE_TYPE'] = 'FileSystemCache' 
app.config['CACHE_DIR'] = 'cache' # path to your server cache folder
app.config['CACHE_THRESHOLD'] = 100000 # number of 'files' before start auto-delete
app.config["CACHE_DEFAULT_TIMEOUT"] = 0
app.config['SECRET_KEY'] = SECRET_KEY
app.config["DEBUG"] = True
app.config['EXECUTOR_PROPAGATE_EXCEPTIONS'] = False

executor = Executor(app)
cache = Cache(app)


def create_filtered_labels(row):
    
    if row['Cancer_on_CT_NLP_rec'] == True:
        label = "MALIGNANCY"
    elif row['Nodule_on_CT_NLP_rec'] == False:
        label = "MISSING_NODULE"
    elif (row['Cancer_on_CT_NLP_rec'] == False) & (row['Nodule_on_CT_NLP_rec'] == True):
        label = row['FOLLOWUP_pred']
    else:
        label = "INCONSISTENT"
    return label

@app.route('/', methods=['GET', "POST"])
def input_fp():
    if request.method == 'POST':
        fpath = request.form['filepath']
        if not fpath:
            print('Path to data is required!')
            flash('Path to data is required!', "error")
        else:
            try:
                data_in = read_file(fpath)
            except FileNotFoundError:
                print(f"The file at path {fpath} cannot be found!")
                cache.set('has_data', False)
                flash('This file does not exist!', "error")
                return render_template('index.html')            
            else:
                cache.set('has_data', True)
                thread_id = str(uuid.uuid1())
                # executor.submit(predict_CT, fpath)
                if len(executor.futures) > 0:
                    flash("You're already running something. Please wait for it to finish until running another!", "warning")
                    _ = executor.futures.pop('predictCT')
                    return redirect(url_for('input_fp'))
                
                future = predict_CT.submit_stored('predictCT', fpath, data_in)
                cache.set('input_file', fpath)
                return redirect(url_for('progress', thread_id=thread_id))

    return render_template('index.html')


@app.route('/progress/<string:thread_id>', methods=['GET'])
def progress(thread_id):

    if executor.futures.exception('predictCT'):
        flash('Something went wrong, please resubmit your file!', "error")
        _ = executor.futures.pop('predictCT')
        return redirect(url_for('input_fp'))
    else:
        return render_template("progress.html", 
            cancer_progress=cache.get('cancer_progress'), 
            nodule_progress=cache.get('nodule_progress'), 
            followup_progress=cache.get('followup_progress'),         
            input_file=cache.get('input_file'),
            thread_id = thread_id)



def read_file(input_file):

    _, ext = os.path.splitext(input_file)
    if ext[1:] in ["xlsx", "xls"]:
        data_in = pd.read_excel(input_file)
    elif ext[1:] == "tsv":
        data_in = pd.read_csv(input_file, sep="\t")
    else:
        data_in = pd.read_csv(input_file)
    
    return data_in

def get_file_type(input_file):
    return os.path.splitext(input_file)[1][1:]

def get_file_length(data_in):
    return data_in.shape[0]

@executor.job
def predict_CT(input_file, data_in, batch_size=50, gpu=False, verbosity=10):

    try:
        total_start_time = time.time()

        start_time = time.time()
        cancer_nlp = spacy.load("en_moore_cancer", disable=["tok2vec", "tagger", "parser", "attribute_ruler", "lemmatizer", "ner"])
        print("--- Load Cancer Model Time: %s seconds ---" % (time.time() - start_time), flush=True)    

        cache.set("has_data", False)
        cache.set("cancer_progress", 0)
        cache.set("nodule_progress", 0)
        cache.set("followup_progress", 0)

        if gpu:
            spacy.require_gpu()
            
        def convert_dict_str_to_dict(x, col_name):
            tmp = ast.literal_eval(x[col_name])
            return tmp

        def extract_prodigy_vals(x, col_name):
            tmp = eval(x[col_name])
            pred = max(tmp, key=tmp.get)
            score = tmp[pred]
            return pred, score


        if not "CT_Text" in data_in.columns:
            raise KeyError("'CT_Text' is not a column in your input data")

        if not "ID" in data_in.columns:
            raise KeyError("'ID' is not a column in your input data")

        _, ext = os.path.splitext(input_file)
        if ext[1:] not in ['csv', "tsv", "xlsx", "xls"]:
            raise ValueError(f"{ext} file type not supported")

        file_len = get_file_length(data_in)

        if int(0.1 * file_len) > 0:
            # anything > 9 documents, take the min of 50 or 10% of document size
            batch_size = min(50, int(0.1 * file_len))
        else:
            # anything < 9 documents, just run them all together
            batch_size = file_len

        print(f"Using batch size: {batch_size}", flush=True)
        # Convert text into IMPRESSIONS only
        # impressions = []
        # for idx, text in self.data_in.loc[~self.data_in['CT_Text'].isnull(), 'CT_Text'].items():
        #     try:
        #         impression = text
        #         if re.search(r"IMPRESSION:|Impression:", text):
        #             idx_start = re.search(r"IMPRESSION:|Impression:", text).start()
        #         else:
        #             idx_start = 0
        #         impression = text[idx_start:]
        #         impressions.append(impression)
        #     except ValueError:
        #         impressions.append(impression)

        # self.data_in.loc[~self.data_in['CT_Text'].isnull(), 'CT_Text_Impressions'] = impressions


        ct_texts = data_in['CT_Text'].tolist()
        impressions = []
        nonimpressions = []

        start_time = time.time()
        for idx, text in enumerate(ct_texts):
            if re.search(r"IMPRESSION:|Impression:", text):
                impression_end_idx = impression_start_idx = re.search(r"IMPRESSION:|Impression:", text).start()
            else:
                impression_start_idx = 0
                impression_end_idx = len(text)

            nonimpression = text[:impression_end_idx]
            nonimpressions.append(nonimpression)
            impression = text[impression_start_idx:]
            impressions.append(impression)

        data_in['CT_Text_Impressions'] = impressions
        data_in['CT_Text_Non_Impressions'] = nonimpressions
        print("--- Split Impression/Narrative Time: %s seconds ---" % (time.time() - start_time), flush=True)    

        if verbosity:
            print("created impressions...", flush=True)

        start_time = time.time()
        # 1. Start with the Cancer module    
        # taken from https://stackoverflow.com/a/44764557/1726404
        '''
        This works by using nlp.pipe and putting our records into tuples. We process it as tuples and get the context
        In our work, the context is just the study id. 
        We get the entity text, label, start and stop characters for each entity
        we convert that to a json string, we then put the [context,json] together into a list
        append this list to nlp_out
        then turn nlp out into a df with 1 col being study id and the other being the nlp out
        Finally we merge the df with our main data df. Now we have a column with the text
        '''
        cancer_nlp_out = []
        count = 0
        for doc, ctx in cancer_nlp.pipe(list(data_in[['CT_Text_Non_Impressions', 'ID']].to_records(index=False)),
                                            as_tuples=True, batch_size=batch_size, n_process=1):
            out_ = doc.cats

            cancer_nlp_out.append([ctx, json.dumps(out_, indent = 2)])

            cache.set('cancer_progress', float(cache.get("cancer_progress")) + 1/file_len * 100)
            # self.cancer_progress += 1/file_len * 100
            
            # just make sure we don't go over 100
            # self.cancer_progress = min(self.cancer_progress, 100)

            if cache.get('cancer_progress') > 0.1:
                cache.set('cancer_progress', round(cache.get('cancer_progress'), 1))            
            # if self.cancer_progress > 0.1:
            #     self.cancer_progress = round(self.cancer_progress, 1)

            if verbosity:
                count +=1
                if count % 50 == 0 and verbosity > 8:
                    print(count, flush=True)
                elif count % 500 == 0 and verbosity > 4:
                    print(count, flush=True)
                elif count % 1000 == 0 and verbosity > 2:
                    print(count, flush=True)
                elif count % 5000 == 0 and verbosity > 1:
                    print(count, flush=True)
        
        cache.set('cancer_progress', 100)
        # self.cancer_progress = 100

        if verbosity:
            print("ran cancer predictions...", flush=True)

        nlp_df = pd.DataFrame(cancer_nlp_out, columns=['ID', 'NLP_OUT'])
        expanded_y_pred = nlp_df.apply(extract_prodigy_vals, axis=1, col_name="NLP_OUT", result_type="expand")

        data_in["Cancer_on_CT_NLP_score"] = expanded_y_pred[1]
        data_in["Cancer_on_CT_NLP_rec"] = data_in["Cancer_on_CT_NLP_score"] > 0.5
        print("--- Cancer Exclusion Time: %s seconds ---" % (time.time() - start_time), flush=True)    

        del cancer_nlp
        gc.collect()

        start_time = time.time()
        nodule_nlp = spacy.load("en_moore_nodule", disable=["tok2vec", "tagger", "parser", "attribute_ruler", "lemmatizer", "ner"])
        print("--- Load Nodule Model Time: %s seconds ---" % (time.time() - start_time), flush=True)    

        start_time = time.time()

        # 2. Nodule Module
        nodule_nlp_out = []
        count = 0
        for doc, ctx in nodule_nlp.pipe(list(data_in[['CT_Text', 'ID']].to_records(index=False)),
                                            as_tuples=True, batch_size=batch_size, n_process=1):
            out_ = doc.cats
            nodule_nlp_out.append([ctx, json.dumps(out_, indent = 2)])

            cache.set('nodule_progress', float(cache.get("nodule_progress")) + 1/file_len * 100)
            # self.nodule_progress += 1/file_len * 100
            
            # just make sure we don't go over 100
            # self.nodule_progress = min(self.nodule_progress, 100)
            
            if cache.get('nodule_progress') > 0.1:
                cache.set('nodule_progress', round(cache.get('nodule_progress'), 1))
            # if self.nodule_progress > 0.1:
            #     self.nodule_progress = round(self.nodule_progress, 1)

            if verbosity:
                count +=1
                if count % 50 == 0 and verbosity > 8:
                    print(count, flush=True)
                elif count % 500 == 0 and verbosity > 4:
                    print(count, flush=True)
                elif count % 1000 == 0 and verbosity > 2:
                    print(count, flush=True)
                elif count % 5000 == 0 and verbosity > 1:
                    print(count, flush=True)
        
        cache.set('nodule_progress', 100)
        # self.nodule_progress = 100

        if verbosity:
            print("ran nodule predictions...", flush=True)

        nlp_df = pd.DataFrame(nodule_nlp_out, columns=['ID', 'NLP_OUT'])
        expanded_y_pred = nlp_df.apply(extract_prodigy_vals, axis=1, col_name="NLP_OUT", result_type="expand")

        data_in["Nodule_on_CT_NLP_score"] = expanded_y_pred[1]
        data_in["Nodule_on_CT_NLP_rec"] = data_in["Nodule_on_CT_NLP_score"] > 0.5
        print("--- Detect Nodule Time: %s seconds ---" % (time.time() - start_time), flush=True)    

        del nodule_nlp
        gc.collect()
        
        start_time = time.time()
        followup_nlp = spacy.load("en_moore_followup", disable=["tok2vec", "tagger", "parser", "attribute_ruler", "lemmatizer", "ner"])
        print("--- Load Followup Model Time: %s seconds ---" % (time.time() - start_time), flush=True)    


        start_time = time.time()
        # 3. Finally, followup
        followup_nlp_out = []
        count = 0
        for doc, ctx in followup_nlp.pipe(list(data_in[['CT_Text_Impressions', 'ID']].to_records(index=False)),
                                            as_tuples=True, batch_size=batch_size, n_process=1):
            out_ = doc.cats
            followup_nlp_out.append([ctx, json.dumps(out_, indent = 2)])

            cache.set('followup_progress', float(cache.get("followup_progress")) + 1/file_len * 100)
            # self.followup_progress += 1/file_len * 100
            
            # just make sure we don't go over 100
            # self.followup_progress = min(self.followup_progress, 100)
            
            if cache.get('followup_progress') > 0.1:
                cache.set('followup_progress', round(cache.get('followup_progress'), 1))
            # if self.followup_progress > 0.1:
            #     self.followup_progress = round(self.followup_progress, 1)

            if verbosity:
                count +=1
                if count % 50 == 0 and verbosity > 8:
                    print(count, flush=True)
                elif count % 500 == 0 and verbosity > 4:
                    print(count, flush=True)
                elif count % 1000 == 0 and verbosity > 2:
                    print(count, flush=True)
                elif count % 5000 == 0 and verbosity > 1:
                    print(count, flush=True)

        cache.set('followup_progress', 100)
        # self.followup_progress = 100
        print("--- Followup Prediction Time: %s seconds ---" % (time.time() - start_time), flush=True)    

        if verbosity:
            print("ran followup predictions...", flush=True)
            count +=1        

        start_time = time.time()
        nlp_df = pd.DataFrame(followup_nlp_out, columns=['ID', 'NLP_OUT'])
        score_df = nlp_df.apply(convert_dict_str_to_dict, axis=1, col_name="NLP_OUT", result_type="expand")
        nlp_df = pd.concat([nlp_df, score_df], axis=1)
        nlp_df['FOLLOWUP_pred'] = nlp_df[["NO_FOLLOWUP", "HARD_FOLLOWUP", "CONDITIONAL_FOLLOWUP"]].idxmax(axis=1)
        data_in_with_scores = data_in.merge(nlp_df, on="ID", how='left')        
        data_in_with_scores = data_in_with_scores.drop("NLP_OUT", axis=1)

        data_in_with_scores['FILTERED_REC'] = data_in_with_scores.apply(create_filtered_labels, axis=1)

        print(data_in_with_scores['FOLLOWUP_pred'].value_counts(normalize=True))

        # Write predictions out to file
        fname, ext = os.path.splitext(input_file)

        if ext[1:] == "tsv":
            data_in_with_scores.to_csv(fname + "_predictions" + ext, index=False, sep="\t")    
        elif ext[1:] == "xls" or ext[1:] == "xlsx":
            data_in_with_scores.to_excel(fname + "_predictions" + ext, index=False)    
        elif ext[1:] == "csv":
            data_in_with_scores.to_csv(fname + "_predictions" + ext, index=False)
        else:
            data_in_with_scores.to_csv(fname + "_predictions.csv", index=False)

        print("--- Postprocessing/Write file time: %s seconds ---" % (time.time() - start_time), flush=True)    

        print("--- Full Pipeline Run: %s seconds ---" % (time.time() - total_start_time), flush=True)

        return True
    
    except Exception as error:
        # handle the exception
        print("An exception occurred:", type(error).__name__, "–", error) # An exception occurred: ZeroDivisionError – division by zero
        raise error
    # except:
    #     print("An error occurred")
    #     raise Exception("HMMM")
