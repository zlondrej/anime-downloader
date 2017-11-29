#!/usr/bin/python

import json
import os
import os.path
import subprocess
import sys

provider_priority = [
    'openupload', 'oload', 'yourupload'
]


def main(input_file):
    episode_list = json.load(open(input_file))

    def mk_tuple(record):
        [name, number] = record['episode'].rsplit(' ', maxsplit=1)
        return (int(number), name, record['video_providers'])

    sorted_episodes = sorted([mk_tuple(record) for record in episode_list])

    for record in sorted_episodes:
        download(*record)


def download(number, name, providers):
    output = '{} {:03d}.mp4'.format(name, number)

    if os.path.isfile(output):
        print("Episode {} - already downloaded".format(number))
        return

    for prefered_provider in provider_priority:
        for provider in providers:
            if provider['name'] == prefered_provider:
                try:
                    print('Episode {} - downloading via provider {}'.format(
                        number, provider['name']
                    ))
                    result = subprocess.run(
                        ['youtube-dl', provider['url'], '-o', output],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE
                    )
                    result.check_returncode()
                    print('Episode {} - finished'.format(number))
                    return
                except subprocess.CalledProcessError as e:
                    print("Episode {} - failed ({})".format(
                            number, e.stderr
                        ),
                        file=sys.stderr
                    )

    print("Episode {} - not available".format(number))


if __name__ == "__main__":
    main(sys.argv[1])
