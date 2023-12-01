import json
import os
import ast
import re
import threading
import math 

import pandas as pd

import spacy
from spacy.training import Corpus
from spacy.tokens import DocBin
from spacy.language import Language


class Followup_PredictionThread(threading.Thread):
    def __init__(self, input_file, gpu = False, verbosity = 10, batch_size = 50) -> None:

        self.input_file = input_file
        self.gpu = gpu
        self.verbosity = verbosity
        self.cancer_progress = 0
        self.nodule_progress = 0
        self.followup_progress = 0
        self.batch_size = batch_size
        self.has_data = False

        try:
            self.data_in = self.read_file()
        except FileNotFoundError:
            print(f"The file at path {self.input_file} cannot be found!")
            self.has_data = False
        else:
            self.has_data = True

        super().__init__()

    def read_file(self):

        _, ext = os.path.splitext(self.input_file)
        if ext[1:] in ["xlsx", "xls"]:
            data_in = pd.read_excel(self.input_file)
        elif ext[1:] == "tsv":
            data_in = pd.read_csv(self.input_file, sep="\t")
        else:
            data_in = pd.read_csv(self.input_file)
        
        return data_in

    def get_file_type(self):
        return os.path.splitext(self.input_file)[1][1:]

    def run(self):

        followup_nlp = spacy.load("en_moore_followup")
        cancer_nlp = spacy.load("en_moore_cancer")
        nodule_nlp = spacy.load("en_moore_nodule")

        if self.gpu:
            spacy.require_gpu()
            
        def convert_dict_str_to_dict(x, col_name):
            tmp = ast.literal_eval(x[col_name])
            return tmp

        def extract_prodigy_vals(x, col_name):
            tmp = eval(x[col_name])
            pred = max(tmp, key=tmp.get)
            score = tmp[pred]
            return pred, score


        if not "CT_text" in self.data_in.columns:
            raise KeyError("'CT_text' is not a column in your input data")

        if not "ID" in self.data_in.columns:
            raise KeyError("'ID' is not a column in your input data")

        _, ext = os.path.splitext(self.input_file)
        if ext[1:] not in ['csv', "tsv", "xlsx", "xls"]:
            raise ValueError(f"{ext} file type not supported")

        file_len = self.get_file_length()

        # Convert text into IMPRESSIONS only
        # impressions = []
        # for idx, text in self.data_in.loc[~self.data_in['CT_text'].isnull(), 'CT_text'].items():
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

        # self.data_in.loc[~self.data_in['CT_text'].isnull(), 'CT_text_Impressions'] = impressions


        ct_texts = self.data_in['CT_Text'].tolist()
        impressions = []
        nonimpressions = []

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

        self.data_in['CT_text_Impressions'] = impressions
        self.data_in['CT_text_Non_Impressions'] = nonimpressions


        if self.verbosity:
            print("created impressions...", flush=True)

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
        for doc, ctx in cancer_nlp.pipe(list(self.data_in[['NON-IMPRESSION', 'KL_ID']].to_records(index=False)),
                                            as_tuples=True, batch_size=self.batch_size, n_process=1):
            out_ = doc.cats
            cancer_nlp_out.append([ctx, json.dumps(out_, indent = 2)])

            self.cancer_progress += 1/file_len * 100
            
            # just make sure we don't go over 100
            # self.cancer_progress = min(self.cancer_progress, 100)
            
            if self.cancer_progress > 0.1:
                self.cancer_progress = round(self.cancer_progress, 1)

            if self.verbosity:
                count +=1
                if count % 50 == 0 and self.verbosity > 8:
                    print(count, flush=True)
                elif count % 500 == 0 and self.verbosity > 4:
                    print(count, flush=True)
                elif count % 1000 == 0 and self.verbosity > 2:
                    print(count, flush=True)
                elif count % 5000 == 0 and self.verbosity > 1:
                    print(count, flush=True)

        self.cancer_progress = 100

        if self.verbosity:
            print("ran cancer predictions...", flush=True)

        nlp_df = pd.DataFrame(cancer_nlp_out, columns=['KL_ID', 'NLP_OUT'])
        expanded_y_pred = nlp_df.apply(extract_prodigy_vals, axis=1, col_name="NLP_OUT", result_type="expand")

        self.data_in["Cancer_on_CT_NLP_score"] = expanded_y_pred[1]
        self.data_in["Cancer_on_CT_NLP_rec"] = self.data_in["Cancer_on_CT_NLP_score"] > 0.5

        # 2. Nodule Module
        nodule_nlp_out = []
        count = 0
        for doc, ctx in nodule_nlp.pipe(list(self.data_in[['CT_Text', 'KL_ID']].to_records(index=False)),
                                            as_tuples=True, batch_size=self.batch_size, n_process=1):
            out_ = doc.cats
            nodule_nlp_out.append([ctx, json.dumps(out_, indent = 2)])

            self.nodule_progress += 1/file_len * 100
            
            # just make sure we don't go over 100
            # self.nodule_progress = min(self.nodule_progress, 100)
            
            if self.nodule_progress > 0.1:
                self.nodule_progress = round(self.nodule_progress, 1)

            if self.verbosity:
                count +=1
                if count % 50 == 0 and self.verbosity > 8:
                    print(count, flush=True)
                elif count % 500 == 0 and self.verbosity > 4:
                    print(count, flush=True)
                elif count % 1000 == 0 and self.verbosity > 2:
                    print(count, flush=True)
                elif count % 5000 == 0 and self.verbosity > 1:
                    print(count, flush=True)

        self.nodule_progress = 100

        if self.verbosity:
            print("ran nodule predictions...", flush=True)

        nlp_df = pd.DataFrame(nodule_nlp_out, columns=['KL_ID', 'NLP_OUT'])
        expanded_y_pred = nlp_df.apply(extract_prodigy_vals, axis=1, col_name="NLP_OUT", result_type="expand")

        self.data_in["Nodule_on_CT_NLP_score"] = expanded_y_pred[1]
        self.data_in["Nodule_on_CT_NLP_rec"] = self.data_in["Nodule_on_CT_NLP_score"] > 0.5

        # 3. Finally, followup
        followup_nlp_out = []
        count = 0
        for doc, ctx in followup_nlp.pipe(list(self.data_in[['IMPRESSION', 'KL_ID']].to_records(index=False)),
                                            as_tuples=True, batch_size=self.batch_size, n_process=1):
            out_ = doc.cats
            followup_nlp_out.append([ctx, json.dumps(out_, indent = 2)])

            self.followup_progress += 1/file_len * 100
            
            # just make sure we don't go over 100
            # self.followup_progress = min(self.followup_progress, 100)
            
            if self.followup_progress > 0.1:
                self.followup_progress = round(self.followup_progress, 1)

            if self.verbosity:
                count +=1
                if count % 50 == 0 and self.verbosity > 8:
                    print(count, flush=True)
                elif count % 500 == 0 and self.verbosity > 4:
                    print(count, flush=True)
                elif count % 1000 == 0 and self.verbosity > 2:
                    print(count, flush=True)
                elif count % 5000 == 0 and self.verbosity > 1:
                    print(count, flush=True)

        self.followup_progress = 100

        if self.verbosity:
            print("ran followup predictions...", flush=True)
                
            count +=1        

        nlp_df = pd.DataFrame(followup_nlp_out, columns=['KL_ID', 'NLP_OUT'])
        score_df = nlp_df.apply(convert_dict_str_to_dict, axis=1, col_name="NLP_OUT", result_type="expand")
        nlp_df = pd.concat([nlp_df, score_df], axis=1)
        nlp_df['FOLLOWUP_pred'] = nlp_df[["NO_FOLLOWUP","HARD_FOLLOWUP", "CONDITIONAL_FOLLOWUP"]].idxmax(axis=1)
        data_in_with_scores = self.data_in.merge(nlp_df, on="KL_ID", how='left')        
        data_in_with_scores = data_in_with_scores.drop("NLP_OUT", axis=1)

        print(data_in_with_scores['FOLLOWUP_pred'].value_counts(normalize=True))

        fname, ext = os.path.splitext(self.input_file)


        # Write predictions out to file
        fname, ext = os.path.splitext(self.input_file)

        if ext[1:] == "tsv":
            data_in_with_scores.to_csv(fname + "_predictions" + ext, index=False, sep="\t")    
        elif ext[1:] == "xls" or ext[1:] == "xlsx":
            data_in_with_scores.to_excel(fname + "_predictions" + ext, index=False)    
        elif ext[1:] == "csv":
            data_in_with_scores.to_csv(fname + "_predictions" + ext, index=False)
        else:
            data_in_with_scores.to_csv(fname + "_predictions.csv", index=False)
                
    def get_file_length(self):
        return self.data_in.shape[0]

