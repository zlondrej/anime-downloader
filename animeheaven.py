#!/usr/bin/python3

import argparse
import base64
import codecs
import enum
import filelock
import itertools
import json
import lxml.html
import os
import os.path
import pathlib
import re
import requests
import shutil
import signal
import sys
import time
import tqdm
import traceback
import urllib

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException


session = requests.Session()
headers = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/68.0.3440.106 Safari/537.36'
}


class AnimeError(Exception):
    pass


class AbuseProtection(AnimeError):
    pass


class UpdateNecessaryError(AnimeError):
    pass


class DownloadState(enum.Enum):
    ASSIGNED_OR_DONE = enum.auto()
    DOWNLOADED = enum.auto()
    FAILED = enum.auto()

    def ok(self):
        return self is not self.FAILED


class AnimeHeaven:
    base_url = 'http://animeheaven.eu'
    anime_url = 'http://animeheaven.eu/i.php'  # a=<anime name>
    search_url = 'http://animeheaven.eu/search.php'  # q=<search query>
    watch_url = 'http://animeheaven.eu/watch.php'  # a=<anime name>&e=<episode>

    headless_webdriver = True
    interactive_console = False


    @classmethod
    def search_anime(cls, search):
        def parse_info(element):
            episode_count = element\
                .cssselect('.iepst2, .iepst2r')[0].text_content()
            anime_name = element.cssselect('.cona')[0].text

            return {
                'episodes': int(episode_count),
                'name': anime_name,
            }

        response = session.get(
            cls.search_url, params={'q': search}, headers=headers)
        response.raise_for_status()

        return map(
            parse_info,
            lxml.html.fromstring(response.text).cssselect('.iepcon'))

    @classmethod
    def get_info(cls, anime_name, fuzzy=True):
        if fuzzy:
            return cls._get_info_fuzzy(anime_name)
        else:
            return cls._get_info_strict(anime_name)

    @classmethod
    def _get_info_fuzzy(cls, anime_name):
        animes = list(cls.search_anime(anime_name))
        if len(animes) == 1:
            return animes[0]
        else:
            for anime in animes:
                if anime['name'].lower() == anime_name.lower():
                    return anime

    @classmethod
    def _get_info_strict(cls, anime_name):
        response = session.get(
            cls.anime_url, params={'a': anime_name}, headers=headers)
        response.raise_for_status()

        episodes = lxml.html.fromstring(response.text).xpath(
            '//div[@class="textd" and text()="Episodes:"]'
        )[0].getnext().text

        return {
            'name': anime_name,
            'episodes': int(episodes),
        }

    @classmethod
    def get_episode(cls, anime_name, episode):
        params = {
            'a': anime_name,
            'e': episode,
        }

        episode_url = '{}?{}'.format(
            cls.watch_url, urllib.parse.urlencode(params))

        browser = None
        try:
            try:
                browser = cls._init_browser()
                browser.get(episode_url)
                dl_element = browser.find_element_by_link_text('Force Download')
                download_link = dl_element.get_attribute('href')

                try:
                    # This whole section is just for purpose of triggering
                    # AnimeHeaven's agressive ad popups so the they won't
                    # have a reason to fight against script users so hard.
                    # But there will be no clicking unless we have download
                    # link already.

                    # Expand burger menu so we can get 'Random' link.
                    # Alternative would be to use larger browser window,
                    # but I think it's better this way for development.
                    browser.find_element_by_id('burgeri').click()
                    random_element = browser.find_element_by_link_text('Random')
                    # Let's click the link so they can be happy from theirs
                    # agressive advertisement popups opening.
                    random_element.click()
                except Exception:
                    # We have the download link so we don't really care
                    # about this failing (probably due to popups anyway).
                    pass

                return {
                    'name': anime_name,
                    'episode': int(episode),
                    'source': download_link,
                }
            except NoSuchElementException as no_such_element_exception:
                if 'abuse protection' in browser.page_source:
                    raise AbuseProtection
                raise UpdateNecessaryError
        except AbuseProtection:
            raise  # No interactive mode when abuse procection is detected.
        except Exception as exception:
            try:
                if cls.interactive_console:
                    from IPython import embed
                    traceback.print_exc()
                    embed()
            finally:
                raise exception
        finally:
            if browser is not None:
                browser.quit()

    @classmethod
    def _init_browser(cls):
        driver_options = webdriver.ChromeOptions()
        driver_options.add_argument('--incognito')
        driver_options.headless = cls.headless_webdriver

        browser = webdriver.Chrome(options=driver_options)
        browser.implicitly_wait(5)
        browser.get(cls.base_url)
        browser.add_cookie({'name': '_popfired', 'value': '1'})
        browser.add_cookie({'name': 'pp', 'value': 'c'})

        return browser


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


def progress_bar(response, initial=0):
    total_size = int(response.headers.get('content-length', 0)) + initial

    total_read = 0
    with tqdm.tqdm(
            total=total_size, initial=initial, unit='B',
            unit_scale=True, dynamic_ncols=True) as progress:
        for chunk in response.iter_content(2**16):
            progress.update(len(chunk))
            yield chunk


def abuse_protection_timeout(timeout):
    print("Abuse protection triggered: waiting {} seconds".format(timeout))
    with tqdm.tqdm(
            total=timeout, initial=0, unit='s', dynamic_ncols=True) as progress:
        for sec in range(timeout):
            time.sleep(1)
            progress.update(1)


