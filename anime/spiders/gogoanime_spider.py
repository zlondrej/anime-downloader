#!/usr/bin/python3

import scrapy


class GogoAnime(scrapy.Spider):
    name = "gogoanime"

    def __init__(self, start_page):
        self.start_urls = [start_page]

    def parse(self, response):
        pages = response.css('.anime_video_body #episode_page li a')
        first = pages[0].xpath('@ep_start').extract_first()
        last = pages[-1].xpath('@ep_end').extract_first()

        episodes = response.css('.anime_info_episodes')
        movie_id = episodes.css('#movie_id::attr(value)').extract_first()
        default_ep = episodes.css('#default_ep::attr(value)').extract_first()

        yield response.follow(
            '/load-list-episode'
            '?ep_start={}&ep_end={}&id={}&default_ep={}'.format(
                first, last, movie_id, default_ep),
            callback=self.parse_episode_list
        )

    def parse_episode_list(self, response):
        for href in response.css('a::attr(href)').extract():
            yield response.follow(href.strip(), callback=self.parse_episode)

    def parse_episode(self, response):
        name = (response
                .xpath('/html/head/meta[@name="description"]/@content')
                .extract_first())
        servers = []
        for server in response.css('.anime_muti_link a'):
            url = server.xpath('@data-video').extract_first()
            server_name = server.xpath('text()').extract_first()
            servers.append({
                'name': server_name.lower(),
                'url': url,
            })

        yield {
            'episode': name,
            'video_providers': servers,
        }
