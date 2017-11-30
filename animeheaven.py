#!/usr/bin/python3

import argparse
import itertools
import lxml.html
import os
import os.path
import re
import requests
import shutil
import sys
import tqdm


class LimitReachedError(Exception):
    pass


class AnimeHeaven:
    base_url = 'http://animeheaven.eu'
    anime_url = 'http://animeheaven.eu/i.php'  # a=<anime name>
    search_url = 'http://animeheaven.eu/search.php'  # q=<search query>
    watch_url = 'http://animeheaven.eu/watch.php'  # a=<anime name>&e=<episode>
    download_link_re = re.compile(r"<a class='an' href='(http[^']+)'>")

    @classmethod
    def search_anime(cls, search):
        def parse_info(element):
            episode_count = element.cssselect('.iepst2')[0].text
            anime_name = element.cssselect('.cona')[0].text

            return {
                'episodes': int(episode_count),
                'anime_name': anime_name,
                # 'anime_link': anime_link,
            }

        response = requests.get(cls.search_url, params={'q': search})
        response.raise_for_status()

        return map(
            parse_info,
            lxml.html.fromstring(response.text).cssselect('.iepcon'))

    @classmethod
    def get_info(cls, anime_name):
        response = requests.get(cls.anime_url, params={'a': anime_name})
        response.raise_for_status()

        episodes = lxml.html.fromstring(response.text).xpath(
            '//div[@class="textd" and text()="Episodes:"]'
        )[0].getnext().text

        return {
            'anime': anime_name,
            'episodes': int(episodes),
        }

    @classmethod
    def get_episode(cls, anime_name, episode):
        params = {
            'a': anime_name,
            'e': episode,
        }
        response = requests.get(cls.watch_url, params=params)
        response.raise_for_status()
        download_link = cls.download_link_re.search(response.text)

        if download_link is None:
            raise LimitReachedError

        return {
            'anime': anime_name,
            'episode': int(episode),
            'source': download_link[1],
        }


class Range:
    def __init__(self, low, high=None):
        self.low = low
        self.high = high

    def __call__(self, episodes):
        if self.high is None:
            return [self.low]
        else:
            return range(self.low, self.high)


class Latest:
    def __init__(self, range):
        self.range = range

    def __call__(self, episodes):
        if self.range < 0:
            return range(max(1, episodes + self.range), episodes + 1)
        elif self.range > 0:
            return range(self.range, episodes + 1)
        else:
            return [episodes]


class All:
    def __call__(self, episodes):
        return range(1, episodes + 1)


def selection_type(value):
    def get_range(value):
        try:
            [low, high] = value.split('-')

            if low == 'latest':
                return Latest(-int(high))
            elif high == 'latest':
                return Latest(int(low))
            else:
                return Range(int(low), int(high) + 1)
        except ValueError:
            if value == 'latest':
                return Latest(0)
            else:
                return Range(int(value))

    ranges = list(map(get_range, value.split(',')))

    def with_episode_count(episodes):
        return sorted(set(itertools.chain.from_iterable(
            [r(episodes) for r in ranges]
        )))

    return with_episode_count


def progress_bar(response):
    total_size = int(response.headers.get('content-length', 0))

    total_read = 0
    with tqdm.tqdm(
            total=total_size, unit='B',
            unit_scale=True, dynamic_ncols=True) as progress:
        for chunk in response.iter_content(2**16):
            progress.update(len(chunk))
            yield chunk


def download(anime, episode, dest_dir):
    log_entry = "{} - {:03d}".format(anime, episode)
    filename = "{} - {:03d}.mp4".format(anime, episode)
    dest_file = os.path.join(dest_dir, filename)

    if os.path.exists(dest_file):
        print("{}: Already downloaded".format(log_entry))
        return

    print("{}: Downloading".format(log_entry))

    try:
        info = AnimeHeaven.get_episode(anime, episode)

        with open(dest_file, 'wb') as output:
            response = requests.get(info['source'], stream=True)
            for chunk in progress_bar(response):
                output.write(chunk)

    except LimitReachedError:
        print("{}: Daily limit reached".format(log_entry))
        raise

    except BaseException as e:
        os.path.exists(dest_file) and os.remove(dest_file)
        print("{}: Download canceled".format(log_entry))

        if not isinstance(e, Exception):  # Re-raise keyboard interrupt
            raise


def main():
    argp = argparse.ArgumentParser()

    argp.add_argument('anime', help='Anime to search/download')
    argp.add_argument(
        '-d', '--download', dest='download', action='store_true',
        default=False, help='Download instead of search')
    argp.add_argument(
        '-D', '--dir', dest='dest_dir', default='.', help='Download directory')
    argp.add_argument(
        '-e', '--episodes', dest='episodes',
        type=selection_type, default=All(),
        help='Select episodes to download (e.g.: '
             '"1,2,7-9,11-22", "latest", "55-latest", '
             '"latest-5" for 5 latest episodes)')

    argp.epilog = """
AnimeHeaven.eu has relatively low daily request limit.
You can bypass this limit by using proxy server.
To use proxy server, just export `HTTP_PROXY` environment variable.
"""

    args = argp.parse_args()

    try:
        if args.download:
            info = AnimeHeaven.get_info(args.anime)
            episodes = itertools.takewhile(
                less_than_eq(info['episodes']), args.episodes)
            for episode in episodes:
                download(args.anime, episode, args.dest_dir)
        else:
            animes = AnimeHeaven.search_anime(args.anime)
            for anime in animes:
                print("{}\n  - Episodes: {}".format(
                    anime['anime_name'],
                    anime['episodes']
                ))
    except BaseException:
        sys.exit(1)


if __name__ == "__main__":
    main()
