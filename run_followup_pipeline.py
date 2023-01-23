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
    def __init__(self, input_file, gpu = False, verbosiy = 10, batch_size = 50) -> None:

        self.input_file = input_file
        self.gpu = gpu
        self.verbosiy = verbosiy
        self.progress = 0
        self.batch_size = batch_size

        self.data_in = self.read_file()

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

        nlp = spacy.load("en_moore_followup")


        self.verbosity = 10

        if self.gpu:
            spacy.require_gpu()
            
        def convert_dict_str_to_dict(x, col_name):
            tmp = ast.literal_eval(x[col_name])
            return tmp
        

        if not "CT_text" in self.data_in.columns:
            raise KeyError("'CT_text' is not a column in your input data")

        if not "ID" in self.data_in.columns:
            raise KeyError("'ID' is not a column in your input data")

        _, ext = os.path.splitext(self.input_file)
        if ext[1:] not in ['csv', "tsv", "xlsx", "xls"]:
            raise ValueError(f"{ext} file type not supported")

        file_len = self.get_file_length()

        # Convert text into IMPRESSIONS only
        impressions = []
        for idx, text in self.data_in.loc[~self.data_in['CT_text'].isnull(), 'CT_text'].items():
            try:
                impression = text
                if re.search(r"IMPRESSION:|Impression:", text):
                    idx_start = re.search(r"IMPRESSION:|Impression:", text).start()
                else:
                    idx_start = 0
                impression = text[idx_start:]
                impressions.append(impression)
            except ValueError:
                impressions.append(impression)
                
        self.data_in.loc[~self.data_in['CT_text'].isnull(), 'CT_text_Impressions'] = impressions

        if self.verbosity:
            print("created impressions...", flush=True)
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
        nlp_out = []
        count = 0
        for doc, ctx in nlp.pipe(list(self.data_in.loc[~self.data_in['CT_text_Impressions'].isnull(), 
                                                ['CT_text_Impressions', 'ID']].to_records(index=False)),
                                            as_tuples=True, batch_size=self.batch_size, n_process=1):

            out_ = doc.cats
            nlp_out.append([ctx, json.dumps(out_, indent = 2)])
            
            self.progress += 1/file_len * 100
            
            # just make sure we don't go over 100
            # self.progress = min(self.progress, 100)
            
            if self.progress > 0.1:
                self.progress = round(self.progress, 1)

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

        self.progress = 100

        if self.verbosity:
            print("ran predictions...", flush=True)
                    
        df = pd.DataFrame(nlp_out, columns=['ID', 'NLP_OUT'])
                
        score_df = df.apply(convert_dict_str_to_dict, axis=1, col_name="NLP_OUT", result_type="expand")
        df = pd.concat([df, score_df], axis=1)
        df['y_pred'] = df[["NO_FOLLOWUP", "HARD_FOLLOWUP", "CONDITIONAL_FOLLOWUP"]].idxmax(axis=1)

        x = self.data_in.merge(df, on="ID", how='left')
        print(x['y_pred'].value_counts(normalize=True))

        x = x.drop("NLP_OUT", axis = 1)

        fname, ext = os.path.splitext(self.input_file)

        if ext[1:] == "tsv":
            x.to_csv(fname + "_predictions" + ext, index=False, sep="\t")    
        elif ext[1:] == "xls" or ext[1:] == "xlsx":
            x.to_excel(fname + "_predictions" + ext, index=False)    
        elif ext[1:] == "csv":
            x.to_csv(fname + "_predictions" + ext, index=False)
        else:
            x.to_csv(fname + "_predictions.csv", index=False)
                
    def get_file_length(self):
        return self.data_in.shape[0]

