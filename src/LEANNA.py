import json
import pickle
import os.path
from enum import Enum
from json import JSONDecodeError
import random
from emora_stdm import DialogueFlow
from emora_stdm import Macro, Ngrams
from typing import Dict, Any, List, Callable, Pattern
import time
import re
import openai
import regexutils

PATH_API_KEY = 'resources/openai_api.txt'
openai.api_key_path = PATH_API_KEY


def visits() -> DialogueFlow:
    transition_visit = {
        'state': 'start',
        '`Hi, I\'m Leanna, your personal start-up consultant. At` #TIME `, I had the pleasure to meet '
        ' \n With time as our guide, our encounter was meant to be. May I know the name of future business tycoon?`': {
            '#SET_CALL_NAMES': {
                '`Nice to meet you, `$call_names `. Before we dive into business, '
                'I want to know how you are doing. Do you mind sharing to me your most exciting day in this week?`': {
                    '#SET_SENTIMENT': {
                        '#IF($sentiment=positive) `The user\'s sentiment is positive`': 'end',
                        '`The user input is unknow`': {
                            'state': 'end',
                            'score': 0.1
                        }
                    }
                }
            }
        }
    }

    macros = {
        'GET_CALL_NAME': MacroNLG(get_call_name),
        'SET_CALL_NAMES': MacroGPTJSON(
            'How does the speaker want to be called?',
            {V.call_names.name: ["Mike", "Michael"]}, V.call_names.name),
        'TIME': MacroTime(),
        'SET_SENTIMENT': MacroGPTJSON(
            'Among the three sentiments, negative, positive, and neutral, what is the speaker\'s sentiment?',
            {V.sentiment.name: ["positive"]}, V.sentiment.name),
        'GET_SENTIMENT': MacroNLG(get_sentiment)
    }

    df = DialogueFlow('start', end_state='end')
    df.load_transitions(transition_visit)
    df.add_macros(macros)
    return df


class V(Enum):
    call_names = 0  # str
    sentiment = 1


def gpt_completion(input: str, regex: Pattern = None) -> str:
    response = openai.ChatCompletion.create(
        model='gpt-3.5-turbo',
        messages=[{'role': 'user', 'content': input}]
    )
    output = response['choices'][0]['message']['content'].strip()

    if regex is not None:
        m = regex.search(output)
        output = m.group().strip() if m else None

    return output


class MacroGPTJSON(Macro):
    def __init__(self, request: str, full_ex: Dict[str, Any], field: str, empty_ex: Dict[str, Any] = None,
                 set_variables: Callable[[Dict[str, Any], Dict[str, Any]], None] = None):
        self.request = request
        self.full_ex = json.dumps(full_ex)
        self.empty_ex = '' if empty_ex is None else json.dumps(empty_ex)
        self.check = re.compile(regexutils.generate(full_ex))
        self.set_variables = set_variables
        self.field = field

    def run(self, ngrams: Ngrams, vars: Dict[str, Any], args: List[Any]):
        examples = f'{self.full_ex} or {self.empty_ex} if unavailable' if self.empty_ex else self.full_ex
        prompt = f'{self.request} Respond in the JSON schema such as {examples}: {ngrams.raw_text().strip()}'
        output = gpt_completion(prompt)
        if not output: return False

        try:
            d = json.loads(output)
        except JSONDecodeError:
            print(f'Invalid: {output}')
            return False

        if self.set_variables:
            self.set_variables(vars, d)
        else:
            vars.update(d)

        vars[self.field] = vars[self.field][0]

        return True


class MacroNLG(Macro):
    def __init__(self, generate: Callable[[Dict[str, Any]], str]):
        self.generate = generate

    def run(self, ngrams: Ngrams, vars: Dict[str, Any], args: List[Any]):
        return self.generate(vars)


def get_call_name(vars: Dict[str, Any]):
    ls = vars[V.call_names.name]
    return ls[random.randrange(len(ls))]


def get_sentiment(vars: Dict[str, Any]):
    ls = vars[V.sentiment.name]
    vars['sentiment'] = ls[random.randrange(len(ls))]
    print(vars['sentiment'])
    return ls[random.randrange(len(ls))]


class MacroTime(Macro):
    def run(self, ngrams: Ngrams, vars: Dict[str, Any], args: List[str]):
        current_time = time.strftime("%H:%M")
        return current_time


def save(df: DialogueFlow, varfile: str):
    d = {k: v for k, v in df.vars().items() if not k.startswith('_')}
    pickle.dump(d, open(varfile, 'wb'))


def load(df: DialogueFlow, varfile: str):
    d = pickle.load(open(varfile, 'rb'))
    df.vars().update(d)
    df.run()
    save(df, varfile)


if __name__ == '__main__':
    df = visits()
    # run save() for the first time,
    # run load() for subsequent times

    path = '/resources/visits.pkl'

    check_file = os.path.isfile(path)
    if check_file:
        load(df, 'resources/visits.pkl')
    else:
        df.run()
        save(df, 'resources/visits.pkl')
