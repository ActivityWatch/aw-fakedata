#!/usr/bin/env python3

"""
File should be self-contained, as it's run by simple `wget .../fakedata.py; python3 fakedata.py` from actions like ActivityWatch/setup-action and integration tests.
"""

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
bucket_browser_chrome = "aw-watcher-web-chrome_" + hostname
bucket_browser_firefox = "aw-watcher-web-firefox_" + hostname

now = datetime.now(tz=timezone.utc)


@click.command("aw-fakedata")
@click.option("--since", type=click.DateTime(formats=["%Y-%m-%d"]))
@click.option("--until", type=click.DateTime(formats=["%Y-%m-%d"]))
def main(since: datetime = None, until: datetime = None):
    """
    Generates fake data for used in testing of ActivityWatch.

    Will run in testing mode by default, can be overridden with the env var AW_TESTING.
    """
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

    if not testing and sys.stdin.isatty():
        ans = input(
            f"Running in prod, are you sure you want to delete the existing buckets?\n{buckets_all}\nAre you sure? (y/N) "
        )
        if ans != "y":
            print("Exiting")
            sys.exit(0)

    for bucket in buckets_all:
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
    {"status": "not-afk", "$weight": 1, "$duration": 120},
    {"status": "afk", "$weight": 1, "$duration": 10},
]

# $weight controls the likelihood of being picked.
# $duration can be optionally set to the expected number of minutes per event.
sample_data_window: List[dict] = [
    # Meetings
    # Should be ~30min every other day
    {
        "app": "zoom",
        "title": "Zoom Meeting",
        "$weight": 3,
        "$duration": 20,
    },
    # Games
    # Should be ~60min every week
    {"app": "Minecraft", "title": "Minecraft", "$weight": 2, "$duration": 200},
    # ActivityWatch-related
    # Should be ~60% of time
    {
        "app": "Firefox",
        "title": "ActivityWatch/activitywatch: Track how you spend your time - github.com/",
        "$weight": 20,
        "$duration": 5,
    },
    {
        "app": "Terminal",
        "title": "vim ~/code/activitywatch/other/aw-fakedata",
        "$weight": 10,
    },
    {
        "app": "Terminal",
        "title": "vim ~/code/activitywatch/README.md",
        "$weight": 3,
        "$duration": 5,
    },
    {"app": "Terminal", "title": "vim ~/code/activitywatch/aw-server", "$weight": 5},
    {"app": "Terminal", "title": "bash ~/code/activitywatch", "$weight": 5},
    # Misc work
    # Should be ~20% of work
    {
        "app": "Firefox",
        "title": "Gmail - mail.google.com/",
        "$weight": 5,
        "$duration": 10,
    },
    {
        "app": "Firefox",
        "title": "Stack Overflow - stackoverflow.com/",
        "$weight": 10,
        "$duration": 5,
    },
    {
        "app": "Firefox",
        "title": "Google Calendar - calendar.google.com/",
        "$weight": 5,
        "$duration": 2,
    },
    # Social media
    # Should be ~30min/day
    {
        "app": "Firefox",
        "title": "reddit: the front page of the internet - reddit.com/",
        "$weight": 10,
        "$duration": 10,
    },
    {
        "app": "Firefox",
        "title": "Home / Twitter - twitter.com/",
        "$weight": 10,
        "$duration": 8,
    },
    {
        "app": "Firefox",
        "title": "Facebook - facebook.com/",
        "$weight": 10,
        "$duration": 3,
    },
    {"app": "Chrome", "title": "Unknown site", "$weight": 2},
    # Media
    # Should be ~1h/month
    {"app": "Spotify", "title": "Spotify", "$weight": 8, "$duration": 3},
    {
        "app": "Chrome",
        "title": "YouTube - youtube.com/",
        "$weight": 4,
        "$duration": 25,
    },
]

sample_data_browser: List[dict] = [
    {"title": "GitHub", "url": "https://github.com", "$weight": 10, "$duration": 10},
    {"title": "Twitter", "url": "https://twitter.com", "$weight": 3, "$duration": 5},
    {"title": "YouTube", "url": "https://youtube.com", "$weight": 5, "$duration": 20},
]


def random_events(
    start: datetime,
    stop: datetime,
    sample_data: List[dict],
    duration_max_default: float = 120 * 60,
) -> List[Event]:
    """Randomly samples events from sample data"""
    events = []

    ts = start
    while ts < stop:
        data = copy(
            random.choices(sample_data, weights=[d["$weight"] for d in sample_data])[0]
        )

        if "$duration" in data:
            duration = timedelta(minutes=random.uniform(0.5, 2) * data["$duration"])
        else:
            duration = timedelta(seconds=random.uniform(5, duration_max_default))

        # Ensure event doesn't spill over
        end = min(stop, ts + duration)

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

    # Seed the rng to get replicable results.
    # Identical input parameters should get identical outputs.
    random.seed(start.timestamp() + end.timestamp())
    buckets = generate_days(start, end)

    for bucketid, events in buckets.items():
        client.insert_events(bucketid, events)
        print(f"Sent {len(events)} to bucket {bucketid}")


def generate_days(start: datetime, stop: datetime) -> Dict[str, List[Event]]:
    buckets: Dict[str, List[Event]] = defaultdict(list)
    for day in daterange(start, stop, inclusive=True):
        for bucket, events in generate_day(day).items():
            buckets[bucket] += events
    return buckets


def generate_day(day: date) -> Dict[str, List[Event]]:
    # Select a random day start and stop
    day_offset = timedelta(hours=8)
    start = datetime.combine(day, time()).replace(tzinfo=timezone.utc) + day_offset
    is_workday = day.isoweekday() in range(1, 6)
    if is_workday:
        day_duration = timedelta(hours=5 + 5 * random.random())
    else:
        # Weekend
        day_duration = timedelta(hours=1 + 4 * random.random())
    # print(day_duration)
    stop = start + day_duration

    # TODO: Add lunchbreak by splitting generate_activity into thw
    break_start = start + (stop - start) / 2
    break_duration = timedelta(minutes=random.uniform(60, 120))
    break_stop = break_start + break_duration

    return merge_activity(
        generate_activity(start, break_start),
        generate_activity(break_stop, stop + break_duration),
    )


def merge_activity(d1, d2):
    dres = defaultdict(list)
    dres.update(d1)
    for k in d2:
        dres[k].extend(d2[k])
    return dres


def generate_afk(start: datetime, stop: datetime) -> List[Event]:
    # FIXME: Randomly generates non-afk events in sequence, should alternate
    return random_events(start, stop, sample_data_afk)


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
