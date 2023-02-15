# Yale Moore CT ILN Followup

This is the souce code for the Docker container containing a transformer (RoBERTa)-based model to predict whether after receiving a CT in the ED, a potential incidental lung nodule finding (ILN) will require a followup or not. We classify into three classes `NO_FOLLOWUP`, `CONDITIONAL_FOLLOWUP`, and `HARD_FOLLOWUP`. The formal definitions are below:

**HARD_FOLLOWUP**: The patient definitively should get a followup visit for a possible ILN   
**CONDITION_FOLLOWUP**: The patient may or may not need a followup visit for a possible ILN   
**NO_FOLLOWUP**: The patient does not need a followup visit for a possible ILN   

The model was trained on Yale-New Haven Health System ED CT reports from 2014-2021. 

![alt text](https://github.com/vsocrates/moore-followup-docker/blob/main/images/screenshot-2.png)

# To Use

In order to use this model: 

1. First pull the container from Docker Hub using Docker Hub Desktop. 
2. Make sure that your local file containing the CT reports has two columns called `CT_text` and `ID`.
3. Look for and pull down a docker container called `vsocrates/moore` and use the following settings. Change the Volumes => Host Path to the path to the folder containing your input data. 

![Container Settings](https://github.com/vsocrates/moore-followup-docker/blob/main/images/container-settings.png)

Our model is located on [Docker Hub](https://hub.docker.com/repository/docker/vsocrates/moore/general) with further details and our model training code is located at https://github.com/vsocrates/moore-followup. 
