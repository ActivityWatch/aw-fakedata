#!/usr/bin/env python3

import os
import random
import logging
from copy import copy
from datetime import datetime, timezone, timedelta, date, time
from typing import List, Iterator

from aw_core.models import Event

from aw_client import ActivityWatchClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


hostname = "fakedata"
window_bucket_name = "aw-watcher-window_" + hostname
afk_bucket_name = "aw-watcher-afk_" + hostname
client_name = "aw-fakedata"


def setup_client():
    logger.info("Setting up client")

    # Default is to run in testing mode, can be run in prod mode if set to exactly 'false'
    testing = os.getenv("AW_TESTING", "true").lower() not in ["false"]
    if testing:
        logger.info(
            "Using testing parameters (set the env var AW_TESTING to false to run in prod mode)"
        )

    client = ActivityWatchClient(client_name, testing=testing)
    client.client_hostname = hostname

    buckets = client.get_buckets()
    logger.info("Deleting old buckets")
    for bucket in [window_bucket_name, afk_bucket_name]:
        if bucket in buckets:
            client.delete_bucket(bucket)

    client.create_bucket(window_bucket_name, "currentwindow")
    client.create_bucket(afk_bucket_name, "afkstatus")

    client.connect()
    return client


# Sample window event data with weights
sample_data: List[dict] = [
    {"app": "zoom", "title": "Zoom Meeting", "$weight": 32},
    {"app": "Minecraft", "title": "Minecraft", "$weight": 25},
    {
        "app": "Firefox",
        "title": "ActivityWatch/activitywatch: Track how you spend your time - github.com/",
        "$weight": 23,
    },
    {
        "app": "Firefox",
        "title": "Home / Twitter - twitter.com/",
        "$weight": 11,
    },
    {
        "app": "Firefox",
        "title": "reddit: the front page of the internet - reddit.com/",
        "$weight": 13,
    },
    {
        "app": "Firefox",
        "title": "Stack Overflow - stackoverflow.com/",
        "$weight": 6,
    },
    {"app": "Terminal", "title": "vim ~/code/activitywatch/aw-server", "$weight": 15},
    {"app": "Terminal", "title": "bash ~/code/activitywatch", "$weight": 15},
    {
        "app": "Terminal",
        "title": "vim ~/code/activitywatch/other/aw-fakedata",
        "$weight": 10,
    },
    {"app": "Terminal", "title": "vim ~/code/activitywatch/README.md", "$weight": 10},
    {"app": "Spotify", "title": "Spotify", "$weight": 5},
]


def random_events(day: date):
    """Generates random window and AFK events for a single day"""
    day_offset = timedelta(hours=8)
    start = datetime.combine(day, time()).replace(tzinfo=timezone.utc) + day_offset
    day_duration = timedelta(hours=1 + 8 * random.random())
    stop = start + day_duration

    window_events = []
    max_event_duration = 60
    ts = start
    while ts < stop:
        data = copy(
            random.choices(sample_data, weights=[d["$weight"] for d in sample_data])[0]
        )
        e = Event(
            timestamp=ts,
            duration=timedelta(seconds=random.random() * max_event_duration),
            data=data,
        )
        window_events += [e]
        ts += e.duration

    afk_events = [
        Event(
            timestamp=start,
            duration=day_duration,
            data={"status": "not-afk"},
        )
    ]

    return window_events, afk_events


def daterange(d1: datetime, d2: datetime) -> Iterator[date]:
    ts = d1
    while ts < d2:
        yield ts.date()
        ts += timedelta(days=1)


def generate(client, start_date, end_date):
    print("Generating fake window events")
    count_window, count_afk = 0, 0
    for d in daterange(start_date, end_date):
        window_events, afk_events = random_events(d)
        client.send_events(window_bucket_name, window_events)
        client.send_events(afk_bucket_name, afk_events)
        count_window += len(window_events)
        count_afk += len(afk_events)

    print(f"Sent {count_window} window events")
    print(f"Sent {count_afk} AFK events")


if __name__ == "__main__":
    client = setup_client()

    start_date = datetime.now(timezone.utc) - timedelta(hours=24 * 30)
    end_date = datetime.now(timezone.utc)
    print(f"Range: {start_date} to {end_date}")

    generate(client, start_date, end_date)
