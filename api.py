import json
import tempfile
from datetime import datetime
from tools import SQLite3Connector
from flask import Flask, request, jsonify, send_file
from scrapy.crawler import CrawlerRunner
from scrapy.utils.project import get_project_settings
from twisted.internet import reactor, endpoints
from scrapy.utils.log import configure_logging
from twisted.web import server, wsgi


class ScrapyApi(Flask):

    def __init__(self, import_name=__package__, **kwargs):
            super(ScrapyApi, self).__init__(import_name, **kwargs)
            configure_logging({'LOG_FORMAT': '%(levelname)s: %(message)s'})
            self._init_url_rules()
            self.process = CrawlerRunner(get_project_settings())
            self.tp = reactor.getThreadPool()
            self.response_meta = {"meta": {
                "project": "WSF Web Scraper"
            }}

    def run(self, host=None, port=None, debug=None, **options):
        super(ScrapyApi, self).run(host, port, debug, **options)

    def _get_meta_response(self, res):
        res.update(self.response_meta)
        return res

    def _init_url_rules(self):
        """Attach the endpoints to run spiders and list the spiders
        that are available in the API
        """

        self.add_url_rule(
            '/spiders/list',
            view_func=self.list_spiders,
            methods=['GET'],
        )
        self.add_url_rule(
            '/spiders/<string:spider>/run',
            view_func=self.run_spider,
            methods=['GET'],
        )
        self.add_url_rule(
            '/scraped/import',
            view_func=self.import_db,
            methods=['POST'],
        )
        self.add_url_rule(
            '/scraped/export',
            view_func=self.export_db,
            methods=['GET'],
        )
        self.add_url_rule(
            '/scraped/reset',
            view_func=self.clear_scraps,
            methods=['GET'],
        )
        self.add_url_rule(
            '/crawls/list',
            view_func=self.list_crawls,
            methods=['GET'],
        )
        self.add_url_rule(
            '/crawls/stop',
            view_func=self.stop,
            methods=['GET'],
        )
        self.add_url_rule(
            '/',
            view_func=self.home,
            methods=['GET'],
        )

    def home(self):
        routes = [
            {
                "url": "/spiders/list",
                "method": "GET"
            },
            {
                "url": "/spiders/:spider/run",
                "method": "GET",
                "arguments": {
                    "spider": "name of the spider to run"
                }
            },
            {
                "url": "/crawls/list",
                "method": "GET"
            },
            {
                "url": "/crawls/stop",
                "method": "GET"
            },
            {
                "url": "/scraped/export",
                "method": "GET"
            },
            {
                "url": "/scraped/import",
                "method": "POST"
            },
            {
                "url": "/scraped/reset",
                "method": "GET"
            }
        ]
        result = self._get_meta_response({"routes": routes})
        return jsonify(result), 200

    def list_spiders(self):
        spiders = self.process.spider_loader.list()
        return jsonify({"data": {"spiders": spiders}}), 200

    def run_spider(self, spider):
        self.process.crawl(spider)
        self.process.join()
        return jsonify({"data": {"status": "running", "spider": spider}}), 200

    def list_crawls(self):
        crawls = self.process.crawlers
        spiders = []
        for crawl in crawls:
            start_time = crawl.stats.get_value('start_time')
            spider = {
                'spider':
                    crawl.spider.name,
                'strart_time':
                    start_time,
                'total_time':
                    str(datetime.now() - start_time),
                'item_dropped':
                    crawl.stats.get_value('item_dropped_count'),
                'item_scraped':
                    crawl.stats.get_value('item_scraped_count'),
                'total_requests':
                    crawl.stats.get_value('downloader/request_count'),
            }

            spiders.append(spider)
        return jsonify({"data": {"spiders": spiders}}), 200

    def stop(self):
        self.process.stop()
        return jsonify({"data": {"status": "success"}}), 200

    def export_db(self):
        database = SQLite3Connector()
        articles_rows = database.get_articles()
        articles = []
        for row in articles_rows:
            articles.append({
                'title': row['title'],
                'file_hash': row['file_hash'],
                'url': row['url'],
            })
        json_file = tempfile.NamedTemporaryFile()
        json_file.write(json.dumps(articles).encode())
        json_file.seek(0)
        return send_file(
            json_file,
            mimetype='application/json',
            as_attachment=True,
            attachment_filename='export.json'
        )

    def import_db(self):
        if request.files:
            data_file = request.files.get('file_url', None)
            if data_file.filename == '':
                return 'Filename must not be blank', 400
            if data_file.content_type == 'application/json':
                json_file = data_file.stream.read()
            else:
                return 'File format is not json.', 400

            database = SQLite3Connector()

            try:
                json_dict = json.loads(json_file)
                for article in json_dict:
                        database.insert_article(
                            article.get('title', ''),
                            article.get('file_hash', ''),
                            article.get('url', '')
                        )

                return '', 201
            except Exception as e:
                result = {"errors": [str(e)]}
                return jsonify(result), 400
        else:
            return 'No JSON file in request', 400

    def clear_scraps(self):
        try:
            self.database.reset_scraped()
            return '', 204
        except Exception as e:
            return str(e), 500


app = ScrapyApi(__name__)

if __name__ == '__main__':
        resource = wsgi.WSGIResource(reactor, reactor.getThreadPool(), app)
        site = server.Site(resource)
        http_server = endpoints.TCP4ServerEndpoint(reactor, 8080)
        http_server.listen(site)
        reactor.run()
