#!/usr/bin/env python3

import os
import sys
import random
import logging
from copy import copy
from datetime import datetime, timezone, timedelta, date, time
from collections import defaultdict
from typing import List, Iterator, Dict

import click

from aw_core.models import Event

from aw_client import ActivityWatchClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


hostname = "fakedata"
client_name = "aw-fakedata"

bucket_window = "aw-watcher-window_" + hostname
bucket_afk = "aw-watcher-afk_" + hostname
bucket_browser_chrome = "aw-watcher-web-chrome_fakedata"
bucket_browser_firefox = "aw-watcher-web-firefox_fakedata"

now = datetime.now(tz=timezone.utc)


@click.command("aw-fakedata")
@click.option("--since", type=click.DateTime(formats=["%Y-%m-%d"]))
@click.option("--until", type=click.DateTime(formats=["%Y-%m-%d"]))
def main(since: datetime, until: datetime = None):
    client = setup_client()

    if not until:
        until = now
    else:
        until = until.replace(tzinfo=timezone.utc)

    if not since:
        since = until - timedelta(days=14)
    else:
        since = since.replace(tzinfo=timezone.utc)

    print(f"Range: {since} to {until}")
    generate(client, since, until)


def setup_client() -> ActivityWatchClient:
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
    buckets_all = [
        bucket_afk,
        bucket_window,
        bucket_browser_chrome,
        bucket_browser_firefox,
    ]

    if not testing:
        ans = input(
            f"Running in prod, are you sure you want to delete all existing buckets?\n{buckets_all}\nAre you sure? (y/N)"
        )
        if ans != "y":
            print("Exiting")
            sys.exit(0)

    for bucket in [
        bucket_window,
        bucket_afk,
        bucket_browser_chrome,
        bucket_browser_firefox,
    ]:
        if bucket in buckets:
            client.delete_bucket(bucket, force=True)

    client.create_bucket(bucket_window, "currentwindow")
    client.create_bucket(bucket_afk, "afkstatus")

    client.create_bucket(bucket_browser_chrome, "web.tab.current")
    client.create_bucket(bucket_browser_firefox, "web.tab.current")

    client.connect()
    return client


# Sample window event data with weights
sample_data_afk: List[dict] = [
    {"status": "afk", "$weight": 30},
    {"status": "not-afk", "$weight": 20},
]

sample_data_window: List[dict] = [
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
    {"app": "Chrome", "title": "Unknown site", "$weight": 5},
]

sample_data_browser: List[dict] = [
    {"title": "GitHub", "url": "https://github.com", "$weight": 10},
    {"title": "Twitter", "url": "https://twitter.com", "$weight": 3},
]


def random_events(
    start: datetime, stop: datetime, sample_data: List[dict], max_event_duration=300
) -> List[Event]:
    """Randomly samples events from sample data"""
    events = []

    ts = start
    while ts < stop:
        data = copy(
            random.choices(sample_data, weights=[d["$weight"] for d in sample_data])[0]
        )

        # Ensure event doesn't spill over
        end = min(stop, ts + timedelta(seconds=random.random() * max_event_duration))

        e = Event(
            timestamp=ts,
            duration=end - ts,
            data=data,
        )
        events += [e]
        ts += e.duration

    return events


def daterange(d1: datetime, d2: datetime, inclusive=False) -> Iterator[date]:
    ts = d1
    while ts < d2:
        yield ts.date()
        ts += timedelta(days=1)
    if inclusive:
        yield ts.date()


def generate(client, start: datetime, end: datetime):
    print("Generating fake window events")
    buckets = generate_days(start, end)

    for bucketid, events in buckets.items():
        client.send_events(bucketid, events)
        print(f"Sent {len(events)} to bucket {bucketid}")


def generate_days(start: datetime, stop: datetime) -> Dict[str, List[Event]]:
    buckets: Dict[str, List[Event]] = defaultdict(list)
    for day in daterange(start, stop, inclusive=True):
        for bucket, events in generate_day(day).items():
            buckets[bucket] += events
    return buckets


def generate_day(day: date) -> Dict[str, List[Event]]:
    # Select a random day start and stop
    day_offset = timedelta(hours=6)
    start = datetime.combine(day, time()).replace(tzinfo=timezone.utc) + day_offset
    day_duration = timedelta(hours=4 + 8 * random.random())
    stop = start + day_duration

    return generate_activity(start, stop)


def generate_afk(start: datetime, stop: datetime) -> List[Event]:
    # FIXME: Randomly generates non-afk events in sequence, should alternate
    return random_events(start, stop, sample_data_afk, max_event_duration=120 * 60)


def generate_browser(start: datetime, stop: datetime) -> List[Event]:
    return random_events(start, stop, sample_data_browser)


def generate_activity(start, end) -> Dict[str, List[Event]]:
    # Generate an AFK event and containing window events
    events_afk = generate_afk(start, end)
    events_window = []
    events_browser_chrome = []
    events_browser_firefox = []

    for event in events_afk:
        if event.data["status"] == "not-afk":
            events_window += random_events(
                event.timestamp, event.timestamp + event.duration, sample_data_window
            )

    for event in events_window:
        if event.data["app"].lower() == "firefox":
            events_browser_firefox += generate_browser(
                event.timestamp, event.timestamp + event.duration
            )
        if event.data["app"].lower() == "chrome":
            events_browser_chrome += generate_browser(
                event.timestamp, event.timestamp + event.duration
            )

    return {
        bucket_window: events_window,
        bucket_afk: events_afk,
        bucket_browser_chrome: events_browser_chrome,
        bucket_browser_firefox: events_browser_firefox,
    }


if __name__ == "__main__":
    main()
