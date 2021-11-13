import json
import logging
import math
import os
import time
from collections import Counter
from datetime import datetime, timedelta

import pytz
import requests

# TODO: CHECK FOR TAG ACCURACY (on load) AND USE ENUM when using the tag
# TODO: What is the detail of the unpaid hours from Sean? How can I describe the work that we have done for him
# TODO: Specify the time of start as midnight


# Utility functions

def days_ago(days):
    # return datetime.now() - timedelta(days=days)
    return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days)

def unpaid_by_client(task): 
    return [t for t in task if 'Paid by Client' not in t.get('tags')]

def unpaid_to_contractor(task): 
    return [t for t in task if 'Paid to Contractor' not in t.get('tags')]

def add_est ( task ): 
    return [
        {
            **t, 
            'start_est':datetime.fromisoformat(t['start']).astimezone(pytz.timezone("US/Eastern")),
            'end_est':datetime.fromisoformat(t['end']).astimezone(pytz.timezone("US/Eastern")),
        } 
        for t
        in task
    ]

def sum_task_time_minutes(tasks):
    """returns the number of minutes of tasks"""
    return sum(t.get('dur',0) for t in tasks)/1000/60

def sum_task_time_hours(tasks, digits=2):
    """returns the number of minutes of tasks"""
    return round(sum_task_time_minutes(tasks)/60,digits)

def readable_date(date, day_of_week=False):
    if (not date): 
        return 'None'
    if day_of_week:
        return date.strftime('%a %m-%d %H:%M')

    return date.strftime('%m-%d %H:%M')

def day(s):
    """provide string in form 10-30-21"""
    return datetime.strptime(s, '%m-%d-%y')

def get_task_info(tasks):
    due_f_client_hr = sum_task_time_hours(unpaid_by_client(tasks))
    due_t_contractor_hr = sum_task_time_hours(unpaid_to_contractor(tasks))
    users = Counter(t['user'] for t in tasks)
    clients = Counter(t['client'] for t in tasks)
    tags = Counter(tag for task in tasks for tag in task['tags'])
    last = max([ t['start_est'] for t in tasks ], default=None)
    first = min([ t['start_est'] for t in tasks ], default=None)
    hours = sum_task_time_hours(tasks)
    return users, clients, tags, first, last, hours, due_f_client_hr, due_t_contractor_hr

def time(t:str):
    return datetime.strptime( t, '%m-%d-%y %H:%M')

def color(text, color):
	e = '\x1b[0m'
	c = {
		'red': '\x1b[1;31m',
		'red_light':'\x1b[31m',
		'teal':'\x1b[1;96m',
		'teal_light': '\x1b[96m',
		'purple': '\x1b[1;95m',
		'purple_light': '\x1b[95m',
		'blue': '\x1b[1;94m',
		'blue_light': '\x1b[94m',
		'black': '\x1b[1;30m',
	}
	if not color in c: raise Exception(f'No color for {color}')
	return f'{c[color]}{text}{e}'


DEFAULT_START = days_ago(30)
DEFAULT_END = None

