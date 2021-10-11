import requests
import logging
import math
import os
import json
import pytz
from datetime import datetime

class TogglHelper(object):
    def __init__(
            self, 
            directory:str, 
            word_list_source:"str | dict",
            manual_connections:set,
            use_only_connected_words:bool=False,
            db_strategy:str='as_needed',
            channel:str='dev', 
            cache_dir:str='input/', 
            output_dir:str='output/', 
            input_dir:str='input/', 
            dump_file_name:str='enwiktionary-latest-pages-articles.xml',
            store_intermediates:bool=False,
            bad_connections:set=set(),
            affix_source:str='prod',
        ):
        """
        To change language data, modify the cache files that are loaded by these modules
        All freq data is from cache
        TODO: Need to test use_only_connected_words to ensure data is removed

        Parameters
            channel: The channel of etymology_explorer to run this on. Should usually be dev or test. Options are `test`, `dev`, `staging`, `prod`
            cache_dir: caches for the wikitext template expansions
            output_dir: location of processed wikidump files
            store_intermediates: whether to keep intermediate values, for troubleshooting
            word_list_source (str | dict): where to get wl_2_id from
                cache: use data/wiktionary/input/wl_2_id.cache
                {channel}: load mysql data from etymology_explorer_{channel}.etymologies table
                none: don't load wl_2_id, and let it populate
                {typeof dict}: use this wl_2_id dict
            manual_connections: set of (desc_wl, root_wl) saved in cache
            use_only_connected_words: whether to trim down the data to only include that
                which is connected to the initial provided wl_2_id list. Connections through
                roots or descendants. All other data is removed after the connection_sources_dl 
                is created
            db_strategy (str): how to manage the database for inserting data
                reinitialize: drop the db and create from the mysql statement file
                as_needed(default): drop tables when needed
                diff: only perform removes and updates as needed (TODO: Implement)
                none: make no changes to the db (just gather the data)
            bad_connections (set of wl or id tuples(desc_wl or id, root_wl or id)): list of connections that should
                not be added.
            manual_connections (set of wl or id tuples(desc_wl or id, root_wl or id)): list of connections that should
                be added.
            affix_source (str [{stage}, own(default), none]): where to get the base list of affixes. 
                Will pull them from mysql and store them in self.affix_dl which is used to update the 
                mysql at the end of the process (post colab)
        """
            # language_source (str): where to go for language_dict data
            # 	web: load wiktionary's language data (normal list and etymology-only)
            # 	cache: use data/wiktionary/input/LC_2_LN.cache etc.
            # 	{channel}: load mysql data from etymology_explorer_{channel}.languages
        if cache_dir and cache_dir[-1] != '/': raise Exception('`Cache_dir` must end in `/` if provided')
        if output_dir and output_dir[-1] != '/': raise Exception('`Output_dir` must end in `/` if provided')
        if input_dir and input_dir[-1] != '/': raise Exception('`Input_dir` must end in `/` if provided')
        if directory[-1] != '/': raise Exception('`directory` must end in `/` ')

        self.manual_connections = manual_connections
        self.bad_connections = bad_connections
        self.store_intermediates = store_intermediates
        self.cache_path = directory+cache_dir if cache_dir else None
        self.output_path = directory+output_dir if output_dir else None
        self.input_path = directory+input_dir if input_dir else None
        self.dump_file_name = dump_file_name
        self.channel = channel
        self.test = self.channel == 'test'
        self.word_list_source = word_list_source
        self.db_strategy = db_strategy
        self.use_only_connected_words = use_only_connected_words
        self.affix_source = affix_source

def get_all_tasks(start, end=None):
    """
    Provide datetime starts and ends
    https://github.com/toggl/toggl_api_docs/blob/master/reports.md#request-parameters
    """
    url = 'https://api.track.toggl.com/reports/api/v2/details'
    params = {
        'user_agent':'declan@highcountrydev.com', 
        'workspace_id':'5548648', 
        'since':start,
    }
    if end != None:
        params['until'] = end
    resp = requests.get(url, params, auth=(os.environ['TOGGL_API_TOKEN'],'api_token'))
    resp_json = resp.json()
    pages = math.ceil(resp_json.get('total_count', 0) / resp_json.get('per_page', 50))
    tasks = add_est(resp_json.get('data', []))
    logging.info(f'Found {pages} pages')
                      
    # This will skip first page, since we already have it
    for page in range(2, pages + 1):
        logging.info(f'Requesting page {page}')
        new_resp = requests.get(url, {**params, 'page':page}, auth=(os.environ['TOGGL_API_TOKEN'],'api_token'))
        new_resp_json = new_resp.json()
        tasks += add_est(new_resp_json.get('data', []))
        
    return tasks

def sum_task_time_minutes(tasks):
    """returns the number of minutes of tasks"""
    return sum(t.get('dur',0) for t in tasks)/1000/60

def sum_task_time_hours(tasks, digits=2):
    """returns the number of minutes of tasks"""
    return round(sum_task_time_minutes(tasks)/60,digits)

def set_tags_on_time_entry(time_entry_id, tags):
    if type(tags) != list:
        raise Exception('must provide list of tags to add')
    url = f'https://api.track.toggl.com/api/v8/time_entries/{time_entry_id}'
    data = {
        "time_entry":{
            "tags":tags,
            'user_agent':'declan@highcountrydev.com', 
            'workspace_id':'5548648', 
        }
    }
    resp = requests.put(url, json.dumps(data), auth=(os.environ['TOGGL_API_TOKEN'],'api_token'))
    return resp.json()

def set_tags_on_tasks(task_id_2_tags, log=False):
    """Provide a dict of tags for each task_id: {2171905751: ['Paid by Client']}"""
    logging.info(f'updating {len(task_id_2_tags)} tasks')
    for i, (task_id, tags) in enumerate(task_id_2_tags.items()):
        if type(tags) != list:
            raise Exception('tags must be a list')
            
        set_tags_on_time_entry(task_id, tags)
        if log: print(f'\rUpdated {i+1}/{len(task_id_2_tags)}', end='')
