## Systen requirements

- python3
- pip for python3

## Python requirements

```
pip3 install --requirement requirements.txt
```

## Updates

I'm usually watching anime on thursdays/fridays so update frequency will be probably once a week.

If you find a bug or that script is outdated due to changes on http://animeheaven.eu site,
don't hesitate to open an issue.

## AnimeHeaven.eu

For usage use `./animeheaven.py --help`.

### Download specification file

It's possible to use *download specification file* using `--config <file>`
option. Example of such file could be something like this:

```json
[
  {"name": "Awesome anime", "dest_dir": "$HOME/Downloads/awesome-anime", "naming_scheme": "awesome-anime s01e{episode:02d}"},
  {"name": "Awesome anime - Season 2", "dest_dir": "$HOME/Downloads/awesome-anime", "naming_scheme": "awesome-anime s02e{episode:02d}"},
  {"name": "Long running anime", "dest_dir": "~/Downloads/long-one", "episodes": "511-latest"}
]
```

Executing `animeheaven --config <file>` will then download all episodes of
specified anime series that haven't been downloaded yet.

*Animeheaven* has some download limitations, but it's possible to overcome
them using proxy servers (by specifiying `HTTP_PROXY` environment variable).
Still, it shouldn't be problem unless you're hoarding animes. It should be
possible to download at least 10 episodes per day.
