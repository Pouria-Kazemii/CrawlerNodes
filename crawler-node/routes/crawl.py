from flask import Blueprint, request, jsonify
from utils.helpers import get_crawler_by_type

crawl_bp = Blueprint('crawl', __name__)

@crawl_bp.route('/crawl', methods=['POST'])
def crawl():
    data = request.get_json()
    crawler_type = data.get("type")
    url = data.get("url")
    options = data.get("options", {})

    crawler = get_crawler_by_type(crawler_type)
    if not crawler:
        return jsonify({"error": "Unknown crawler type"}), 400

    result = crawler.crawl(url, options)
    return jsonify(result)
