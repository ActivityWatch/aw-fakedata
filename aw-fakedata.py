#!/usr/bin/env python3

import random
import logging
from time import sleep
from copy import copy
from datetime import datetime, timezone, timedelta

from aw_core.models import Event

from aw_client import ActivityWatchClient

hostname = "fake-data"
window_bucket_name = "aw-watcher-window-testing_"+hostname
afk_bucket_name = "aw-watcher-afk-testing_"+hostname

def delete_prev_buckets():
    logging.info("Deleting old buckets")
    client = ActivityWatchClient("aw-fake-client", testing=True)
    client.client_hostname = hostname
    client.connect()
    client.delete_bucket(window_bucket_name)
    client.delete_bucket(afk_bucket_name)


def setup_client():
    logging.info("Setting up client")
    client = ActivityWatchClient("aw-fake-client", testing=True)
    client.client_hostname = hostname

    eventtype = "currentwindow"
    client.setup_bucket(window_bucket_name, eventtype)

    eventtype = "afkstatus"
    client.setup_bucket(afk_bucket_name, eventtype)

    client.connect()
    return client

def window_events(client, start_date, end_date):
    print("Generating fake window events")

    template_window_events = []
    for app_i in range(4):
        appname = "App "+str(app_i)
        for title_i in range(10):
            title = "Title "+str(title_i)
            e = Event(label=appname, timestamp=start_date, keyvals={"title": title})
            template_window_events.append(e)
    ts = start_date
    window_events = []
    batch_size = 5000
    count = 0
    while ts < end_date:
        event_duration = 25
        e = copy(random.choice(template_window_events))
        e.timestamp = ts
        e.duration = timedelta(seconds=event_duration)
        window_events.append(e)
        ts += timedelta(seconds=event_duration)
        count += 1
        if count % batch_size == 0:
            client.send_events(window_bucket_name, window_events)
            window_events = []
            sleep(0.05)
    client.send_events(window_bucket_name, window_events)

    print("Sent {} window events".format(count))

def afk_events(client, start_date, end_date):
    print("Generating fake afk events")
    interval = 3000
    base_event = Event(label="not-afk", timestamp=start_date, duration=timedelta(seconds=interval))
    afk_events = []
    ts = start_date
    afk_events = []
    while ts < end_date:
        e = copy(base_event)
        e.timestamp = ts-timedelta(seconds=1)
        ts += timedelta(seconds=interval)
        afk_events.append(e)
    print("Sending {} afk events".format(len(afk_events)))
    client.send_events(afk_bucket_name, afk_events)

if __name__ == '__main__':
    delete_prev_buckets()
    start_date = datetime.now(timezone.utc) - timedelta(hours=7)
    end_date = datetime.now(timezone.utc)
    print(start_date)
    print(end_date)

    client = setup_client()
    window_events(client, start_date, end_date)
    afk_events(client, start_date, end_date)

    # Sleep so client dispatcher has time to send events
    sleep(10)
