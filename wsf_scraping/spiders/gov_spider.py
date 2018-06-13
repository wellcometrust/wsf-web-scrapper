import scrapy
from urllib.parse import urlparse
from scrapy.http import Request
from .base_spider import BaseSpider
from wsf_scraping.items import GovArticle


class GovSpider(BaseSpider):
    name = 'gov_uk'
    custom_settings = {
        'JOBDIR': 'crawls/gov_uk'
    }

    def start_requests(self):
        """ This sets up the urls to scrape for each years."""
        urls = [
            'https://www.gov.uk/government/policies',
        ]

        for url in urls:
            self.logger.info('Initial url: %s', url)
            yield scrapy.Request(
                url=url,
                callback=self.parse,
                errback=self.on_error,
                dont_filter=True,
            )

    def parse(self, response):
        """ Parse the articles listing page and go to the next one.

        @url https://www.gov.uk/government/policies
        @returns items 0 0
        @returns requests 1
        """

        file_links = response.css(
            '.attachment-details .title a::attr("href")'
        ).extract()
        other_document_links = response.css(
            'li.document a::attr("href")'
        ).extract()

        for href in other_document_links:
            yield Request(
                url=response.urljoin(href),
                callback=self.parse,
                errback=self.on_error,
            )

        for fhref in file_links:
            yield Request(
                url=response.urljoin(fhref),
                callback=self.save_pdf,
                errback=self.on_error
            )

        next_page = response.css(
            '.pub-c-pagination__item--next a::attr("href")'
        ).extract_first()
        if next_page:
            yield Request(
                url=response.urljoin(next_page),
                callback=self.parse,
                errback=self.on_error,
            )

    def save_pdf(self, response):
        is_pdf = self._check_headers(response.headers)

        if not is_pdf:
            if self._check_headers(response.headers, b'text/html'):
                yield Request(
                    url=response.request.url,
                    callback=self.parse,
                    errback=self.on_error,
                )
            else:
                self.logger.info('Not a PDF, aborting (%s)', response.url)
                return

        # Download PDF file to /tmp
        filename = urlparse(response.url).path.split('/')[-1]
        if filename:
            with open('/tmp/' + filename, 'wb') as f:
                f.write(response.body)
            # Populate a WHOArticle Item
            gov_article = GovArticle({
                    'title': '',
                    'uri': response.request.url,
                    'pdf': filename,
                    'sections': {},
                    'keywords': {}
                }
            )

            yield gov_article