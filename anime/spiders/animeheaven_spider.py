#!/usr/bin/python3

import re

import scrapy


class AnimeHeaven(scrapy.Spider):
    name = "animeheaven"

    download_link_re = re.compile(r"<a class='an' href='(http[^']+)'>")

    def __init__(self, start_page):
        self.start_urls = [start_page]

    def parse(self, response):
        episodes = response.css('a.infovan::attr(href)').extract()

        for episode in reversed(episodes):
            yield response.follow(episode, callback=self.parse_episode)

    def parse_episode(self, response):
        name = (
            response
            .css('.infoan2::text')
            .extract_first())
        number = (
            response
            .css('.c .infoan2').xpath('../text()')
            .extract_first()).rsplit(' ', 1)[-1]

        download = self.download_link_re.search(response.text)[1]

        yield {
            'anime': name,
            'episode': int(number),
            'videos': [{'@site': download}],
        }