def download(anime, episode, naming_scheme, dest_dir):
    log_entry = "{} - {:03d}".format(anime, episode)
    basename = naming_scheme.format(name=anime, episode=episode)
    filename = "{}.mp4".format(basename)

    dest_dir.mkdir(exist_ok=True)

    dest_file = dest_dir / filename
    temp_file = dest_dir / '~{}'.format(filename)
    temp_lock = filelock.FileLock(f'{temp_file}.lock', timeout=0)

    if dest_file.exists() or temp_lock.is_locked:
        return DownloadState.ASSIGNED_OR_DONE

    remove_lock = True
    # Retry with total possible timeout up to 10 minutes
    retry_timeouts = [0, 90, 30, 90, 150, 150]

    for retry_timeout in retry_timeouts:
        if retry_timeout > 0:
            abuse_protection_timeout(retry_timeout)
        try:
            with temp_lock:
                info = AnimeHeaven.get_episode(anime, episode)

                headers = {}
                fsize = 0
                if temp_file.exists():
                    fsize = temp_file.stat().st_size
                    headers['Range'] = f'bytes={fsize}-'

                response = session.get(
                    info['source'], stream=True, headers=headers)
                response.raise_for_status()

                mode = 'ab' if response.status_code == 206 else 'wb'

                with open(temp_file, mode) as output:
                    if response.status_code == 206:
                        print("{}: Resuming".format(log_entry))
                    else:
                        print("{}: Downloading".format(log_entry))
                        fsize = 0
                    for chunk in progress_bar(response, fsize):
                        output.write(chunk)

                shutil.move(temp_file, dest_file)

                return DownloadState.DOWNLOADED
        except filelock.Timeout:
            remove_lock = False
        except AbuseProtection:
            continue
        except KeyboardInterrupt:
            print("{}: Download canceled".format(log_entry))
            # Keep the file to be able to resume.
            raise
        finally:
            if remove_lock and os.path.exists(temp_lock.lock_file):
                os.remove(temp_lock.lock_file)

    return DownloadState.FAILED


def raise_signal(signal, frame):
    raise KeyboardInterrupt


def main():
    argp = argparse.ArgumentParser()

    argp.add_argument(
        'anime', nargs='*',
        help='anime to search/download, fuzzy names are allowed, '
             'multiple arguments can be used instead of spaces')
    argp.add_argument(
        '-d', '--download', dest='download', action='store_true',
        default=False, help='download instead of search')
    argp.add_argument(
        '-D', '--dir', dest='dest_dir', default='.', help='download directory')
    argp.add_argument(
        '-n', '--naming-scheme', dest='naming_scheme',
        default='{name} - {episode:03d}',
        help='pattern for filenames; Usable variables are {name} (string) and '
        '{episode} (integer). Follows python\'s format string syntax. '
        '(https://docs.python.org/3/library/string.html#formatstrings) '
        '(default: "%(default)s")')
    argp.add_argument(
        '-e', '--episodes', dest='episodes',
        type=selection_type, default=All(),
        help='select episodes to download (e.g.: '
             '"1,2,7-9,11-22", "latest", "55-latest", '
             '"latest-5" for 5 latest episodes)')

    argp.add_argument(
        '-c', '--config', dest='config',
        help='download specification file; JSON document contaning list of '
        'animes to download. Single anime entry is object that contains "name" '
        'property with name of anime. More properties are supported and their '
        'correspond with this programs\' options.')

    argp.add_argument(
        '--dev-mode', dest='dev_mode', action='store_true',
        help='Development option for testing. Disables headless WebDriver and '
        'open\'s up interactive terminal WebDriver fails to extract link from '
        'the page.')

    argp.epilog = """
AnimeHeaven.eu has relatively agressive abuse protection.
You can bypass this protection by using proxy server.
To use proxy server, just export `HTTP_PROXY` environment variable.
"""

    args = argp.parse_args()
    signal.signal(signal.SIGTERM, raise_signal)

    if args.dev_mode:
        AnimeHeaven.interactive_console = True
        AnimeHeaven.headless_webdriver = False

    try:
        if args.config:
            if not os.path.exists(args.config):
                argp.error(
                    'Specification file "{}" does not exist.'.format(
                        args.config))
            args.download = True
            with open(args.config) as spec_file:
                specs = json.load(spec_file)
            assert isinstance(specs, list)
            anime_specs = []
            for anime in specs:
                episodes = anime.get('episodes')
                episodes = selection_type(episodes) if episodes else All()
                dest_dir = os.path.expanduser(
                    os.path.expandvars(anime['dest_dir']))
                naming_scheme = anime.get('naming_scheme', args.naming_scheme)
                anime_specs.append(
                    (anime['name'], dest_dir, naming_scheme, episodes))
        else:
            anime_specs = [(
                ' '.join(args.anime),
                args.dest_dir,
                args.naming_scheme,
                args.episodes)]

        if args.download:
            for (anime_name, dest_dir, naming_scheme, episodes) in anime_specs:
                anime = AnimeHeaven.get_info(anime_name)
                if anime is None:
                    argp.exit(1, 'anime not found by given name\n')
                episodes = list(episodes(anime['episodes']))

                got_all = False
                while not got_all:
                    # Always try to download oldest episodes first
                    for episode in episodes:
                        state = download(
                            anime['name'], episode, naming_scheme,
                            pathlib.Path(dest_dir))

                        if episode == episodes[-1]:
                            got_all = state.ok()

                        if state is DownloadState.DOWNLOADED:
                            break

                        if state is DownloadState.FAILED:
                            argp.exit(1,
                                'Abuse protection wasn\'t lifted in '
                                '10 minutest. Aborting download.\n')
        else:
            animes = AnimeHeaven.search_anime(args.anime)
            for anime in animes:
                print("{}\n  - Episodes: {}".format(
                    anime['name'],
                    anime['episodes']
                ))

    except UpdateNecessaryError:
        argp.exit(2,
            'Script update may be neccessary due changes on site.\n'
            'Feel free to open an issue on '
            'https://github.com/JOndra91/anime-downloader\n')
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
