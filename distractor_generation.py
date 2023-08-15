import re
import gensim.downloader as api
from gensim.models import KeyedVectors
from rapidfuzz.process import extract
from rapidfuzz.distance import Levenshtein

model_name = "word2vec-google-news-300"
model = api.load(model_name)
model = KeyedVectors.load('data/word2vec-google-news-300.model')

def clean_answer(answer: str) -> str:
    stage_0 = answer.split(' ')
    stage_1 = [val[0].isupper() for val in stage_0]
    if any(stage_1):
        stage_2 = answer.title()
    else:
        stage_2 = answer.lower()

    stage_3 = re.sub(' ', '_', stage_2)
    return stage_3


def clean_distractors(distractors: list(str), cleaned_answer: str) -> list(str):
    distractors = [re.sub('_|-',' ',value[0]) for value in distractors]
    # filter redundant distractors
    cleaned_distractors = [re.sub('\s+', ' ', value) for value in distractors]
    # remove distractors which contain answer (exact match)
    cleaned_distractors = [value for value in cleaned_distractors 
                           if value.lower() not in cleaned_answer.lower()]
    return cleaned_distractors


def filter_distractors(cleaned_distractors, cleaned_answer):
    filtered_distractors = extract(query=cleaned_answer, choices=cleaned_distractors,
                                   scorer=Levenshtein.distance, limit=None)
    filtered_distractors = list(filter(lambda y: y[1]>3, filtered_distractors))
    filtered_distractors.sort(key=lambda x: x[2])
    filtered_distractors = list(map(lambda x:x[0], filtered_distractors))
    return filtered_distractors


def generate_disctractors(answer):
    #answer = 'carbon dioxide'
    try:
        cleaned_answer = clean_answer(answer)
        distractors = model.most_similar(cleaned_answer, topn=20)

        cleaned_distractors = clean_distractors(distractors, cleaned_answer)
        filtered_distractors = filter_distractors(cleaned_distractors, cleaned_answer)    
        return filtered_distractors

    except KeyError:
        print('No matching word found in Word2Vec')
        return []