class TogglHelper(object):
    def __init__( 
        self, 
        start=None, 
        end=None,
        user_agent='declan@highcountrydev.com' ,
        workspace_id='5548648',
    ): 
        """
        start: datetime
        """
        self.start = start or DEFAULT_START
        self.end = end or DEFAULT_END
        self.user_agent = user_agent
        self.workspace_id = workspace_id
        self.toggl_api_token = os.environ['TOGGL_API_TOKEN']
        self.session = requests.Session()
        self.tasks = self._get_all_tasks(start=self.start, end=self.end)
        self.users = set(t.get('user') for t in self.tasks)
        self.tags = set(tag for task in self.tasks for tag in task.get('tags') )
        self.clients = {s for s in set(t.get('client') for t in self.tasks) if s}
        self.print_summary()

    def _print_task_summary(self,tasks, start, end):
        start_str = readable_date(start or self.start)
        end_str = readable_date(end or self.end)
        print(f'{len(tasks)} tasks since {start_str} to {end_str}')

        print('All', sum_task_time_hours(tasks), 'hours')

        print('----------------------------------')
        for user in self.users:
            user_tasks = [t for t in tasks if t.get('user')==user]
            unpaid_by_client_user_tasks = unpaid_by_client(user_tasks)
            unpaid_to_contractor_user_tasks = unpaid_to_contractor(user_tasks)
            
            print('All', user, sum_task_time_hours(user_tasks), 'hours')
            print('Unpaid by Client to', user, sum_task_time_hours(unpaid_by_client_user_tasks), 'hours')
            print('Unpaid to Contractor', user, sum_task_time_hours(unpaid_to_contractor_user_tasks), 'hours')
            print()
        print('----------------------------------')
        for client in self.clients:
            client_tasks = [t for t in tasks if t.get('client')==client]
            unpaid_by_client_client_tasks = unpaid_by_client(client_tasks)
            unpaid_to_contractor_client_tasks = unpaid_to_contractor(client_tasks)
            
            print('All', client, sum_task_time_hours(client_tasks), 'hours')
            print('Unpaid by Client', client, sum_task_time_hours(unpaid_by_client_client_tasks), 'hours')
            print('Unpaid to Contractor by', client, sum_task_time_hours(unpaid_to_contractor_client_tasks), 'hours')
            print()


    def print_summary(self, start=None, end=None):
        """
        Gets the tasks if different start and end, then prints out details on them
        """
        tasks = self.get_temp_tasks_for_start_and_end(start, end)
        self._print_task_summary(tasks, start or self.start, end or self.end)

    def abbreviated_str(self, entity, tasks):
        users, clients, tags, first, last, hours, due_f_client_hr, due_t_contractor_hr = get_task_info(tasks)
        string = f'{entity}'+\
            f':{color(readable_date(first),"purple")} TO {color(readable_date(last),"purple")}; '+\
            f'all {color(hours,"black")}h; '+\
            f'due: by cli {color(due_f_client_hr,"blue")}h, '+\
            f'to con {color(due_t_contractor_hr,"red")}h'
        return string

    def print_user_summary(self, user, start=None, end=None):
        tasks = self.get_temp_tasks_for_start_and_end(start, end)
        # start_str = readable_date(start or self.start)
        # end_str = readable_date(end or self.end)

        user_tasks = self._get_user_subset_of_tasks(user, tasks)
        # unpaid_by_client_user_tasks = unpaid_by_client(user_tasks)
        # unpaid_to_contractor_user_tasks = unpaid_to_contractor(user_tasks)
        print(self.abbreviated_str(user, user_tasks))
        # print(f'{user} has {len(user_tasks)} tasks since {start_str} to {end_str} for', sum_task_time_hours(user_tasks), 'hours')
        # print('Unpaid by Client to', user, sum_task_time_hours(unpaid_by_client_user_tasks), 'hours')
        # print('Unpaid to Contractor', user, sum_task_time_hours(unpaid_to_contractor_user_tasks), 'hours')
        print()

        for client in self.clients:
            client_tasks = [t for t in user_tasks if t.get('client')==client]
            print('For', self.abbreviated_str(client, client_tasks))
            # unpaid_by_client_client_tasks = unpaid_by_client(client_tasks)
            # unpaid_to_contractor_client_tasks = unpaid_to_contractor(client_tasks)
            
            # print('All', client, 'work by', user, sum_task_time_hours(client_tasks), 'hours')
            # print('Unpaid by Client', client, sum_task_time_hours(unpaid_by_client_client_tasks), 'hours')
            # print('Unpaid to Contractor by', client, sum_task_time_hours(unpaid_to_contractor_client_tasks), 'hours')

    def print_client_summary(self, client, start=None, end=None):
        tasks = self.get_temp_tasks_for_start_and_end(start, end)
        start_str = readable_date(start or self.start)
        end_str = readable_date(end or self.end)

        client_tasks = self._get_client_subset_of_tasks(client, tasks)
        unpaid_by_client_client_tasks = unpaid_by_client(client_tasks)
        unpaid_to_contractor_client_tasks = unpaid_to_contractor(client_tasks)
        print(f'{client} has {len(client_tasks)} tasks since {start_str} to {end_str} for', sum_task_time_hours(client_tasks), 'hours')
        print('Unpaid hours by Client', client, sum_task_time_hours(unpaid_by_client_client_tasks), 'hours')
        print('Unpaid hours to Contractors by', client, sum_task_time_hours(unpaid_to_contractor_client_tasks), 'hours')

        print()
        for user in self.users:
            user_tasks = [t for t in client_tasks if t.get('user')==user]
            unpaid_by_client_user_tasks = unpaid_by_client(user_tasks)
            unpaid_to_contractor_user_tasks = unpaid_to_contractor(user_tasks)
            
            print('All', client, 'work by', user, sum_task_time_hours(user_tasks), 'hours')
            print('Unpaid by Client to', user, sum_task_time_hours(unpaid_by_client_user_tasks), 'hours')
            print('Unpaid to Contractor', user, sum_task_time_hours(unpaid_to_contractor_user_tasks), 'hours')
            print()

    def _get_all_tasks(self, start=None, end=None):
        """
        Provide datetime starts and ends
        https://github.com/toggl/toggl_api_docs/blob/master/reports.md#request-parameters
        """
        url = 'https://api.track.toggl.com/reports/api/v2/details'
        params = {
            'user_agent':'declan@highcountrydev.com', 
            'workspace_id':'5548648', 
            'since':start or self.start,
        }
        if end != None:
            params['until'] = end
        resp = self.session.get(url, params=params, auth=(self.toggl_api_token,'api_token'))
        resp_json = resp.json()
        pages = math.ceil(resp_json.get('total_count', 0) / resp_json.get('per_page', 50))
        tasks = add_est(resp_json.get('data', []))
        logging.info(f'Found {pages} pages')
                        
        # This will skip first page, since we already have it
        for page in range(2, pages + 1):
            logging.info(f'Requesting page {page}')
            new_resp = self.session.get(url, params={**params, 'page':page}, auth=(self.toggl_api_token,'api_token'))
            new_resp_json = new_resp.json()
            tasks += add_est(new_resp_json.get('data', []))
            
        return tasks

    def update_all_tasks(self, new_start=None, new_end=None):
        if new_start: self.start=new_start
        if new_end: self.end=new_end

        # will use new self.start and new self.end
        self.tasks = self._get_all_tasks()

    def _set_tags_on_time_entry(self, time_entry_id, tags):
        if type(tags) != list:
            raise Exception('must provide list of tags to add')
        tries = 0
        while tries < 5:
            url = f'https://api.track.toggl.com/api/v8/time_entries/{time_entry_id}'
            data = {
                "time_entry":{
                    "tags":tags,
                    'user_agent':self.user_agent, 
                    'workspace_id':self.workspace_id, 
                }
            }
            resp = self.session.put(url, json.dumps(data), auth=(self.toggl_api_token,'api_token'))

            if resp.ok:
                return resp.json()

            elif resp.status_code == 429:
                print('–Too many requests, waiting 2 seconds...', 'attempt #', tries + 1)
            else:
                print('Unknown response error, waiting 5 seconds', resp.status_code, 'attempt #', tries + 1)
                time.sleep(5)
            time.sleep(2)
            tries += 1
        raise Exception(f'Request failed and exhausted all tries: { tries }, code: {resp.status_code}')

    def set_tags_on_tasks(self, task_id_2_tags, log=False):
        """Provide a dict of tags for each task_id: {2171905751: ['Paid by Client']}"""
        logging.info(f'updating {len(task_id_2_tags)} tasks')
        for i, (task_id, tags) in enumerate(task_id_2_tags.items()):
            if type(tags) != list:
                raise Exception('tags must be a list')
                
            self._set_tags_on_time_entry(task_id, tags)
            if log: print(f'\rUpdated {i+1}/{len(task_id_2_tags)}', end='')

    def record_contractor_payment(self, user, start=None, end=None):
        """
        start: if left None, will handle since beginning of self.all_tasks
        start: if left None, will handle since end of self.all_tasks
        """
        tasks = self.get_temp_tasks_for_start_and_end(start, end)

        user_tasks = self._get_user_subset_of_tasks(user, tasks)
        total_task_count = len(user_tasks)
        total_hours = sum_task_time_hours(user_tasks)

        # unpaid to contractor
        unpaid_user_tasks = unpaid_to_contractor(user_tasks) 
        unpaid_user_task_count = len(unpaid_user_tasks)
        unpaid_user_hours = sum_task_time_hours(unpaid_user_tasks)

        # paid to contractor
        paid_user_task_count = total_task_count - unpaid_user_task_count
        paid_user_hours = total_hours - unpaid_user_hours

        print( 'Recording payment to', user, 'starting', readable_date(start),'ending',readable_date(end))
        print( 'Payable tasks:', unpaid_user_task_count, 'tasks,',unpaid_user_hours,'hours.')
        print('Already paid tasks:', paid_user_task_count, 'tasks,' ,paid_user_hours,'hours.')

        if input('Continue (y/N)?') == 'y':
            task_id_2_tags={t['id']:list(set([*t['tags'],'Paid to Contractor'])) for t in unpaid_user_tasks}; task_id_2_tags
            self.set_tags_on_tasks(task_id_2_tags, log=True)

    def record_client_payment(self, client, start=None, end=None):
        """
        start: if left None, will handle since beginning of self.all_tasks
        start: if left None, will handle since end of self.all_tasks
        """
        tasks = self.get_temp_tasks_for_start_and_end(start, end)

        client_tasks = self._get_client_subset_of_tasks(client, tasks)
        total_task_count = len(client_tasks)
        total_hours = sum_task_time_hours(client_tasks)

        # unpaid by client
        unpaid_client_tasks = unpaid_by_client(client_tasks) 
        unpaid_client_task_count = len(unpaid_client_tasks)
        unpaid_client_hours = sum_task_time_hours(unpaid_client_tasks)

        # paid by client
        paid_client_task_count = total_task_count - unpaid_client_task_count
        paid_client_hours = total_hours - unpaid_client_hours

        print( 'Recording payment to', client, 'starting', readable_date(start),'ending',readable_date(end))
        print( 'Payable tasks:', unpaid_client_task_count, 'tasks,',unpaid_client_hours,'hours.')
        print('Already paid tasks:', paid_client_task_count, 'tasks,' ,paid_client_hours,'hours.')

        if input('Continue (y/N)?') == 'y':
            task_id_2_tags={t['id']:list(set([*t['tags'],'Paid by Client'])) for t in unpaid_client_tasks}; task_id_2_tags
            self.set_tags_on_tasks(task_id_2_tags, log=True)

    def get_task_descriptions(self, client=None, user=None, project=None, start=None, end=None, remove_paid_by_client=False, remove_paid_to_user=False):
        tasks = self.get_temp_tasks_for_start_and_end(start, end)
        if client:  tasks = self._get_client_subset_of_tasks(client, tasks)
        if remove_paid_by_client: tasks = unpaid_by_client(tasks)
        if user:  tasks = self._get_user_subset_of_tasks(user, tasks)
        if remove_paid_to_user: tasks = unpaid_to_contractor(tasks)

        self._print_task_summary(tasks, start or self.start, end or self.end)

        task_descriptions = {}
        for task in tasks:
            desc = task.get('description', 'No Description')
            t_client = task.get('client', 'None')
            t_user = task.get('user', 'None')
            t_project = task.get('project', 'None')
            current_data = task_descriptions\
                .setdefault(t_client, {})\
                .setdefault(t_user, {})\
                .setdefault(t_project, {})\
                .setdefault(desc, { 'hours':0, 'tasks':0, })

            task_descriptions[t_client][t_user][t_project][desc] = {
                'hours': current_data['hours'] + sum_task_time_hours([task]),
                'tasks': current_data['tasks'] + 1, 
            }

        for t_client, client_tasks in task_descriptions.items():
            for t_user, user_tasks in client_tasks.items():
                for t_project, project_tasks in user_tasks.items():
                    for t_desc, t_details in project_tasks.items():
                        print( 
                            "" if client else t_client.split()[0], 
                            "" if project else t_project.split()[0],
                            "" if user else t_user.split()[0],
                            t_details.get('tasks'),
                            # 'tasks', 
                            round(t_details.get('hours'),1),
                            'hr ##',
                            t_desc[:50],
                        )

    def get_temp_tasks_for_start_and_end(self, start, end):
        """ Get tasks for start and end. If both are none, then get default tasks"""
        if not start and not end:
            return self.tasks
        else:
            return self._get_all_tasks(start=( start or DEFAULT_START ), end=( end or DEFAULT_END ))


    def _get_user_subset_of_tasks(self, user, tasks):
        return [t for t in tasks if t.get('user')==user]

    def _get_client_subset_of_tasks(self, client, tasks):
        return [t for t in tasks if t.get('client')==client]

    def user_tasks(self, user): 
        return self._get_user_subset_of_tasks(self.tasks, user)

    def client_tasks(self, client): 
        return self._get_client_subset_of_tasks(self.tasks, client)
